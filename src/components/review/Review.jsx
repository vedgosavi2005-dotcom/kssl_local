import { createContext, useContext, useEffect, useState } from "react";
import "../../styles/review.css";

/* The review copy. Same app in Vite mode "review" (`npm run dev:review`, 127.0.0.1:5180) against
   the review backend (KSSL_VIEW=review, :8601), which reads the staging DB and sends a status per
   card and per setup table. Approve copies the card (with everything under it) from the staging DB
   to the serving DB, the live UI (backend/review.py). In the live build REVIEW is false and
   everything here renders nothing.

   Cards carry `_src: {t, k, id}` (table, key column, key value); <Review src={item._src} /> attaches
   the controls. Setup tables (ui.* and the reference tables) are approved whole from the banner. */
export const REVIEW = import.meta.env.VITE_REVIEW === "1";

const Ctx = createContext(null);
const LABEL = { new: "new", changed: "changed", live: "live", rejected: "rejected" };

async function post(path, params) {
  const res = await fetch(`${path}?${new URLSearchParams(params)}`, { method: "POST", headers: { "X-KSSL-Write": "1" } });   // backend CSRF guard
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status}`);
  return body;
}

export function ReviewProvider({ initial, children }) {
  const [st, setSt] = useState(initial || {});
  const [panel, setPanel] = useState(null); // {kind: "trace", t, id, n} | {kind: "setup"}
  if (!REVIEW) return children;
  const apply = (body) => {
    setSt(body.review || {});
    setPanel((p) => (p && p.kind === "trace" ? { ...p, n: (p.n || 0) + 1 } : p));
  };
  const act = (t, id, action) =>
    post("/api/review", { table: t, key: id, action }).then(apply, (e) => alert(`Could not ${action}: ${e.message}`));
  const actTable = (schema, table, action) =>
    post("/api/review/table", { schema, table, action }).then(apply, (e) => alert(`Could not ${action}: ${e.message}`));
  const counts = {};
  Object.values(st.cards || {}).forEach((tab) => Object.values(tab).forEach((c) => (counts[c.s] = (counts[c.s] || 0) + 1)));
  const pending = Object.values(st.tables || {}).reduce(
    (n, tabs) => n + Object.values(tabs).filter((x) => x.s !== "live").length,
    0,
  );
  return (
    <Ctx.Provider value={{ st, act, actTable, openTrace: (t, id) => setPanel({ kind: "trace", t, id }) }}>
      {children}
      <div className="rv-banner">
        <span>
          REVIEW COPY · {counts.new || 0} new · {counts.changed || 0} changed · {counts.live || 0} live · {counts.rejected || 0} rejected
        </span>
        <button type="button" onClick={() => setPanel({ kind: "setup" })}>
          Setup tables{pending ? ` · ${pending} to approve` : ""}
        </button>
      </div>
      {panel?.kind === "trace" && (
        <TraceDrawer {...panel} onOpen={(t, id) => setPanel({ kind: "trace", t, id })} onClose={() => setPanel(null)} />
      )}
      {panel?.kind === "setup" && <SetupPanel st={st} actTable={actTable} onClose={() => setPanel(null)} />}
    </Ctx.Provider>
  );
}

/* Approve / Reject / Undo / Unpublish / Trace for one card. `src` = the object's _src. */
export function Review({ src, style }) {
  const ctx = useContext(Ctx);
  if (!REVIEW || !ctx || !src || !src.t || src.id === undefined || src.id === null || src.id === "") return null;
  const { t } = src;
  const id = String(src.id);
  const c = ctx.st.cards?.[t]?.[id] || { s: "new", live: false };
  const stop = (e) => e.stopPropagation();
  const btn = (action, label, cls, title) => (
    <button type="button" className={cls} title={title} onClick={() => ctx.act(t, id, action)}>
      {label}
    </button>
  );
  return (
    <div className="rv-bar" style={style} onClick={stop} onKeyDown={stop} role="group" aria-label="Review">
      <span className={`rv-status rv-${c.s}`} title={c.s === "rejected" && c.live ? "an older version is still live" : ""}>
        {LABEL[c.s] || c.s}
        {c.s === "rejected" && c.live ? " · old live" : ""}
      </span>
      {c.s !== "live" && btn("approve", c.s === "changed" ? "Approve change" : "Approve", "rv-ok", "Copy this version to the live UI")}
      {(c.s === "new" || c.s === "changed") && btn("reject", "Reject", "rv-no", "Keep this version off the live UI")}
      {c.s === "rejected" && btn("undo", "Undo", "", "Back to pending")}
      {c.live && btn("unpublish", "Unpublish", "rv-no", "Remove from the live UI, with everything under it")}
      <button type="button" onClick={() => ctx.openTrace(t, id)}>
        Trace
      </button>
    </div>
  );
}

/* For pages that draw their records as an HTML string: the same records as a plain list with a
   Review bar each, shown in the review copy only. items = [{src, label}]. */
export function ReviewList({ items, title }) {
  if (!REVIEW || !items || !items.length) return null;
  return (
    <details className="rv-list" open>
      <summary>
        {title || "Review"} · {items.length}
      </summary>
      {items.map((it, i) => (
        <div className="rv-li" key={`${it.src?.t}:${it.src?.id}:${i}`}>
          <span>{it.label || it.src?.id}</span>
          <Review src={it.src} />
        </div>
      ))}
    </details>
  );
}

function SetupPanel({ st, actTable, onClose }) {
  const [showEmpty, setShowEmpty] = useState(false);
  const groups = [
    ["ui", "Page setup (ui tables)"],
    ["serving", "Reference tables (serving)"],
  ];
  return (
    <div className="rv-drawer" role="dialog" aria-label="Setup tables">
      <div className="rv-dh">
        <b>Setup tables</b>
        <button type="button" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <p className="rv-dim">
        No cards here: one Approve per table replaces the whole live table with the staging table; Unpublish empties it.
      </p>
      <label className="rv-dim">
        <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} /> show tables that are empty on both sides
      </label>
      {groups.map(([schema, heading]) => {
        const all = Object.entries(st.tables?.[schema] || {});
        const rows = all.filter(([, x]) => showEmpty || x.n || x.live_n);
        return (
          <div className="rv-sec" key={schema}>
            <div className="rv-h">
              {heading} · {rows.length}
              {all.length > rows.length ? ` of ${all.length}` : ""}
            </div>
            {rows.length === 0 && <p className="rv-dim">Nothing staged.</p>}
            {rows.map(([name, x]) => (
              <div className="rv-li" key={name}>
                <span className="rv-tname">
                  {name}
                  <span className="rv-dim">
                    {" "}
                    · staging {x.n} · live {x.live_n}
                  </span>
                </span>
                <div className="rv-bar">
                  <span className={`rv-status rv-${x.s}`}>{LABEL[x.s] || x.s}</span>
                  {x.s !== "live" && (
                    <button type="button" className="rv-ok" onClick={() => actTable(schema, name, "approve")}>
                      Approve setup changes
                    </button>
                  )}
                  {x.live_n > 0 && (
                    <button type="button" className="rv-no" onClick={() => actTable(schema, name, "unpublish")}>
                      Unpublish
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function TraceDrawer({ t, id, n, onOpen, onClose }) {
  const [node, setNode] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setErr("");
    fetch(`/api/review/trace?${new URLSearchParams({ table: t, key: id })}`)
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(new Error(j.detail)))))
      .then(setNode)
      .catch((e) => setErr(String(e.message || e)));
  }, [t, id, n]);
  return (
    <div className="rv-drawer" role="dialog" aria-label="Data trace">
      <div className="rv-dh">
        <b>Where this card's data lives</b>
        <button type="button" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <p className="rv-dim">
        Staging (the staging database) = what you review. Approve copies these rows to the same tables in <code>serving</code> (the
        live UI).
        <span className="rv-chg"> Yellow</span> = differs from live, with the live value under it.
      </p>
      {err && <p className="rv-err">{err}</p>}
      {!node && !err && <p>Loading…</p>}
      {node && (
        <>
          <TableBlock node={node} />
          {node.parents?.length > 0 && (
            <div className="rv-sec">
              <div className="rv-h">Belongs to</div>
              {node.parents.map((p) => (
                <button type="button" className="rv-link" key={p.table + p.key} onClick={() => onOpen(p.table.replace("staging.", ""), p.key)}>
                  {p.table} · {p.key_column} = {p.key} → trace
                </button>
              ))}
            </div>
          )}
          <Children node={node} />
        </>
      )}
    </div>
  );
}

function Children({ node }) {
  if (!node.children.length) return <p className="rv-dim">No child rows.</p>;
  return node.children.map((c, i) => (
    <details className="rv-sec" key={c.table + c.sql + i}>
      <summary className="rv-h">
        {c.table} · {c.rows.length} row{c.rows.length === 1 ? "" : "s"}
        {c.removed.length ? ` · ${c.removed.length} removed on approve` : ""}
      </summary>
      <TableBlock node={c} />
      {c.children.length > 0 && <Children node={c} />}
    </details>
  ));
}

const show = (v) => (v === null || v === undefined ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));

function TableBlock({ node }) {
  return (
    <div className="rv-sec">
      <div className="rv-h">
        {node.table} <span className="rv-dim">→ {node.live_table}</span>
      </div>
      <code className="rv-sql" title="Click to copy" onClick={() => navigator.clipboard?.writeText(node.sql)}>
        {node.sql}
      </code>
      {node.rows.length === 0 && <p className="rv-dim">Not in staging.</p>}
      {node.rows.map(({ row, sources, live }, i) => (
        <table className="rv-tbl" key={i}>
          <caption className={live === null ? "rv-new" : ""}>
            {live === null ? "new row (not live yet)" : live && Object.keys(live).length ? `${Object.keys(live).length} field(s) differ from live` : "same as live"}
          </caption>
          <tbody>
            {Object.entries(row).map(([col, val]) => {
              const src = sources.filter((s) => s.column_name === col);
              const changed = live && col in live;
              if (val === null && src.length === 0 && !changed) return null;
              return (
                <tr key={col} className={changed ? "rv-chg-row" : ""}>
                  <th>{col}</th>
                  <td>
                    {show(val)}
                    {changed && <div className="rv-old">live: {show(live[col])}</div>}
                    {src.map((s, j) => (
                      <div className="rv-src" key={j}>
                        <a href={s.source_url} target="_blank" rel="noreferrer">
                          {s.source_tier || "source"} · {s.document_id || s.source_url}
                        </a>
                        {s.quote && <q>{s.quote}</q>}
                      </div>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ))}
      {node.removed?.map((r, i) => (
        <p className="rv-removed" key={i}>
          Live row removed on approve: {show(r[node.key_column])}
          <span className="rv-dim"> {show(Object.fromEntries(Object.entries(r).filter(([, v]) => v !== null).slice(0, 4)))}</span>
        </p>
      ))}
    </div>
  );
}
