/* Light markdown for model text: paragraphs, "- " bullets, **bold**, `code`.
   Built as React elements -- model output is never injected as HTML. */

function inline(text, keyBase) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<b key={`${keyBase}-${i++}`}>{tok.slice(2, -2)}</b>);
    else out.push(<code key={`${keyBase}-${i++}`}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function renderMarkdown(src) {
  const lines = String(src || "").replace(/\r/g, "").split("\n");
  const blocks = [];
  let para = [];
  let list = [];
  const flushPara = () => {
    if (para.length) blocks.push({ t: "p", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (list.length) blocks.push({ t: "ul", items: list });
    list = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (!line) {
      flushPara();
      flushList();
    } else if (bullet) {
      flushPara();
      list.push(bullet[1]);
    } else if (/^#{1,6}\s+/.test(line)) {
      flushPara();
      flushList();
      blocks.push({ t: "h", text: line.replace(/^#{1,6}\s+/, "") });
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return blocks.map((b, i) => {
    if (b.t === "ul")
      return (
        <ul key={i}>
          {b.items.map((it, j) => (
            <li key={j}>{inline(it, `${i}-${j}`)}</li>
          ))}
        </ul>
      );
    if (b.t === "h") return <p className="pa-md-h" key={i}>{inline(b.text, i)}</p>;
    return <p key={i}>{inline(b.text, i)}</p>;
  });
}
