"""Per-conversation state: the orchestrator's message history and the result sets the data
agent produced. In memory -- the backend runs one uvicorn worker (see Dockerfile); a
restart starts a fresh conversation, which the frontend handles."""

import asyncio
import itertools
import time
import uuid
from dataclasses import dataclass, field

from . import config


@dataclass
class ResultSet:
    id: str
    title: str
    sql: str
    columns: list            # [{"name", "type"}]
    rows: list               # list of lists, same order as columns
    truncated: bool = False
    ms: int = 0
    assumptions: list = field(default_factory=list)   # set by categorize

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def column_names(self) -> list:
        return [c["name"] for c in self.columns]

    def column_type(self, name: str):
        for c in self.columns:
            if c["name"] == name:
                return c["type"]
        return None

    def records(self) -> list:
        names = self.column_names()
        return [dict(zip(names, r)) for r in self.rows]

    def public(self) -> dict:
        """What the frontend receives with a view."""
        return {"id": self.id, "title": self.title, "sql": self.sql, "columns": self.columns,
                "rows": self.rows, "truncated": self.truncated}

    def preview(self, n: int = config.PREVIEW_ROWS, cell_chars: int = 0) -> dict:
        """What a model sees: shape, a few rows, per-column stats over ALL rows (sums, and
        for low-cardinality columns the count of each value). Never the whole set."""
        stats = {}
        for i, c in enumerate(self.columns):
            vals = [r[i] for r in self.rows if r[i] is not None]
            if c["type"] == "number" and vals:
                stats[c["name"]] = {"min": min(vals), "max": max(vals), "sum": round(sum(vals), 4),
                                    "nulls": self.row_count - len(vals)}
            elif c["type"] in ("text", "date", "boolean"):
                counts = {}
                for v in vals:
                    counts[str(v)] = counts.get(str(v), 0) + 1
                stats[c["name"]] = {"distinct": len(counts),
                                    **({"value_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}
                                       if len(counts) <= 15 else {}),
                                    "nulls": self.row_count - len(vals)}
        rows = self.rows[:n]
        if cell_chars:
            rows = [[v[:cell_chars] + "…" if isinstance(v, str) and len(v) > cell_chars else v for v in r] for r in rows]
        shown = min(n, self.row_count)
        return {"result_id": self.id, "title": self.title, "row_count": self.row_count,
                "truncated": self.truncated, "columns": self.columns,
                "rows": rows, "rows_shown": shown, "stats": stats,
                **({"note": f"Only the first {shown} of {self.row_count} rows are listed here. The full result is "
                            f"stored as {self.id}; categorize and the canvas always use every row, so never page "
                            "through it with OFFSET."} if shown < self.row_count else {}),
                **({"assumptions": self.assumptions} if self.assumptions else {})}


@dataclass
class Conversation:
    id: str
    messages: list = field(default_factory=list)      # orchestrator history, append-only
    results: dict = field(default_factory=dict)        # result_id -> ResultSet
    views: list = field(default_factory=list)          # [{id, title, question, result_ids}], newest last
    view_specs: dict = field(default_factory=dict)     # id -> the hydrated spec, so a view can be reopened
    recent_questions: list = field(default_factory=list)
    turn_reads: list = field(default_factory=list)     # page content read this turn (for the verifier)
    updated: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def add_result(self, **kw) -> ResultSet:
        rs = ResultSet(id=f"r{next(self._ids)}", **kw)
        self.results[rs.id] = rs
        return rs


_conversations: dict = {}


def get_or_create(conv_id) -> Conversation:
    now = time.time()
    for cid in [k for k, c in _conversations.items() if now - c.updated > config.CONVERSATION_TTL_S]:
        _conversations.pop(cid, None)
    conv = _conversations.get(conv_id) if conv_id else None
    if conv is None:
        if len(_conversations) >= config.MAX_CONVERSATIONS:
            oldest = min(_conversations.values(), key=lambda c: c.updated)
            _conversations.pop(oldest.id, None)
        conv = Conversation(id=uuid.uuid4().hex)
        _conversations[conv.id] = conv
    conv.updated = now
    return conv


def get(conv_id):
    return _conversations.get(conv_id) if conv_id else None


def register(conv) -> Conversation:
    conv.updated = time.time()
    _conversations[conv.id] = conv
    return conv


def drop(conv_id) -> None:
    _conversations.pop(conv_id, None)
