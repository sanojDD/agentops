import logging
import time
import uuid

from dotenv import load_dotenv

from app.core.config import ENV_PATH, get_settings

# LangSmith reads its settings from os.environ, not from our Settings class.
# Load .env into the environment BEFORE importing anything that uses LangSmith.
# On Render there is no .env file; real environment variables are used instead.
load_dotenv(ENV_PATH)

from fastapi import FastAPI, Request  # noqa: E402

from app.api.v1 import health, llm  # noqa: E402
from app.core.logging import configure_logging, request_id_var  # noqa: E402

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("agentops")

app = FastAPI(title=settings.app_name, version=settings.app_version)


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


app.include_router(health.router)
app.include_router(llm.router, prefix="/api/v1")
