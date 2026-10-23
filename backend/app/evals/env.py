import os

from dotenv import load_dotenv

from app.core.config import ENV_PATH


def isolate(trace: bool = False) -> None:
    """Make an evaluation run harmless to your real data.

    - The database is switched off: evaluation documents are never written to
      your Neon/PostgreSQL database and your own documents are never read.
    - LangSmith tracing is off unless you pass --trace (it would otherwise
      fill your project with evaluation runs).
    """
    import app.db.session as session_mod
    from app.retrieval.store import get_store

    session_mod.get_database_url = lambda: None
    session_mod.reset_engine()
    get_store.cache_clear()

    if trace:
        load_dotenv(ENV_PATH)  # LangSmith reads its settings from os.environ
    else:
        os.environ["LANGSMITH_TRACING"] = "false"
