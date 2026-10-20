"""Backward-compatible import path. The provider code now lives in app.providers.llm."""

from app.providers.base import ProviderError  # noqa: F401
from app.providers.llm import complete  # noqa: F401
