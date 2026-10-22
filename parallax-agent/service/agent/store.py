"""Saved conversations and saved views, in the service's own schema (parallax_agent) of the
product database -- never in the product's tables. uninstall.sql drops it.

A conversation row holds two things:
  memory      what the agent needs to continue it (its message history, the result sets
              and the views) -- so a conversation survives a service restart and can be
              reopened from History days later;
  transcript  what the dock shows (the user's questions, the answers, the chips), written
              by the browser after each answer.
A saved view is a frozen copy of one canvas view (spec with its rows) -- what a share link
opens."""

import itertools
import json
import os

import psycopg2
import psycopg2.extras

from . import state

_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS parallax_agent;
CREATE TABLE IF NOT EXISTS parallax_agent.conversation (
  id          text PRIMARY KEY,
  title       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  transcript  jsonb,
  memory      jsonb
);
CREATE TABLE IF NOT EXISTS parallax_agent.saved_view (
  id          text PRIMARY KEY,
  title       text,
  question    text,
  conversation_id text,
  spec        jsonb NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
"""

_ready = {"ok": False}


def _conn():
    conn = psycopg2.connect(os.environ.get("KSSL_DSN", ""), connect_timeout=5)
    conn.autocommit = True
    return conn


def ensure() -> None:
    try:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
        finally:
            conn.close()
        _ready["ok"] = True
    except Exception as exc:  # history is a convenience; the chat works without it
        print(f"[agent] saved conversations unavailable: {exc}", flush=True)


def ready() -> bool:
    return _ready["ok"]


# ---------------------------------------------------------------- serialisation

def _block(b):
    if isinstance(b, dict):
        return b
    return b.model_dump(mode="json", exclude_none=True)


def _message(m):
    c = m["content"]
    return {"role": m["role"], "content": c if isinstance(c, str) else [_block(b) for b in c]}


def _memory(conv) -> dict:
    return {
        "messages": [_message(m) for m in conv.messages],
        "results": {rid: {"title": rs.title, "sql": rs.sql, "columns": rs.columns, "rows": rs.rows,
                          "truncated": rs.truncated, "ms": rs.ms, "assumptions": rs.assumptions}
                    for rid, rs in conv.results.items()},
        "views": conv.views,
        "view_specs": conv.view_specs,
        "recent_questions": conv.recent_questions,
    }


# ---------------------------------------------------------------- conversations

def save_memory(conv) -> None:
    if not ready() or not conv.messages:
        return
    title = (conv.recent_questions[0] if conv.recent_questions else "Conversation")[:120]
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO parallax_agent.conversation (id, title, memory) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET memory = EXCLUDED.memory, updated_at = now(), "
                "title = COALESCE(parallax_agent.conversation.title, EXCLUDED.title)",
                (conv.id, title, psycopg2.extras.Json(_memory(conv), dumps=lambda o: json.dumps(o, default=str))))
    finally:
        conn.close()


def save_transcript(conv_id: str, title: str, messages: list) -> None:
    if not ready():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO parallax_agent.conversation (id, title, transcript) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET transcript = EXCLUDED.transcript, updated_at = now(), "
                "title = COALESCE(NULLIF(EXCLUDED.title, ''), parallax_agent.conversation.title)",
                (conv_id, (title or "")[:120], psycopg2.extras.Json(messages)))
    finally:
        conn.close()


def load(conv_id: str):
    """The Conversation as it was, or None."""
    if not ready() or not conv_id:
        return None
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT memory FROM parallax_agent.conversation WHERE id = %s", (conv_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    mem = row and row["memory"]
    if not mem:
        return None
    conv = state.Conversation(id=conv_id)
    conv.messages = mem.get("messages") or []
    for rid, r in (mem.get("results") or {}).items():
        conv.results[rid] = state.ResultSet(id=rid, **r)
    conv.views = mem.get("views") or []
    conv.view_specs = mem.get("view_specs") or {}
    conv.recent_questions = mem.get("recent_questions") or []
    n = max([int(r[1:]) for r in conv.results if r[1:].isdigit()] or [0])
    conv._ids = itertools.count(n + 1)
    return conv


def list_conversations(limit: int = 40) -> list:
    if not ready():
        return []
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title, updated_at, jsonb_array_length(COALESCE(transcript, '[]')) AS n "
                        "FROM parallax_agent.conversation WHERE transcript IS NOT NULL "
                        "ORDER BY updated_at DESC LIMIT %s", (limit,))
            return [{**r, "updated_at": r["updated_at"].isoformat()} for r in cur.fetchall()]
    finally:
        conn.close()


def get_conversation(conv_id: str):
    if not ready():
        return None
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title, transcript, memory -> 'view_specs' AS views, memory -> 'views' AS order_ "
                        "FROM parallax_agent.conversation WHERE id = %s", (conv_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    specs = row["views"] or {}
    order = [v["id"] for v in (row["order_"] or []) if v.get("id") in specs]
    return {"id": row["id"], "title": row["title"], "transcript": row["transcript"] or [],
            "views": [specs[i] for i in order]}


def delete_conversation(conv_id: str) -> None:
    if not ready():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM parallax_agent.conversation WHERE id = %s", (conv_id,))
    finally:
        conn.close()


# ---------------------------------------------------------------- saved views

def save_view(spec: dict, conv_id: str) -> str:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO parallax_agent.saved_view (id, title, question, conversation_id, spec) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (spec["id"], spec.get("title"), spec.get("question"), conv_id,
                 psycopg2.extras.Json(spec, dumps=lambda o: json.dumps(o, default=str))))
    finally:
        conn.close()
    return spec["id"]


def list_views(limit: int = 40) -> list:
    if not ready():
        return []
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title, question, created_at FROM parallax_agent.saved_view "
                        "ORDER BY created_at DESC LIMIT %s", (limit,))
            return [{**r, "created_at": r["created_at"].isoformat()} for r in cur.fetchall()]
    finally:
        conn.close()


def get_view(view_id: str):
    if not ready():
        return None
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT spec FROM parallax_agent.saved_view WHERE id = %s", (view_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def delete_view(view_id: str) -> None:
    if not ready():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM parallax_agent.saved_view WHERE id = %s", (view_id,))
    finally:
        conn.close()
