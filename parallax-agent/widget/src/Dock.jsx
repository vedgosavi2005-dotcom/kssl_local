import { useEffect, useRef, useState } from "react";
import { deleteConversation, deleteSavedView, listConversations, listSavedViews } from "./api.js";
import { renderMarkdown } from "./markdown.jsx";
import { TEXT, fillText } from "./product.js";

const MODEL_LABEL = { "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-opus-5-5": "Claude Opus 5.5", "claude-haiku-5-5": "Claude Haiku 5.5" };

/* THE DOCK: the chat, always on the right while the product (or the canvas) changes
   beside it. */
export default function Dock(props) {
  const { messages, busy, status, budget, debug, onClose, onReset, onSend, onStop, onShowView,
    onOpenPage, onToggleCanvas, canvasOpen, hasViews, pageText, suggestions, onOpenConversation, onOpenSavedView } = props;
  const [history, setHistory] = useState(false);
  const [text, setText] = useState("");
  const logRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const focus = () => inputRef.current && inputRef.current.focus();
    window.addEventListener("pa-focus-input", focus);
    return () => window.removeEventListener("pa-focus-input", focus);
  }, []);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(140, el.scrollHeight)}px`;
  }, [text]);

  const submit = (value) => {
    const q = (value ?? text).trim();
    if (!q || busy) return;
    setText("");
    onSend(q);
  };

  const disabled = status && !status.enabled;
  const model = status && status.models ? MODEL_LABEL[status.models.orchestrator] || status.models.orchestrator : "Claude";
  const provider = status && status.provider === "openrouter" ? "via OpenRouter" : "";

  return (
    <aside className="pa-dock" aria-label="Parallax Analyst chat">
      <header className="pa-dock-head">
        <div className="pa-dock-title">
          <span className="pa-tick" />
          <div>
            <div className="pa-dock-name">Parallax Analyst</div>
            <div className="pa-dock-ctx" title={pageText}>{pageText ? `Looking at: ${pageText}` : fillText(TEXT.tagline)}</div>
          </div>
        </div>
        <div className="pa-dock-actions">
          {hasViews ? (
            <button className="pa-btn" onClick={onToggleCanvas} title={canvasOpen ? "Back to the page" : "Show the last generated view"} type="button">
              {canvasOpen ? "Page" : "View"}
            </button>
          ) : null}
          <button className={`pa-btn${history ? " primary" : ""}`} onClick={() => setHistory((h) => !h)} title="Earlier conversations and saved views" type="button">History</button>
          <button className="pa-btn" onClick={onClose} title="Close the chat" type="button" aria-label="Close the chat">✕</button>
        </div>
      </header>

      {disabled ? <div className="pa-banner">{status.error || (status.db && status.db.error) || "The analyst is not configured: add a model key to parallax-agent/.env and restart the service."}</div> : null}

      {history ? (
        <History
          onClose={() => setHistory(false)}
          onOpenConversation={(id) => { setHistory(false); onOpenConversation(id); }}
          onOpenSavedView={(id) => { setHistory(false); onOpenSavedView(id); }}
        />
      ) : null}

      <div className="pa-log" ref={logRef} hidden={history}>
        {messages.length === 0 ? (
          <div className="pa-empty">
            <p>{fillText(TEXT.welcome)}</p>
            <div className="pa-eyebrow">For this page</div>
            <div className="pa-starters">
              {(suggestions || []).map((s) => (
                <button className="pa-starter" disabled={busy || disabled} key={s} onClick={() => submit(s)} type="button">{s}</button>
              ))}
            </div>
            <div className="pa-eyebrow" style={{ marginTop: 16 }}>Across the platform</div>
            <div className="pa-starters">
              {TEXT.general.map(fillText).filter((g) => !(suggestions || []).includes(g)).map((s) => (
                <button className="pa-starter" disabled={busy || disabled} key={s} onClick={() => submit(s)} type="button">{s}</button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div className="pa-msg pa-user" key={m.id}><div className="pa-bubble">{m.text}</div></div>
            ) : (
              <Answer key={m.id} m={m} question={(messages[i - 1] || {}).text} debug={debug} onOpenPage={onOpenPage}
                onSend={submit} onShowView={onShowView} busy={busy} />
            ),
          )
        )}
      </div>

      <div className="pa-compose">
        <button
          aria-label="New conversation"
          className="pa-reset"
          disabled={!messages.length}
          onClick={onReset}
          title="New conversation: clears this chat so the next question starts fresh"
          type="button"
        >
          ↺
        </button>
        <textarea
          aria-label="Ask Parallax Analyst"
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={busy ? "Working on it…" : "Ask a question, or say what to show…"}
          ref={inputRef}
          rows={1}
          value={text}
        />
        {busy ? (
          <button className="pa-send pa-stop" onClick={onStop} title="Stop" type="button">■</button>
        ) : (
          <button className="pa-send" disabled={!text.trim() || disabled} onClick={() => submit()} title="Send (Enter)" type="button">→</button>
        )}
      </div>
      {debug ? (
        <footer className="pa-foot">
          <span>{model} {provider}</span>
          {budget && budget.tracked ? <span>${budget.spent_usd.toFixed(2)} of ${budget.budget_usd.toFixed(0)} used</span> : null}
        </footer>
      ) : <div className="pa-foot-gap" />}
    </aside>
  );
}

function Answer({ m, question, debug, onShowView, onOpenPage, onSend, busy }) {
  const [open, setOpen] = useState(false);
  const queries = m.steps.filter((s) => s.kind === "query");
  const secs = m.t1 ? ((m.t1 - m.t0) / 1000).toFixed(1) : null;
  return (
    <div className="pa-msg pa-bot">
      {debug && queries.length ? (
        <div className="pa-activity">
          <button className="pa-activity-toggle" onClick={() => setOpen((o) => !o)} type="button">
            {open ? "▾" : "▸"} {queries.length} quer{queries.length === 1 ? "y" : "ies"} run{secs ? ` · ${secs}s` : ""}
          </button>
          {open ? (
            <ol className="pa-queries">
              {queries.map((q, i) => (
                <li className={q.error ? "pa-q-err" : ""} key={i}>
                  <div className="pa-q-title">
                    {q.kind === "categorize" ? "Categorised: " : ""}{q.title}
                    <span>{q.error ? " · failed, retried" : ` · ${q.row_count} rows`}</span>
                  </div>
                  <pre>{q.error ? `${q.error}\n\n${q.sql}` : q.sql}</pre>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}

      {m.steps.filter((s) => s.kind !== "query").map((s, i) =>
        s.kind === "view" ? (
          <button className="pa-viewchip" key={i} onClick={() => onShowView(s.id)} type="button">
            <span className="pa-viewchip-ico">▦</span>
            <span className="pa-viewchip-t">{s.title}</span>
            <span className="pa-viewchip-a">{s.reopened ? "Shown again" : "Open view"}</span>
          </button>
        ) : (
          <button className="pa-navchip" key={i} onClick={() => onOpenPage(s.pillar, s.view, s.payload, s.focus)} type="button">
            → Opened {s.label}{s.focus && !String(s.label).toLowerCase().includes(String(s.focus).toLowerCase()) ? ` · ${s.focus}` : ""}
          </button>
        ),
      )}

      {m.text ? <div className="pa-answer">{renderMarkdown(m.text)}</div> : null}

      {debug && m.verify && m.verify.status === "verified" ? (
        <div className="pa-verify ok">✓ {m.verify.checked} figure{m.verify.checked === 1 ? "" : "s"} checked against the data</div>
      ) : null}
      {m.verify && m.verify.status === "issues" ? (
        <div className="pa-verify warn">
          <div>Please double-check: {m.verify.issues.length === 1 ? "one statement" : "some statements"} could not be confirmed against the platform data.</div>
          <ul>{m.verify.issues.map((x, i) => <li key={i}><b>{x.claim}</b>: {x.problem}</li>)}</ul>
        </div>
      ) : null}

      {m.notice ? (
        <div className={`pa-notice pa-notice-${m.notice.kind}`}>
          <p>{m.notice.text}</p>
          {m.notice.suggestions.length ? (
            <div className="pa-chips">
              {m.notice.suggestions.map((s) => (
                <button className="pa-chip" disabled={busy} key={s} onClick={() => onSend(s)} type="button">{s}</button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {m.contextLost ? (
        <div className="pa-note">The earlier part of this chat is no longer available to the assistant, so this answer starts fresh.</div>
      ) : null}

      {m.error ? (
        <div className="pa-error">
          {m.error}
          {m.retry && question ? (
            <button className="pa-btn pa-retry" disabled={busy} onClick={() => onSend(question)} type="button">↻ Retry</button>
          ) : null}
        </div>
      ) : null}

      {!m.done ? (
        <div className="pa-status">
          <span className="pa-dots"><i /><i /><i /></span>
          {m.status || "Working"}
        </div>
      ) : null}
    </div>
  );
}


/* Earlier conversations (reopen and continue) and saved views (reopen or share). */
function History({ onClose, onOpenConversation, onOpenSavedView }) {
  const [convs, setConvs] = useState(null);
  const [views, setViews] = useState(null);
  const load = () => {
    listConversations().then(setConvs).catch(() => setConvs([]));
    listSavedViews().then(setViews).catch(() => setViews([]));
  };
  useEffect(load, []);
  const when = (iso) => {
    try {
      return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "";
    }
  };
  return (
    <div className="pa-history">
      <div className="pa-history-head">
        <span className="pa-eyebrow" style={{ margin: 0 }}>History</span>
        <button className="pa-link" onClick={onClose} type="button">Back to chat</button>
      </div>
      <div className="pa-eyebrow">Saved views</div>
      {views === null ? <div className="pa-note">Loading…</div> : views.length === 0 ? (
        <div className="pa-note">No saved views yet. Use ☆ Save on a generated view.</div>
      ) : views.map((v) => (
        <div className="pa-hist-row" key={v.id}>
          <button className="pa-hist-open" onClick={() => onOpenSavedView(v.id)} type="button">
            <span className="pa-hist-t">▦ {v.title}</span>
            <span className="pa-hist-d">{when(v.created_at)}</span>
          </button>
          <button className="pa-hist-del" onClick={() => deleteSavedView(v.id).then(load)} title="Delete" type="button">✕</button>
        </div>
      ))}
      <div className="pa-eyebrow" style={{ marginTop: 18 }}>Conversations</div>
      {convs === null ? <div className="pa-note">Loading…</div> : convs.length === 0 ? (
        <div className="pa-note">No earlier conversations.</div>
      ) : convs.map((c) => (
        <div className="pa-hist-row" key={c.id}>
          <button className="pa-hist-open" onClick={() => onOpenConversation(c.id)} type="button">
            <span className="pa-hist-t">{c.title}</span>
            <span className="pa-hist-d">{when(c.updated_at)}</span>
          </button>
          <button className="pa-hist-del" onClick={() => deleteConversation(c.id).then(load)} title="Delete" type="button">✕</button>
        </div>
      ))}
    </div>
  );
}
