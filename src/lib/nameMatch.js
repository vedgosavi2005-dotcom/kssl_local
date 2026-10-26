/* A NAME search (owner 2026-10-25: the Products search finds a product or a company by its name only, never by text inside its
   specs or description): every typed word must start a word of the name, so "loc" finds LOCUST but not "Block 20". */
export function nameMatches(name, query) {
  const words = String(name || "").toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
  const typed = String(query || "").toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
  return typed.length > 0 && typed.every((t) => words.some((w) => w.startsWith(t)));
}
