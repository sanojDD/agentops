from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def parse_origins(raw: str) -> list[str]:
    """CORS_ORIGINS is a comma-separated list of exact origins, e.g.
    "https://agentops-web.onrender.com,http://localhost:5173"."""
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError(
            "CORS_ORIGINS must list explicit origins (for example "
            "https://agentops-web.onrender.com), not *"
        )
    return origins


def add_cors(app: FastAPI, origins: list[str]) -> None:
    """Allow only the listed browser origins. No cookies are used (the admin
    token travels in a header), so credentials stay disabled."""
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["X-Admin-Token", "X-Demo-Token", "Content-Type"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
