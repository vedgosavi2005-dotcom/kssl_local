/* The client this dataset describes. Set once from data.client at load; every
   on-screen mention of the client reads it from here. No default: with no
   client record the name is the empty string, never a stand-in. */
let current = null;

export function setClient(client) {
  current = client && typeof client === "object" ? client : null;
}

export function clientName() {
  return (current && current.name) || "";
}

export function clientShort() {
  return (current && (current.short || current.name)) || "";
}

/* "<client> · Product" -> "Product". The prefix is the client's own name or short name from the
   data; with no client record nothing is stripped. */
export function stripClientPrefix(label) {
  const s = String(label == null ? "" : label);
  const own = [clientShort(), clientName()].filter(Boolean).find(
    (n) => s.toLowerCase().startsWith(n.toLowerCase()) && /^\s*·/.test(s.slice(n.length)),
  );
  return own ? s.slice(own.length).replace(/^\s*·\s*/, "") : s;
}

/* The self-naming "<client> present" label some rows carry in place of a product name. It is the stored
   actLabel.bf when the dataset has one, else the client's own short or full name followed by "present". */
export function isPresenceLabel(label, actLabel) {
  const s = String(label == null ? "" : label).trim().toLowerCase();
  if (!s) return false;
  const stored = actLabel && actLabel.bf ? String(actLabel.bf).trim().toLowerCase() : "";
  return s === stored || [clientShort(), clientName()].filter(Boolean).some((n) => s === `${n.toLowerCase()} present`);
}
