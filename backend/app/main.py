import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from app.core.config import ENV_PATH, get_settings

# LangSmith reads its settings from os.environ, not from our Settings class.
# Load .env into the environment BEFORE importing anything that uses LangSmith.
# On Render there is no .env file; real environment variables are used instead.
load_dotenv(ENV_PATH)

from fastapi import FastAPI, Request  # noqa: E402

from app.api.v1 import chat, documents, health, llm, runs  # noqa: E402
from app.core.cors import add_cors, parse_origins  # noqa: E402
from app.core.logging import configure_logging, request_id_var  # noqa: E402
from app.db.session import db_enabled  # noqa: E402
from app.retrieval.store import warm_up_store  # noqa: E402

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("agentops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load documents from the database in the background so the server starts
    # listening immediately (Neon may need a few seconds to wake up).
    if db_enabled():
        app.state.warmup = asyncio.create_task(asyncio.to_thread(warm_up_store))
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex  # always generated server-side
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request",
        extra={
            "fields": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        },
    )
    request_id_var.reset(token)
    return response


# Added after request_context so CORS is the outermost layer: even error
# responses (401, 503) carry the headers the browser needs to read them.
add_cors(app, parse_origins(settings.cors_origins))

app.include_router(health.router)
app.include_router(llm.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
