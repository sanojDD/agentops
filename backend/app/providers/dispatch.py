from app.providers import gemini_native, openai_compat
from app.providers.registry import ProviderSpec


async def call(spec: ProviderSpec, prompt: str, **kwargs) -> dict:
    """Send one request using the right protocol for this provider."""
    if spec.api_style == "gemini_native":
        return await gemini_native.call(spec, prompt, **kwargs)
    return await openai_compat.call(spec, prompt, **kwargs)
