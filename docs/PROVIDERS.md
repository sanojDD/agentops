# Model providers

AgentOps can talk to four free-tier model providers through one client: **OpenRouter** (default), **Groq**, **Google Gemini** and **Mistral**. Pick a primary, optionally list backups, and the app switches between them for you.

All four speak the same chat-completions protocol, so there is one implementation (`providers/openai_compat.py`) and a small registry (`providers/registry.py`). `providers/llm.py` holds the single function the rest of the app calls, `complete()`.

## Setup

| Provider | Key variable | Model variable (default) | Where to get a key |
|---|---|---|---|
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` (`google/gemma-4-26b-a4b-it:free`) | openrouter.ai, Keys |
| Groq | `GROQ_API_KEY` | `GROQ_MODEL` (`llama-3.3-70b-versatile`) | console.groq.com, API Keys |
| Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` (`gemini-2.5-flash`) | aistudio.google.com, Get API key |
| Mistral | `MISTRAL_API_KEY` | `MISTRAL_MODEL` (`mistral-small-latest`) | console.mistral.ai, API keys |

Free tiers, model names and rate limits change and can disappear; check each provider's current limits page before relying on one, and treat the default model names as starting points (the self-check below tells you whether a name exists). Each provider also has `<NAME>_BASE_URL` (defaults to the official endpoint; Gemini uses Google's OpenAI-compatible endpoint).

Keys go in `.env` locally and in the API service's Environment on Render. They are never committed, logged, returned by the API, or printed by the self-check.

## Switching and backups

```text
LLM_PROVIDER=openrouter                  # primary
LLM_FALLBACK_PROVIDERS=groq,gemini       # tried in this order if the primary fails
```
- To switch, change `LLM_PROVIDER` and redeploy; nothing else changes.
- A provider named in the chain without an API key is skipped, so you can prepare the config before getting every key.
- A typo in a provider name stops the server at startup with a message listing the valid names.
- To see what is configured without exposing keys: `GET /api/v1/llm/providers` (owner token).

### When a backup is used

| What happened to the primary | Failover? | Why |
|---|---|---|
| Rate limit (429) | yes | Another provider has its own quota |
| Timeout, 5xx, network error | yes | Another provider may be healthy |
| Token starvation (empty answer, see below) | yes | A different model may answer |
| Bad key / no credits (401, 402, 403) | no | A configuration problem; hiding it would leave you with a broken primary and no warning |
| Unknown model or bad request (400, 404, 422) | no | Same reason |

If every provider in the chain fails with a failover-eligible error, the API returns `503` "All configured model providers failed". If only one provider is configured it keeps its own, more specific error (for example `429`). Timeouts: `LLM_TIMEOUT_SECONDS` (45) per attempt and `LLM_TOTAL_TIMEOUT_SECONDS` (100) across all attempts of one call.

The provider that actually answered is in the server log (`chat_run` has a `provider` field) and the LangSmith trace (`llm_complete`).

## The token starvation bug (empty answers) and its fix

**Symptom:** a reasoning model (for example `nvidia/nemotron-3.5-lightning:free`) returned an empty answer, so verification rejected it, the agent retried, and the question ended in the fallback message.

**Cause:** reasoning models "think" before answering, and those hidden reasoning tokens are counted against `max_tokens`. With budgets of 512 (answers) and 96 (query rewrites) the thinking used everything, the response ended with `finish_reason: "length"`, and `content` was an empty string.

**Fixes (all in this release):**

1. **Bigger budgets.** `MAX_ANSWER_TOKENS` is now 2048 and `MAX_REWRITE_TOKENS` is 512. Both are environment variables, so you can tune them without code changes.
2. **Optional reasoning control.** Set a reasoning effort per provider and the app sends it with every request:

   | Variable | Sent as | Typical values |
   |---|---|---|
   | `OPENROUTER_REASONING_EFFORT` | `"reasoning": {"effort": ...}` | `none`, `low`, `medium`, `high` |
   | `GROQ_REASONING_EFFORT` | `"reasoning_effort": ...` | model dependent (some models accept `none`, gpt-oss models `low`/`medium`/`high`) |
   | `GEMINI_REASONING_EFFORT` | `"reasoning_effort": ...` | `none`, `low`, `medium`, `high` |
   | Mistral | no equivalent parameter | not sent |

   Leave it empty and nothing is sent. Some models cannot switch reasoning off and answer `400` if you ask; then rely on the budget instead.
3. **A clear error instead of a silent empty answer.** If a model still returns nothing because it ran out of tokens, the API reports `token_budget` ("The model used its whole output budget before writing an answer. Increase MAX_ANSWER_TOKENS or set a reasoning effort"), logs `llm_token_budget` with the reasoning token count, and tries a backup provider if one is configured. The web page shows "Out of tokens" with the same advice.

Longer budgets can mean slower answers on reasoning models; `LLM_TIMEOUT_SECONDS` is 45 by default for that reason.

## Self-check (run this after adding or changing a key)

From `backend/`, with the virtual environment active and your `.env` filled in:

```powershell
python -m app.tools.check_providers                                   # every provider that has a key
python -m app.tools.check_providers --provider groq                   # one provider
python -m app.tools.check_providers --provider openrouter --starvation-test
```

For each provider it checks: the key is accepted, the configured model exists in the provider's list, and a real request returns a non-empty answer (with latency, finish reason and reasoning tokens). With `--starvation-test` it replays one realistic answer request three ways (old 96-token budget, new budget, new budget with reasoning off) and says whether starvation reproduces and whether the fix works for your model. The exit code is 0 only if everything checked passed. Output looks like this (this example was produced against a local stand-in for a reasoning model; yours will show your real provider and numbers):

```text
Provider chain: openrouter
Output budgets: answer=2048, rewrite=512

openrouter: model=nvidia/nemotron-3.5-lightning:free  reasoning_effort=(not sent)
  PASS  model 'nvidia/nemotron-3.5-lightning:free' is available (1 models listed)
  PASS  answered in 23 ms, finish=stop, reasoning_tokens=200, reply='...'
  starvation test (same request, different settings):
  STARVED old budget (96 tokens), reasoning not controlled: no answer written
  OK    new budget (2048 tokens), reasoning not controlled: 47 characters, reasoning_tokens=200
  OK    new budget (2048 tokens), reasoning effort 'none': 47 characters, reasoning_tokens=0
  PASS  starvation reproduced at 96 tokens and fixed by the larger budget
```

The same checks are available on a running server (owner token): `POST /api/v1/llm/check?provider=groq` and `GET /api/v1/llm/providers`.

## What is verified, and how

The automated tests use local servers that imitate the four providers, including a reasoning model that returns an empty answer when its budget is too small. They check the exact request each provider receives (path, `Authorization` header, model, token budget, reasoning parameter), the starvation bug and every fix, every failover rule above, key redaction, the new endpoints and the self-check tool, plus the whole graph answering through a starving model. They cannot confirm that your real keys, model names and free-tier limits work today: that is what the self-check is for.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Self-check: `FAIL auth` | Wrong or revoked key, or no credits. Create a new key and update `.env` and Render |
| `WARN model ... is not in the provider's model list` | Misspelled or retired model name; pick one from the provider's model list |
| `FAIL bad_request` on Gemini | Gemini reports an invalid API key as a 400; check the key first |
| `token_budget` errors | Raise `MAX_ANSWER_TOKENS`, set the provider's `*_REASONING_EFFORT`, or choose a non-reasoning model |
| `400` after setting a reasoning effort | That model does not accept the parameter; unset it |
| Server will not start: "LLM_PROVIDER must be one of" | Typo in `LLM_PROVIDER` or `LLM_FALLBACK_PROVIDERS` |
| Answers come from the backup unexpectedly | The primary is rate limited or slow; see the `provider_failover` log lines |
| `503 No model provider is configured` | No key is set for any provider in the chain |
