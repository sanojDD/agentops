// Turns model output into safe, structured pieces. Nothing here produces HTML:
// React renders the pieces as text, so document or model content cannot inject markup.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "cite"; ref: number };

export function parseInline(line: string): Inline[] {
  const out: Inline[] = [];
  for (const part of line.split(/(\*\*[^*\n]+\*\*|\[\d+\])/g)) {
    if (!part) continue;
    const cite = /^\[(\d+)\]$/.exec(part);
    if (cite) {
      out.push({ kind: "cite", ref: Number(cite[1]) });
    } else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      out.push({ kind: "bold", text: part.slice(2, -2) });
    } else {
      out.push({ kind: "text", text: part });
    }
  }
  return out;
}

export type Block =
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) {
      blocks.push({ kind: "p", text: paragraph.join(" ") });
      paragraph = [];
    }
  };

  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    const ul = /^[-*•]\s+(.*)$/.exec(line);
    const ol = /^\d+[.)]\s+(.*)$/.exec(line);
    if (ul || ol) {
      flush();
      const kind = ul ? "ul" : "ol";
      const item = (ul ?? ol)![1];
      const last = blocks[blocks.length - 1];
      if (last && last.kind === kind) last.items.push(item);
      else blocks.push({ kind, items: [item] });
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

// ---- highlighting the words of the question inside an evidence passage ----

const STOP = new Set(
  (
    "a an the and or but of to in on at for with by from as is are was were be been it its this " +
    "that these those what which who whom when where why how do does did can could should would " +
    "will i you he she we they me my our your their about into than then there if so not no any " +
    "some has have had"
  ).split(" "),
);

function stem(word: string): string {
  return word.length > 3 && word.endsWith("s") && !word.endsWith("ss") ? word.slice(0, -1) : word;
}

export function queryTerms(question: string): Set<string> {
  const words = question.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return new Set(words.filter((w) => w.length > 1 && !STOP.has(w)).map(stem));
}

export interface Segment {
  text: string;
  hit: boolean;
}

export function highlight(text: string, terms: Set<string>): Segment[] {
  return text
    .split(/([A-Za-z0-9]+)/)
    .filter((part) => part !== "")
    .map((part) => ({
      text: part,
      hit: /^[A-Za-z0-9]+$/.test(part) && terms.has(stem(part.toLowerCase())),
    }));
}
