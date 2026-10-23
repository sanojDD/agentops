"""Command line: python -m app.evals <validate | retrieval | run | compare>."""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import PROVIDER_NAMES, get_settings
from app.evals.dataset import DEFAULT_DATASET, REPO_ROOT, load_dataset, validate
from app.evals.env import isolate
from app.evals.experiments import render_markdown as render_experiments
from app.evals.experiments import run_grid
from app.evals.report import compare_markdown, render_markdown, write_reports
from app.evals.retrieval import RetrievalConfig, build_store, fill_store
from app.evals.runner import ResultCache, overrides, run_system, summarize
from app.evals.systems import AgentOpsSystem, ExtractiveSystem
from app.providers.registry import spec_for

DEFAULT_OUT = REPO_ROOT / "evals" / "reports"
CACHE_DIR = REPO_ROOT / "evals" / "cache"


def _load(path: str | None):
    ds = load_dataset(path or DEFAULT_DATASET)
    problems = validate(ds)
    if problems:
        print("The dataset has problems:")
        for p in problems:
            print("  -", p)
        return None
    return ds


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def cmd_validate(args) -> int:
    ds = load_dataset(args.dataset or DEFAULT_DATASET)
    problems = validate(ds)
    if problems:
        print(f"{len(problems)} problem(s) in dataset '{ds.name}':")
        for p in problems:
            print("  -", p)
        return 1
    answerable = sum(q.answerable for q in ds.questions)
    types: dict[str, int] = {}
    for q in ds.questions:
        types[q.type] = types.get(q.type, 0) + 1
    print(
        f"Dataset '{ds.name}' is valid: {len(ds.documents)} documents, {len(ds.questions)} questions "
        f"({answerable} answerable, {len(ds.questions) - answerable} not). By type: {types}. sha256 {ds.sha256[:12]}"
    )
    return 0


def cmd_retrieval(args) -> int:
    isolate()
    ds = _load(args.dataset)
    if ds is None:
        return 1
    results = run_grid(ds)
    markdown = render_experiments(ds, results)
    out = Path(args.out) if args.out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    (out / f"{stamp}-retrieval.md").write_text(markdown, encoding="utf-8")
    (out / f"{stamp}-retrieval.json").write_text(
        json.dumps({"dataset": {"name": ds.name, "sha256": ds.sha256}, "results": results}, indent=2),
        encoding="utf-8",
    )
    print(markdown)
    print(f"Saved to {out / (stamp + '-retrieval.md')}")
    return 0


def _agentops_config(settings, cfg: RetrievalConfig, provider: str) -> dict:
    from app.graph.nodes import ANSWER_PROMPT, REWRITE_PROMPT

    return {
        "system": "agentops",
        "provider": provider,
        "model": getattr(settings, f"{provider}_model"),
        "reasoning_effort": getattr(settings, f"{provider}_reasoning_effort", ""),
        "gemini_mode": settings.gemini_mode if provider == "gemini" else "",
        "max_answer_tokens": settings.max_answer_tokens,
        "max_rewrite_tokens": settings.max_rewrite_tokens,
        "chunk_size": cfg.chunk_size,
        "overlap": cfg.overlap,
        "top_k": cfg.top_k,
        "min_coverage": cfg.min_coverage,
        "min_support": settings.rag_min_support,
        "prompt": hashlib.sha256((ANSWER_PROMPT + REWRITE_PROMPT).encode()).hexdigest()[:12],
    }


def _progress(i, n, q, score, result, cached) -> None:
    mark = {
        "correct": "PASS", "correct_abstention": "PASS", "incorrect": "FAIL",
        "false_abstention": "FAIL", "unsupported_answer": "FAIL", "error": "ERR ",
    }[score["status"]]
    suffix = "  (from cache)" if cached else ""
    print(f"[{i:>2}/{n}] {q.id:<4} {q.type:<10} {mark}  {result.latency_s:5.1f}s  {score['status']}{suffix}", flush=True)


async def _run(args) -> int:
    isolate(trace=args.trace)
    ds = _load(args.dataset)
    if ds is None:
        return 2
    settings = get_settings()
    cfg = RetrievalConfig(
        "current",
        chunk_size=args.chunk_size or settings.chunk_size,
        overlap=args.chunk_overlap or settings.chunk_overlap,
        top_k=args.top_k or settings.rag_top_k,
        min_coverage=settings.rag_min_coverage if args.min_coverage is None else args.min_coverage,
    )
    out = Path(args.out) if args.out else DEFAULT_OUT

    if args.system == "extractive":
        store = build_store(ds, cfg)
        system = ExtractiveSystem(store, cfg)
        config = {"system": "extractive", "chunk_size": cfg.chunk_size, "overlap": cfg.overlap, "top_k": cfg.top_k, "min_coverage": cfg.min_coverage}
        provider, model = "none", "extractive"
        cache = ResultCache(None)  # free and instant: no cache needed
        run_cfg = config
        return await _execute(args, ds, system, store, config, provider, model, run_cfg, cache, out, None)

    provider = args.provider or settings.llm_provider
    if provider not in PROVIDER_NAMES:
        print(f"Unknown provider '{provider}'. Use one of: {', '.join(PROVIDER_NAMES)}")
        return 2
    if not spec_for(settings, provider).configured:
        print(f"No API key for '{provider}'. Set {provider.upper()}_API_KEY in .env (see docs/PROVIDERS.md).")
        return 2

    values = {
        "llm_provider": provider,
        "llm_fallback_providers": settings.llm_fallback_providers if args.with_fallbacks else "",
        "rag_top_k": cfg.top_k,
        "rag_min_coverage": cfg.min_coverage,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.overlap,
        "max_documents": 10_000,
        "max_total_chunks": 10**9,
    }
    if args.model:
        values[f"{provider}_model"] = args.model
    from app.retrieval.store import get_store

    with overrides(settings, **values):
        get_store.cache_clear()
        store = fill_store(get_store(), ds, cfg)
        model = getattr(settings, f"{provider}_model")
        config = _agentops_config(settings, cfg, provider)
        cache = ResultCache(None if args.no_cache else CACHE_DIR / f"agentops-{provider}.jsonl")
        n = len(ds.questions) if not args.limit else min(args.limit, len(ds.questions))
        print(f"Evaluating agentops with {provider} / {model} on {n} questions (up to ~{n * 2} model calls; "
              f"answers already in the cache are not re-requested).")
        return await _execute(args, ds, AgentOpsSystem(provider), store, config, provider, model, config, cache, out, None)


async def _execute(args, ds, system, store, config, provider, model, run_cfg, cache, out, _unused) -> int:
    scored, results, cached = await run_system(
        system, ds, store, config=config, limit=args.limit, delay=args.delay, cache=cache, on_progress=_progress
    )
    summary = summarize(scored, results)
    meta = {
        "system": system.name,
        "provider": provider,
        "model": model,
        "label": args.label or "",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "dataset": {"name": ds.name, "sha256": ds.sha256, "n_questions": len(ds.questions)},
        "config": run_cfg,
        "cached": cached,
        "limit": args.limit,
    }
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{system.name}-{provider}-{model}").strip("-")[:60]
    json_path, md_path = write_reports(out, slug, meta, summary, scored, [r.to_dict() for r in results])
    print()
    print(render_markdown(meta, summary, scored, [r.to_dict() for r in results]))
    print(f"Saved: {md_path}\n       {json_path}")
    return 0


def cmd_compare(args) -> int:
    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
    markdown = compare_markdown(reports)
    print(markdown)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"Saved to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evals", description="Evaluate the AgentOps RAG pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="check the dataset for typos and inconsistencies")
    v.add_argument("--dataset")

    r = sub.add_parser("retrieval", help="compare retrieval settings (no model calls)")
    r.add_argument("--dataset")
    r.add_argument("--out", help="folder for the report (default: evals/reports)")

    e = sub.add_parser("run", help="answer every question and score the answers")
    e.add_argument("--system", choices=["extractive", "agentops"], default="agentops")
    e.add_argument("--provider", choices=PROVIDER_NAMES, help="model provider for the agentops system")
    e.add_argument("--model", help="override the provider's model name")
    e.add_argument("--with-fallbacks", action="store_true", help="allow backup providers (off by default so a run measures one model)")
    e.add_argument("--limit", type=int, help="only the first N questions (spread across all types)")
    e.add_argument("--delay", type=float, default=0.0, help="seconds to wait between questions (use 3-5 on free tiers)")
    e.add_argument("--no-cache", action="store_true", help="ignore and do not write cached answers")
    e.add_argument("--trace", action="store_true", help="send runs to LangSmith (off by default)")
    e.add_argument("--label", help="a name for this run in comparisons")
    e.add_argument("--chunk-size", type=int)
    e.add_argument("--chunk-overlap", type=int)
    e.add_argument("--top-k", type=int)
    e.add_argument("--min-coverage", type=float)
    e.add_argument("--dataset")
    e.add_argument("--out", help="folder for the reports (default: evals/reports)")

    c = sub.add_parser("compare", help="side-by-side table of saved reports (.json)")
    c.add_argument("reports", nargs="+")
    c.add_argument("--out")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "retrieval":
        return cmd_retrieval(args)
    if args.command == "run":
        return asyncio.run(_run(args))
    return cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
