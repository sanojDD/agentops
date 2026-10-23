"""Baseline-versus-variants retrieval experiments.

Method: same questions, same documents, change ONE setting at a time, compare
the numbers. The first row is the baseline (the app's current defaults)."""

from app.evals.dataset import Dataset
from app.evals.retrieval import RetrievalConfig, build_store, evaluate_retrieval

DEFAULT_GRID = [
    RetrievalConfig("baseline (current defaults)"),
    RetrievalConfig("smaller chunks (500/100)", chunk_size=500, overlap=100),
    RetrievalConfig("larger chunks (1500/200)", chunk_size=1500, overlap=200),
    RetrievalConfig("more chunks (top_k 8)", top_k=8),
    RetrievalConfig("lenient filter (min coverage 0.2)", min_coverage=0.2),
    RetrievalConfig("strict filter (min coverage 0.5)", min_coverage=0.5),
    RetrievalConfig("wide net (top_k 8, coverage 0.2)", top_k=8, min_coverage=0.2),
]


def run_grid(ds: Dataset, grid: list[RetrievalConfig] | None = None) -> list[dict]:
    results = []
    for cfg in grid or DEFAULT_GRID:
        store = build_store(ds, cfg)
        results.append(evaluate_retrieval(store, ds, cfg))
    return results


def pct(rate_dict: dict) -> str:
    return "n/a" if rate_dict["value"] is None else f"{rate_dict['value'] * 100:.0f}%"


def render_markdown(ds: Dataset, results: list[dict]) -> str:
    n_ans = results[0]["answerable"]["all"]["n"]
    n_un = results[0]["unanswerable"]["all"]["n"]
    lines = [
        "# Retrieval experiments",
        "",
        f"Dataset `{ds.name}` (sha256 `{ds.sha256[:12]}`): {n_ans} answerable and {n_un} unanswerable questions, "
        f"{len(ds.documents)} documents. No model is called; this measures search only.",
        "",
        "| Setting | Chunks | Hit@k direct | Hit@k paraphrase | Hit@k all | Ranking-only hit@k | MRR@10 | Gold recall | No evidence: off-topic | No evidence: near-miss |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        a, u = r["answerable"], r["unanswerable"]
        lines.append(
            f"| {r['config']['name']} | {r['n_chunks']} | {pct(a['direct']['system_hit'])} | "
            f"{pct(a['paraphrase']['system_hit'])} | {pct(a['all']['system_hit'])} | "
            f"{pct(a['all']['ranking_hit'])} | {a['all']['mrr']:.2f} | {a['all']['gold_recall'] * 100:.0f}% | "
            f"{pct(u['off_topic']['no_evidence_first'])} | {pct(u['near_miss']['no_evidence_first'])} |"
        )
    base = results[0]["answerable"]["all"]
    lines.append(
        f"| random chunks (same top_k) | {results[0]['n_chunks']} | | | {base['random_hit'] * 100:.0f}% | | | | | |"
    )
    lines += [
        "",
        "How to read it:",
        "- **Hit@k**: for answerable questions, the share where one of the top-k chunks contains the gold evidence. Higher is better.",
        "- **Ranking-only hit@k**: the same, without the coverage filter, so it shows how good the *ranking* is on its own.",
        "- **MRR@10**: mean of 1/rank of the first gold chunk (1.0 = always first). Higher is better.",
        "- **Gold recall**: share of the gold snippets found among the returned chunks.",
        "- **No evidence**: for unanswerable questions, the share where search correctly returns nothing. Higher is better, and it trades off against hit@k: a more lenient filter finds more answers and also more false evidence.",
        "- The random row shows what chance alone would score; anything near it means search is not working.",
        "- With only %d answerable questions, differences of a few points are noise (see the confidence intervals in the JSON report)." % n_ans,
    ]
    return "\n".join(lines) + "\n"
