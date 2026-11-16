// Titles keep a little chemical markup: CsPbBr<sub>3</sub>, <i>in vivo</i>, 10<sup>-3</sup>
// (cleaned at ingestion by poc_feeds.clean_title). Render exactly these three tags as React elements;
// any other element becomes its plain text, so no other HTML (attributes, links, scripts) ever renders.
// The input is parsed by DOMParser into an inert document (no scripts run, no images load).
const ALLOWED = { SUB: "sub", SUP: "sup", I: "i" };

function convert(node, key) {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent.replace(/\s+/g, " ");
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  if (["SCRIPT", "STYLE", "TEMPLATE"].includes(node.tagName)) return null;   // never show their source
  const children = convertChildren(node);
  const tag = ALLOWED[node.tagName];
  return tag ? <Tag key={key} tag={tag}>{children}</Tag> : <span key={key}>{children}</span>;
}

function Tag({ tag: T, children }) {
  return <T>{children}</T>;
}

function convertChildren(node) {
  const out = [];
  node.childNodes.forEach((child, i) => {
    // "CsPbBr <sub>3</sub>": drop the stray space before a subscript/superscript
    const next = node.childNodes[i + 1];
    if (child.nodeType === Node.TEXT_NODE && next && ["SUB", "SUP"].includes(next.tagName)) {
      out.push(child.textContent.replace(/\s+/g, " ").replace(/ $/, ""));
      return;
    }
    out.push(convert(child, i));
  });
  return out;
}

export default function RichText({ html }) {
  if (!html) return null;
  if (!/[<&]/.test(html)) return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  return <>{convertChildren(doc.body)}</>;
}
