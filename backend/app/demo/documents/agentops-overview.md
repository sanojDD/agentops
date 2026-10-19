# AgentOps overview

AgentOps is a document question-answering system that shows its work. You upload documents, ask a question, and get an answer with numbered citations that point at the passages it used, together with a record of every step the agent took.

## How a question is answered

Each question runs through a LangGraph workflow with five steps: validate, retrieve, generate, verify and, if needed, fallback. Validate rejects empty questions. Retrieve searches the document chunks with a keyword ranking method called BM25 and keeps the passages that share enough words with the question. Generate sends those passages to a language model and asks it to answer only from them and to cite them as [1], [2] and so on. Verify checks the answer before it is returned.

## How an answer is checked

The verify step does not call a second model. It checks that the answer is not empty, that every citation points to a passage that was actually retrieved, and that at least half of the content words in the answer appear in the retrieved passages. An answer that fails these checks is rejected.

## When the documents do not contain the answer

If no passage matches, or the answer fails verification, the agent retries once. It asks the model to rewrite the question as a keyword search, searches again with a wider net, and tries to answer again. If the second attempt also fails, AgentOps returns a plain message saying it could not find a supported answer instead of guessing. The agent makes at most two retrieval attempts per question.

## Errors and retries

Only temporary provider problems, such as timeouts and server errors, are retried automatically. A rate limit is never retried, because retrying would waste the free quota. Each question uses at most three answer calls to the language model.

## What it is built with

The backend is written in Python with FastAPI and LangGraph. Documents, text chunks and the history of every run are stored in PostgreSQL hosted on Neon. Every run is traced in LangSmith, and the run ID shown with each answer is the same ID used in the trace. The web interface is written in React and TypeScript. The language model is a free model served through OpenRouter.

## How it is hosted for free

The backend runs on a Render free web service, which goes to sleep after fifteen minutes without traffic and needs about a minute to wake up. The web interface is a Render static site. The database is the free plan of Neon, which also sleeps when idle. Because the hosting is free, the demo has daily limits on how many questions can be asked.

## Known limits

Search is keyword based, so it can miss answers that use different words than the question. The answer check is lexical, so a fluent answer that reuses words from a document with a different meaning could pass. These limits are known and are the starting point for the evaluation work. Each question is answered on its own, without memory of earlier questions.
