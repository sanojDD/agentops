# Evaluation report: extractive

- Dataset: `agentops-eval-v1` (sha256 `42743f13aa59`), 44 questions run
- Date (UTC): 2026-10-23 01:37
- Settings: chunk 900/150, top_k 4, min coverage 0.34
- Answers reused from cache: 0 of 44

## Results

| Metric | Value | 95% interval | Count |
|---|---|---|---|
| Answerable accuracy (every required fact present) | 62% | 43-79% | 15/24 |
| False abstention rate (answerable questions it refused) | 4% | 1-20% | 1/24 |
| Abstention recall (unanswerable questions it refused) | 45% | 26-66% | 9/20 |
| Unsupported answer rate (unanswerable questions it answered anyway) | 55% | 34-74% | 11/20 |
| Abstention precision (refusals that were right) | 90% | 60-98% | 9/10 |
| Decision accuracy (answered the answerable, refused the rest) | 55% | 40-68% | 24/44 |
| Citation points at the gold passage | 83% | 63-93% | 19/23 |

- Mean fact recall on answerable questions: 62%
- Latency per question: p50 <0.05 s, p95 <0.05 s
- Model calls per question: 0.00
- Mean support score of answered questions (the system's own check): n/a

## By question type (share handled correctly)

| Type | Correct | 95% interval | Count |
|---|---|---|---|
| Direct | 81% | 57-93% | 13/16 |
| Paraphrase | 25% | 7-59% | 2/8 |
| Off-topic | 100% | 68-100% | 8/8 |
| Near-miss | 8% | 1-35% | 1/12 |

## Where it went wrong

| Id | Type | What happened | Question |
|---|---|---|---|
| d05 | direct | answered, missing a required fact | What HTTP status does the API return when the rate limit is exceeded? |
| d12 | direct | answered, missing a required fact | On which day and time is scheduled maintenance performed? |
| d14 | direct | answered, missing a required fact | How many members can a Team workspace have? |
| p01 | paraphrase | answered, missing a required fact | What do I get if my 99.9% uptime guarantee is missed slightly? |
| p02 | paraphrase | refused an answerable question | How soon do I need to ask for compensation after an outage? |
| p03 | paraphrase | answered, missing a required fact | If I stop paying, what happens to my projects? |
| p04 | paraphrase | answered, missing a required fact | Can a person who left the company still use the keys they made? |
| p05 | paraphrase | answered, missing a required fact | Which hosting locations are offered for customer data? |
| p07 | paraphrase | answered, missing a required fact | What do I do if my server answers slowly to Helio's event notifications? |
| n01 | near_miss | answered an unanswerable question | How do I install the Ruby SDK? |
| n02 | near_miss | answered an unanswerable question | What is the refund policy for hardware purchases? |
| n03 | near_miss | answered an unanswerable question | How many days of log retention does the Starter plan have? |
| n04 | near_miss | answered an unanswerable question | Which payment methods does Helio accept in India? |
| n05 | near_miss | answered an unanswerable question | What is the maximum number of projects on the Enterprise plan? |
| n07 | near_miss | answered an unanswerable question | What is the webhook timeout in the sandbox environment? |
| n08 | near_miss | answered an unanswerable question | Does Helio support GraphQL? |
| n09 | near_miss | answered an unanswerable question | Who founded Helio Cloud and in what year? |
| n10 | near_miss | answered an unanswerable question | Which languages is the dashboard available in? |
| n11 | near_miss | answered an unanswerable question | Is there a student discount? |
| n12 | near_miss | answered an unanswerable question | How many API keys can a workspace have? |

Caveats: the keyword fact check is a proxy for correctness (a right answer worded unexpectedly is counted wrong, and a wrong answer containing the right words is counted right); the questions were written by the project author; intervals are wide because the test set is small.
