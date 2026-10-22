/* The agent service's HTTP API. Same origin: the gateway serves the product and
   /api/agent/* together. */

export async function getStatus() {
  const r = await fetch("/api/agent/status", { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export function forgetConversation(id) { // kept for callers that want a hard delete
  if (!id) return;
  fetch(`/api/agent/conversation/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
}

/* POST a message and read the server-sent events. onEvent gets each parsed event;
   resolves when the stream ends. `signal` aborts (the Stop button). */
export async function chat({ conversationId, message, page, signal, onEvent }) {
  const r = await fetch("/api/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ conversation_id: conversationId, message, page }),
    signal,
  });
  if (!r.ok || !r.body) {
    let detail = "";
    try {
      detail = (await r.json()).error || "";
    } catch (e) {
      /* not JSON */
    }
    throw new Error(detail || `the agent service answered ${r.status}`);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      const data = chunk
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (!data) continue; // keep-alive comment
      try {
        onEvent(JSON.parse(data));
      } catch (e) {
        /* a malformed event is skipped, not fatal */
      }
    }
  }
}

/* ---------------------------------------------------------------- history & saved views */

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${url} answered ${r.status}`);
  return r.json();
}

export const listConversations = () => getJSON("/api/agent/conversations").then((d) => d.conversations || []);
export const getConversation = (id) => getJSON(`/api/agent/conversations/${encodeURIComponent(id)}`);
export const listSavedViews = () => getJSON("/api/agent/views").then((d) => d.views || []);
export const getSavedView = (id) => getJSON(`/api/agent/views/${encodeURIComponent(id)}`);

export function deleteConversation(id) {
  return fetch(`/api/agent/conversation/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
}

export function deleteSavedView(id) {
  return fetch(`/api/agent/views/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
}

export function saveTranscript(id, title, messages) {
  if (!id) return Promise.resolve();
  return fetch(`/api/agent/conversations/${encodeURIComponent(id)}/transcript`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, messages }),
  }).catch(() => {});
}

export async function saveView(view, conversationId) {
  const r = await fetch(`/api/agent/views/${encodeURIComponent(view.id)}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, spec: view }),
  });
  if (!r.ok) throw new Error(`save answered ${r.status}`);
  return r.json();
}
