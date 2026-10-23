import json
from datetime import datetime, timezone
from pathlib import Path


def _pct(r: dict | None) -> str:
    return "n/a" if not r or r["value"] is None else f"{r['value'] * 100:.0f}%"


def _ci(r: dict) -> str:
    return "n/a" if r["value"] is None else f"{r['ci'][0] * 100:.0f}-{r['ci'][1] * 100:.0f}%"


def _count(r: dict) -> str:
    return f"{r['k']}/{r['n']}"


def _lat(value) -> str:
    return "n/a" if value is None else ("<0.05" if value < 0.05 else f"{value:.1f}")


def _num(value, fmt="{:.1f}") -> str:
    return "n/a" if value is None else fmt.format(value)


def render_markdown(meta: dict, summary: dict, scored: list[dict], results: list[dict]) -> str:
    title = f"{meta['system']} ({meta['provider']} / {meta['model']})" if meta["system"] == "agentops" else meta["system"]
    cfg = meta["config"]
    lines = [
        f"# Evaluation report: {title}",
        "",
        f"- Dataset: `{meta['dataset']['name']}` (sha256 `{meta['dataset']['sha256'][:12]}`), "
        f"{summary['n_questions']} questions run",
        f"- Date (UTC): {meta['timestamp']}",
        f"- Settings: chunk {cfg['chunk_size']}/{cfg['overlap']}, top_k {cfg['top_k']}, "
        f"min coverage {cfg['min_coverage']}" + (f", answer tokens {cfg['max_answer_tokens']}" if "max_answer_tokens" in cfg else ""),
        f"- Answers reused from cache: {meta['cached']} of {summary['n_questions']}",
    ]
    if summary["n_errors"]:
        lines.append(
            f"- **Errors (excluded from every rate below): {summary['n_errors']}** {summary['error_kinds']}. "
            "Re-run to retry them (errors are not cached)."
        )
    lines += [
        "",
        "## Results",
        "",
        "| Metric | Value | 95% interval | Count |",
        "|---|---|---|---|",
    ]
    rows = [
        ("Answerable accuracy (every required fact present)", "answerable_accuracy"),
        ("False abstention rate (answerable questions it refused)", "false_abstention_rate"),
        ("Abstention recall (unanswerable questions it refused)", "abstention_recall"),
        ("Unsupported answer rate (unanswerable questions it answered anyway)", "unsupported_answer_rate"),
        ("Abstention precision (refusals that were right)", "abstention_precision"),
        ("Decision accuracy (answered the answerable, refused the rest)", "decision_accuracy"),
        ("Citation points at the gold passage", "citation_gold_rate"),
    ]
    for label, key in rows:
        r = summary[key]
        lines.append(f"| {label} | {_pct(r)} | {_ci(r)} | {_count(r)} |")
    lines += [
        "",
        f"- Mean fact recall on answerable questions: {_num(summary['fact_recall_mean'] and summary['fact_recall_mean'] * 100, '{:.0f}')}%",
        f"- Latency per question: p50 {_lat(summary['latency_p50_s'])} s, p95 {_lat(summary['latency_p95_s'])} s",
        f"- Model calls per question: {_num(summary['llm_calls_mean'], '{:.2f}')}",
        f"- Mean support score of answered questions (the system's own check): {_num(summary['support_score_mean'], '{:.2f}')}",
        "",
        "## By question type (share handled correctly)",
        "",
        "| Type | Correct | 95% interval | Count |",
        "|---|---|---|---|",
    ]
    names = {"direct": "Direct", "paraphrase": "Paraphrase", "off_topic": "Off-topic", "near_miss": "Near-miss"}
    for t, r in summary["by_type"].items():
        lines.append(f"| {names[t]} | {_pct(r)} | {_ci(r)} | {_count(r)} |")

    if summary["failures"]:
        lines += ["", "## Where it went wrong", "", "| Id | Type | What happened | Question |", "|---|---|---|---|"]
        what = {
            "incorrect": "answered, missing a required fact",
            "false_abstention": "refused an answerable question",
            "unsupported_answer": "answered an unanswerable question",
            "error": "provider error (excluded)",
        }
        for f in summary["failures"][:25]:
            lines.append(f"| {f['id']} | {f['type']} | {what.get(f['status'], f['status'])} | {f['question']} |")
    lines += [
        "",
        "Caveats: the keyword fact check is a proxy for correctness (a right answer worded unexpectedly "
        "is counted wrong, and a wrong answer containing the right words is counted right); the questions "
        "were written by the project author; intervals are wide because the test set is small.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(out_dir: Path, slug: str, meta: dict, summary: dict, scored: list[dict], results: list[dict]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"{stamp}-{slug}"
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    json_path.write_text(
        json.dumps({"meta": meta, "summary": summary, "questions": scored, "results": results}, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(meta, summary, scored, results), encoding="utf-8")
    return json_path, md_path


def compare_markdown(reports: list[dict]) -> str:
    """Side-by-side table of several report.json files."""
    def label(rep: dict) -> str:
        m = rep["meta"]
        return m.get("label") or (f"{m['provider']} / {m['model']}" if m["system"] == "agentops" else m["system"])

    heads = [label(r) for r in reports]
    lines = [
        "# Comparison",
        "",
        "| Metric | " + " | ".join(heads) + " |",
        "|---|" + "---|" * len(heads),
    ]
    rows = [
        ("Answerable accuracy", "answerable_accuracy"),
        ("False abstention rate (lower is better)", "false_abstention_rate"),
        ("Abstention recall", "abstention_recall"),
        ("Abstention precision", "abstention_precision"),
        ("Decision accuracy", "decision_accuracy"),
        ("Citation points at gold passage", "citation_gold_rate"),
    ]
    for name, key in rows:
        cells = [f"{_pct(r['summary'][key])} ({_count(r['summary'][key])})" for r in reports]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("| Latency p50 / p95 (s) | " + " | ".join(
        f"{_lat(r['summary']['latency_p50_s'])} / {_lat(r['summary']['latency_p95_s'])}" for r in reports) + " |")
    lines.append("| Model calls per question | " + " | ".join(_num(r["summary"]["llm_calls_mean"], "{:.2f}") for r in reports) + " |")
    lines.append("| Errors (excluded) | " + " | ".join(str(r["summary"]["n_errors"]) for r in reports) + " |")
    lines += ["", "All runs use the same dataset only if the sha256 values match: "
              + ", ".join(f"`{r['meta']['dataset']['sha256'][:12]}`" for r in reports) + "."]
    return "\n".join(lines) + "\n"
