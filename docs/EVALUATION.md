# Evaluation (Phase 7)

Unit tests tell you the code does what you wrote. **Evaluation tells you whether the system is any good at its job**: finding the right passage, answering correctly, and saying "not found" when it should. This page explains how it works from scratch, how to run it, and how to read and (honestly) report the results.

## The idea in one paragraph

Take a fixed set of documents and a fixed list of questions where *we know the right answer* (or know that the documents contain none). Run the system on every question, compare what it did with what it should have done, and count. Because the questions and documents never change, you can change one thing (a setting, a model, a prompt), run again, and see whether the numbers moved. That is an experiment, and it is how you can say "this change helped" with evidence.

## What is in the repository

```
evals/
  datasets/v1/
    corpus/*.md          20 short documents (fictional platform "Helio Cloud")
    questions.json       44 questions, with gold evidence and required facts
  reports/               saved results (.md to read, .json for every detail)
  cache/                 remembered model answers (not committed)
backend/app/evals/
  dataset.py             loads and validates the dataset
  metrics.py             every metric, a few lines each
  retrieval.py           retrieval-only evaluation (no model)
  experiments.py         baseline vs variants of the retrieval settings
  systems.py             the systems under test: the real workflow, and a no-model baseline
  runner.py              runs, scores, summarises, caches
  report.py, cli.py      reports and the command line
```

### The four kinds of question

| Type | Count | What it tests | Example |
|---|---|---|---|
| Direct | 16 | The question shares its words with the answer passage | "How long do refresh tokens last?" |
| Paraphrase | 8 | Same facts, different words: hard for keyword search | "Can a person who left the company still use the keys they made?" |
| Off-topic | 8 | Nothing in the documents is about it. The system should say "not found" | "What is the capital of Australia?" |
| Near-miss | 12 | Related to the documents, but the fact is not there. The hardest kind: the system sees relevant-looking text and must still refuse | "How do I install the Ruby SDK?" |

There are also 10 look-alike *distractor* documents (release notes, an FAQ, a glossary, a status-code list) so that search has real competition: with only 10 documents, even random picking would score 30%.

### What "right" means for a question

- **Gold evidence**: a snippet of text that must appear in a passage the system retrieves. Example: `costs 29 dollars per month per workspace`.
- **Facts**: what the answer must contain. Each fact lists acceptable wordings: `["3 times", "three times", "3 attempts"]`. The answer passes if **every** fact is found in **any** of its wordings.
- Unanswerable questions have neither: the right behaviour is to refuse.

## The metrics, one by one

### Retrieval (is the right passage found?)
No model is involved, so these cost nothing and run in a second.

| Metric | Plain meaning |
|---|---|
| **Hit@k** | For answerable questions: the share where one of the top *k* returned passages contains the gold evidence. Here *k* = 4. |
| **Ranking-only hit@k** | The same, but ignoring the coverage filter. It isolates how good the *ranking* is from how strict the *filter* is. |
| **MRR@10** | Mean reciprocal rank: if the gold passage is 1st you score 1, 2nd gives 0.5, 3rd 0.33, missing 0; then average. 1.0 means "always first". |
| **Gold recall** | Share of the gold snippets that appear among the returned passages. |
| **No evidence** | For unanswerable questions: the share where search returns nothing. Higher is better, but it fights with hit@k: a more lenient filter finds more real answers *and* more false evidence. |
| **Random baseline** | What picking *k* random passages would score. If search is not far above this, it is not working. |

### Answers (is the answer right?)

| Metric | Plain meaning |
|---|---|
| **Answerable accuracy** | Of the answerable questions, the share answered with every required fact present. |
| **Mean fact recall** | The same but partial credit: if 1 of 2 facts is present, that is 0.5. Refusals count as 0. |
| **Citation points at the gold passage** | Of the answers given, the share where at least one *cited* passage contains the gold evidence. This catches "right answer, wrong source". |

### Abstention (does it know when to say "not found"?)

Every question ends in one of four boxes:

| | The system answered | The system refused |
|---|---|---|
| **Answerable** | counted in accuracy (right or wrong) | **false abstention** (too cautious) |
| **Unanswerable** | **unsupported answer** (it made something up: the dangerous one) | **correct abstention** |

- **Abstention recall** = correct abstentions ÷ unanswerable questions. "Of the questions it should refuse, how many did it refuse?"
- **Unsupported answer rate** = 1 − abstention recall.
- **False abstention rate** = refusals ÷ answerable questions.
- **Abstention precision** = correct abstentions ÷ all refusals. "When it refuses, is it right?"
- **Decision accuracy** = (right answers + correct refusals) ÷ all questions: one headline number.

Always read abstention recall and false abstention rate **together**. A system that refuses everything scores 100% abstention recall and 0% accuracy; one that answers everything has 0% recall. Good means both are healthy.

### Cost and speed
Latency (median and 95th percentile) and **model calls per question** (one answer call per attempt, plus one rewrite per extra search). On free tiers, calls are the real budget.

### Baselines: what you compare against
A number means little alone. Two baselines are built in:
- **Random retrieval**: the floor for search quality.
- **Extractive system**: no language model at all. It copies the single best-matching sentence from the retrieved passages, or says "not found". If the real system cannot beat this on accuracy and abstention, the model is not earning its keep.

### Confidence intervals: why 17/24 is not "71%"
With 24 questions, one question changes the percentage by 4 points, so a small test set is *noisy*. Every rate in the reports comes with a 95% interval (Wilson). Rule of thumb: **if two systems' intervals overlap heavily, you cannot claim one is better.** Differences of a few points on 44 questions are noise.

### Reproducibility
Each report records the dataset's sha256 fingerprint, all settings (model, chunking, thresholds, token budgets, a hash of the prompts), and the date. Model calls use temperature 0, but providers can still vary slightly, so run twice before trusting a small difference. The answer cache is keyed on all of the above, so a changed model, prompt or setting never reuses old answers.

## How to run it (Windows PowerShell, from `backend/`, virtual environment active)

All evaluation commands switch the database and LangSmith tracing **off** by default, so they never touch your Neon database or fill your traces.

```powershell
# 1. Check the dataset for typos (instant, free)
python -m app.evals validate

# 2. Retrieval experiments: baseline vs 6 variants vs random (instant, free, no keys)
python -m app.evals retrieval

# 3. The no-model baseline over all 44 questions (instant, free, no keys)
python -m app.evals run --system extractive

# 4. The real system with a model (uses your free quota)
python -m app.evals run --system agentops --provider groq --limit 8 --delay 4
```

Step 4 notes:
- `--limit 8` runs a quick sample (spread across all four question types). Drop it for all 44.
- `--delay 4` waits 4 seconds between questions to stay under free-tier request-per-minute limits.
- Expect roughly 1 to 2 model calls per question, up to 4 on a hard one. Check your provider's current free limits first (see [PROVIDERS.md](PROVIDERS.md)).
- Errors such as rate limits are **excluded** from the rates, listed in the report, and **not cached**, so run the same command again to retry just those questions.
- Answers are cached in `evals/cache/`, so re-running costs nothing for questions already answered with the same settings.
- Add `--model <name>` to try another model of the same provider, `--with-fallbacks` to allow backup providers (off by default so a run measures one model), `--trace` to send the run to LangSmith, `--label "groq-llama"` to name the run in comparisons.
- Experiment with settings for a run: `--top-k 6`, `--min-coverage 0.25`, `--chunk-size 500 --chunk-overlap 100`.

Compare saved runs side by side:

```powershell
python -m app.evals compare ..\evals\reports\<baseline>.json ..\evals\reports\<groq>.json ..\evals\reports\<openrouter>.json --out ..\evals\reports\comparison.md
```

Each run writes `evals/reports/<timestamp>-<system>-<provider>-<model>.md` and `.json`.

## Results shipped with the repository (no model needed)

Produced by `python -m app.evals retrieval` and `python -m app.evals run --system extractive` on dataset `agentops-eval-v1` (sha256 `42743f13aa59`). The model-based results depend on your keys and are not included: run step 4 and add your own table below.

### Retrieval experiments

| Setting | Chunks | Hit@k direct | Hit@k paraphrase | Hit@k all | MRR@10 | No evidence: off-topic | No evidence: near-miss |
|---|---|---|---|---|---|---|---|
| **baseline (current defaults)** | 24 | 100% | 88% | 96% | 0.85 | 100% | 8% |
| smaller chunks (500/100) | 45 | 100% | 62% | 88% | 0.84 | 100% | 17% |
| larger chunks (1500/200) | 20 | 100% | 88% | 96% | 0.87 | 100% | 0% |
| more chunks (top_k 8) | 24 | 100% | 88% | 96% | 0.85 | 100% | 8% |
| lenient filter (min coverage 0.2) | 24 | 100% | 88% | 96% | 0.85 | 88% | 0% |
| strict filter (min coverage 0.5) | 24 | 100% | 62% | 88% | 0.85 | 100% | 17% |
| random chunks (same top_k) | 24 | | | 17% | | | |

What this teaches:
- **Search works**: 96% against 17% for chance.
- **Paraphrases are the weak spot** (88%, and 62% with small chunks or a strict filter). Keyword search cannot match "hosting locations" to "data region". This is the measured case for embedding-based search.
- **`top_k` 8 changed nothing**: the coverage filter, not `k`, limits what comes back. Changing a setting that does nothing is worth knowing.
- **A lenient filter costs you**: coverage 0.2 let one off-topic question retrieve false evidence (100% to 88%) without finding more answers.
- **Near-miss questions nearly always retrieve evidence** (only 8% get "no evidence"): they share vocabulary with real passages. For these, refusing must happen *after* retrieval, in the answer and verification steps.
- With 24 answerable questions, differences like 96% vs 88% are **one or two questions**: noise-sized. Treat the large gaps (62% vs 88%) as signal and the small ones as unproven.

### Extractive baseline (no model), 44 questions

| Metric | Value | 95% interval | Count |
|---|---|---|---|
| Answerable accuracy | 62% | 43-79% | 15/24 |
| False abstention rate | 4% | 1-20% | 1/24 |
| Abstention recall | 45% | 26-66% | 9/20 |
| Unsupported answer rate | 55% | 34-74% | 11/20 |
| Decision accuracy | 55% | 40-68% | 24/44 |

By type: direct 81%, paraphrase 25%, off-topic 100%, near-miss 8%. A system with no language model handles the easy cases and fails exactly where you would expect: it answers 11 of 20 questions that the documents cannot answer. **This is the bar the real system must clear**, especially on near-miss questions.

### Your model results (fill in after step 4)

| System | Answerable accuracy | Abstention recall | False abstention | Decision accuracy | p50 latency | Calls/question |
|---|---|---|---|---|---|---|
| extractive baseline | 62% (15/24) | 45% (9/20) | 4% (1/24) | 55% (24/44) | <0.05 s | 0 |
| agentops, provider / model | | | | | | |
| agentops, provider / model | | | | | | |

## Reading your results: what to do next

| You see | It means | A sensible next step |
|---|---|---|
| Hit@k high but accuracy low | Search finds the passage; the model or prompt fails to use it | Look at the "Where it went wrong" list; adjust the prompt or model |
| Paraphrase hit rate low | Keyword search cannot bridge different wording | Embedding or hybrid retrieval (the next experiment) |
| Abstention recall low, especially near-miss | The system answers with related but unsupported text | Stricter verification (a model-based support check), stronger "refuse" instructions |
| False abstention high | Too cautious: the verifier or filter rejects good answers | Lower the support threshold or coverage; re-measure both abstention numbers |
| Accuracy equal to the extractive baseline | The model adds little here | Try another model, or question whether the model is needed for this data |
| Many errors | Rate limits or provider trouble | Re-run (errors are retried), add `--delay`, or use another provider |

**Change one thing at a time**, re-run on the same dataset, and compare with the `compare` command.

## Limits you should state openly

- **Small and synthetic.** 44 questions over a fictional corpus the project author wrote. Intervals are wide, and results do not transfer to other documents.
- **Same author wrote the data and the system.** That tends to flatter the system. Questions written by someone else, or drawn from real use, would be stronger.
- **Keyword fact check.** A correct answer worded unexpectedly counts as wrong; a wrong answer that contains the right words counts as right. It is a proxy, not a judge. (Model-based judging is the planned upgrade, and it needs its own validation.)
- **Tuning on the test set overfits.** If you adjust thresholds until the numbers look good on these 44 questions, the numbers no longer describe how the system behaves on new questions. Tune on some questions and report on the rest, or add new questions after tuning.
- **Free models vary** between runs and over time. Report the date and model name.
- Not a benchmark: it is a regression and comparison tool for this project.

## Reporting results honestly (for the README and your resume)

Good: state the numbers **with the sample size** and what you compared against.
- "Built an evaluation harness (20 documents, 44 questions incl. 12 near-miss traps) measuring retrieval hit@4, answer accuracy, and abstention recall with 95% confidence intervals."
- "Keyword retrieval reached 96% hit@4 vs 17% for random; on the 8 paraphrase questions it fell to 88%, motivating hybrid retrieval." (these two numbers are measured and shipped)
- After your run: "[model] answered [x/24] answerable questions correctly and correctly refused [y/20] unanswerable ones, versus [15/24] and [9/20] for a no-model baseline."

Avoid: percentages without counts, "state of the art", "99% accurate", or claims about real-world performance from a 44-question synthetic set.

## Adding or changing questions

1. Add a document to `evals/datasets/v1/corpus/` (a `.md` file) or a question to `questions.json`. For a *new version* of the dataset, copy the folder to `v2` and pass `--dataset`.
2. Answerable question: `type` is `direct` or `paraphrase`; `gold_evidence` is text copied exactly from a document; `facts` lists the facts the answer must contain, each with its acceptable wordings.
3. Unanswerable question: `type` is `off_topic` or `near_miss`; the information must be genuinely absent from **every** document (search the corpus for the key words before adding it), with no `gold_evidence` or `facts`.
4. Run `python -m app.evals validate`. It catches duplicate ids, evidence that is not in the corpus, wordings that appear nowhere, and mismatched types. The dataset's sha256 changes, so old cached answers are not reused.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `No API key for 'groq'` | Set `GROQ_API_KEY` in `.env`; run `python -m app.tools.check_providers --provider groq` |
| Report shows errors (rate_limited, timeout) | The provider throttled you. Re-run (only the failed questions are retried), add `--delay 5`, or use `--limit` |
| `The dataset has problems:` | Run `validate` and fix what it lists |
| Numbers differ slightly between runs | Provider variation. Run twice; ignore differences inside the confidence intervals |
| You changed a prompt or setting and results look identical | The cache only reuses answers for identical settings; if results are identical, the change had no effect (as with `top_k` above) |
| Want to see the model's actual answers | Open the run's `.json`: `results` holds every answer, `questions` every score |

## Command reference

| Command | Purpose | Cost |
|---|---|---|
| `python -m app.evals validate` | Check the dataset | free |
| `python -m app.evals retrieval` | Retrieval experiments vs random | free |
| `python -m app.evals run --system extractive` | No-model baseline | free |
| `python -m app.evals run --system agentops --provider P` | The real workflow with provider P | model calls |
| `python -m app.evals compare A.json B.json ...` | Side-by-side table | free |
