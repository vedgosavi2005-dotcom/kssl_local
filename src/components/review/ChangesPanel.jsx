import { useEffect, useState } from "react";
import "../../styles/pipeline.css";
import { currentUser } from "../../lib/login";

/* CHANGES FROM THE NEWS (review site only; owner 24 Oct: "show it on review and mark it as a new thing, so the reviewer can say:
   should we continue or not?"). What an article says that is new or different from our records -- a new rival product, a spec,
   a leadership change, a partner, a plant, a company fact -- waits here as a proposal (backend/change_proposals.py). Accept writes
   it into the review data (it then shows as NEW / CHANGED and goes live with the usual Approve); Reject keeps it out for good. */

const KIND = { new_product: "New product", spec: "Spec", leadership: "Leadership change", partner: "New partner", location: "New plant / location",
               company_fact: "Company fact" };
const call = async (path, body) => {
  const r = await fetch(path, body ? { method: "POST", headers: { "X-KSSL-Write": "1", "X-KSSL-User": currentUser() || "", "Content-Type": "application/json" },
                                      body: JSON.stringify(body) } : undefined);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `${r.status}`);
  return j;
};

export function usePendingChanges() {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (import.meta.env.VITE_REVIEW !== "1") return;    // the live build has no review API
    call("/api/review/changes").then((d) => setN((d.items || []).length), () => setN(0));
  }, []);
  return [n, setN];
}

export default function ChangesPanel({ onClose, onCount }) {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("pending");
  const [edit, setEdit] = useState({});
  const [done, setDone] = useState(0);
  const [err, setErr] = useState("");
  const load = () => call(`/api/review/changes?status=${status}`).then((d) => { setItems(d.items || []); if (status === "pending" && onCount) onCount((d.items || []).length); },
    (e) => setErr(e.message));
  useEffect(() => { setItems(null); load(); }, [status]);   // eslint-disable-line react-hooks/exhaustive-deps
  const decide = (p, action) => {
    const body = { id: p.proposal_id };
    if (action === "accept" && edit[p.proposal_id] != null && edit[p.proposal_id] !== p.proposed_value) body.value = edit[p.proposal_id];
    if (action === "reject") { const note = window.prompt("Why reject? (optional)", ""); if (note === null) return; body.note = note; }
    call(`/api/review/changes/${action}`, body).then(() => { if (action === "accept") setDone((x) => x + 1); load(); }, (e) => alert(e.message));
  };
  const groups = {};
  (items || []).forEach((p) => { (groups[p.kind] = groups[p.kind] || []).push(p); });
  return (
    <div className="pl-panel" role="dialog" aria-label="Changes from the news">
      <div className="pl-h">
        <b>Changes from the news</b>
        <span className="pl-dim">new or different facts articles state; nothing changes until you accept</span>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ marginLeft: "auto" }}>
          <option value="pending">Waiting for a decision</option><option value="accepted">Accepted</option><option value="rejected">Rejected</option><option value="all">All</option>
        </select>
        {done ? <button type="button" onClick={() => window.location.reload()}>Reload to see {done} accepted change{done > 1 ? "s" : ""} as NEW</button> : null}
        <button type="button" onClick={onClose}>Close</button>
      </div>
      {err ? <p className="pl-err">{err}</p> : null}
      <div style={{ overflow: "auto", flex: 1 }}>
        {!items ? <p className="pl-dim">Loading…</p> : !items.length ? <p className="pl-dim">Nothing here.</p> : Object.entries(groups).map(([kind, list]) => (
          <div key={kind}>
            <div className="pl-sec">{KIND[kind] || kind} ({list.length})</div>
            {list.map((p) => (
              <div className="pl-rec" key={p.proposal_id} style={{ display: "grid", gridTemplateColumns: "minmax(160px,1fr) minmax(220px,2fr) minmax(220px,2fr) auto", gap: "4px 14px" }}>
                <div><b>{p.competitor || "—"}</b><div className="pl-dim">{p.subject}{p.field ? ` · ${p.field}` : ""}</div></div>
                <div>
                  <div className="pl-dim">We hold</div>
                  <div>{p.current_value || (p.target_id ? "—" : "nothing yet: this is new")}</div>
                </div>
                <div>
                  <div className="pl-dim">The article says{p.effective_date ? ` (from ${String(p.effective_date).slice(0, 10)})` : ""}</div>
                  {p.status === "pending" ? (
                    <input value={edit[p.proposal_id] ?? p.proposed_value} onChange={(e) => setEdit({ ...edit, [p.proposal_id]: e.target.value })}
                           style={{ width: "100%", background: "#101013", color: "#e8e8e6", border: "1px solid #3a3a40", padding: "3px 6px" }} />
                  ) : <div>{p.proposed_value}{p.unit ? ` ${p.unit}` : ""}</div>}
                  <div className="pl-dim" style={{ marginTop: 3 }}>“{p.quote}” · <a href={p.article_url} target="_blank" rel="noreferrer">article{p.article_date ? ` ${String(p.article_date).slice(0, 10)}` : ""}</a></div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {p.status === "pending" ? (
                    <>
                      <button type="button" onClick={() => decide(p, "accept")} title="Write it into the review data; it then shows as NEW / CHANGED for the usual Approve">Accept</button>
                      <button type="button" onClick={() => decide(p, "reject")} title="Keep it out; the same fact is not proposed again">Reject</button>
                    </>
                  ) : <span className={`pl-st ${p.status === "accepted" ? "ok" : "failed"}`}>{p.status}</span>}
                  {p.decided_by || p.decided_at ? <span className="pl-dim">{p.decided_by || ""} {String(p.decided_at || "").slice(0, 16).replace("T", " ")}</span> : null}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
