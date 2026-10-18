import { describe, expect, it } from "vitest";
import { highlight, parseBlocks, parseInline, queryTerms } from "./answer";

describe("parseInline", () => {
  it("splits citations and bold text", () => {
    expect(parseInline("Return within **30 days** [1][2].")).toEqual([
      { kind: "text", text: "Return within " },
      { kind: "bold", text: "30 days" },
      { kind: "text", text: " " },
      { kind: "cite", ref: 1 },
      { kind: "cite", ref: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("never produces markup: html stays plain text", () => {
    const parts = parseInline("<img src=x onerror=alert(1)> [3]");
    expect(parts[0]).toEqual({ kind: "text", text: "<img src=x onerror=alert(1)> " });
  });
});

describe("parseBlocks", () => {
  it("groups paragraphs and lists", () => {
    const blocks = parseBlocks("Intro line\ncontinues here.\n\n- one\n- two\n\n1. first\n2. second");
    expect(blocks).toEqual([
      { kind: "p", text: "Intro line continues here." },
      { kind: "ul", items: ["one", "two"] },
      { kind: "ol", items: ["first", "second"] },
    ]);
  });

  it("does not treat **bold** at line start as a list", () => {
    expect(parseBlocks("**Note:** careful")).toEqual([{ kind: "p", text: "**Note:** careful" }]);
  });

  it("handles empty input", () => {
    expect(parseBlocks("")).toEqual([]);
  });
});

describe("highlight", () => {
  it("marks words from the question, ignoring stopwords and plurals", () => {
    const terms = queryTerms("What is the refund policy for returns?");
    const hits = highlight("Customers may return products. Refund policy applies.", terms)
      .filter((s) => s.hit)
      .map((s) => s.text.toLowerCase());
    expect(hits).toEqual(["return", "refund", "policy"]);
    expect(terms.has("return")).toBe(true);
  });

  it("keeps the original text intact", () => {
    const text = "Hello, world 42!";
    const joined = highlight(text, new Set(["world"])).map((s) => s.text).join("");
    expect(joined).toBe(text);
  });
});
