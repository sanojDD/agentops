from dataclasses import dataclass, field

from app.core.config import PROVIDER_NAMES, Settings


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key: str | None
    model: str
    reasoning_effort: str  # "" means the parameter is not sent
    extra_headers: dict[str, str] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def spec_for(settings: Settings, name: str) -> ProviderSpec:
    secret = getattr(settings, f"{name}_api_key", None)
    key = secret.get_secret_value().strip() if secret is not None else ""
    
    # Safe model resolution with fallback to prevent null values
    model_val = getattr(settings, f"{name}_model", "") or ""
    if not model_val:
        model_defaults = {
            "gemini": "gemini-2.5-pro",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "google/gemma-4-26b-a4b-it:free",
            "mistral": "mistral-small-latest",
        }
        model_val = model_defaults.get(name, "")

    # Ensure Gemini OpenAI compatibility endpoint never gets the "models/" prefix
    if name == "gemini" and model_val.startswith("models/"):
        model_val = model_val.replace("models/", "")

    return ProviderSpec(
        name=name,
        base_url=getattr(settings, f"{name}_base_url", ""),
        api_key=key or None,
        model=model_val,
        reasoning_effort=getattr(settings, f"{name}_reasoning_effort", "").strip(),
        extra_headers={"X-Title": settings.app_name} if name == "openrouter" else {},
    )


def chain_names(settings: Settings) -> list[str]:
    """Primary first, then the fallbacks, without duplicates."""
    names = [settings.llm_provider] + [
        n for n in settings.llm_fallback_providers.split(",") if n
    ]
    return list(dict.fromkeys(names))


def all_specs(settings: Settings) -> list[ProviderSpec]:
    return [spec_for(settings, n) for n in PROVIDER_NAMES]


def usable_chain(settings: Settings) -> list[ProviderSpec]:
    """The providers to try, in order, skipping any without an API key."""
    return [s for s in (spec_for(settings, n) for n in chain_names(settings)) if s.configured]


def primary_model(settings: Settings) -> str:
    return getattr(settings, f"{settings.llm_provider}_model")
