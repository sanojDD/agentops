# Evaluation data and reports

- `datasets/v1/` holds the evaluation dataset: `corpus/` (20 short documents about a fictional developer platform) and `questions.json` (44 questions with gold evidence and required facts).
- `reports/` holds saved results (`.md` to read, `.json` for the full per-question detail). The files here were produced by the commands in [docs/EVALUATION.md](../docs/EVALUATION.md).
- `cache/` (not committed) remembers model answers so a re-run does not spend free-tier quota.

Everything is run with `python -m app.evals ...` from `backend/`. Start with [docs/EVALUATION.md](../docs/EVALUATION.md): it explains every metric from scratch.
