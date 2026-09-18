"""
virtual_lab.ai.providers
──────────────────────────
Provider registry for VirtualLab AI workbench.

Only GeminiProvider is implemented. All other providers explicitly declare
themselves unavailable via UnavailableProvider. They will:
  • return False from test_connection()
  • raise ProviderUnavailableError from complete()
  • appear correctly greyed-out in the AIWorkbench settings dialog

Never silently return a fake success.
"""
from .gemini import GeminiProvider
from .mlx_local import MLXLocalProvider


class ProviderUnavailableError(RuntimeError):
    """Raised when an unimplemented provider is invoked."""


class UnavailableProvider:
    """
    Sentinel for providers that have no implementation in this build.
    Satisfies the IntelligenceProvider protocol interface but always
    signals its unavailability rather than silently returning fake data.
    """

    def __init__(self, provider_id: str, display_name: str = ""):
        self.provider_id = provider_id
        self._display_name = display_name or provider_id

    def models(self) -> list:
        return []

    def test_connection(self) -> bool:
        return False

    def supports_structured_output(self) -> bool:
        return False

    def is_configured(self) -> bool:
        return False

    def complete(self, request):
        raise ProviderUnavailableError(
            f"Provider '{self._display_name}' is not implemented in this build. "
            "Only Gemini is currently available."
        )

    def generate_proposal(self, prompt: str, context: dict) -> tuple:
        raise ProviderUnavailableError(
            f"Provider '{self._display_name}' is not implemented in this build."
        )


# ── Provider Registry ─────────────────────────────────────────────────────────

PROVIDER_REGISTRY = {
    "gemini":    GeminiProvider,
    "mlx_local": MLXLocalProvider,
    "openai":    lambda: UnavailableProvider("openai",     "OpenAI"),
    "anthropic": lambda: UnavailableProvider("anthropic",  "Anthropic"),
    "groq":      lambda: UnavailableProvider("groq",       "Groq"),
    "ollama":    lambda: UnavailableProvider("ollama",     "Ollama"),
}

IMPLEMENTED_PROVIDERS = {"gemini", "mlx_local"}


def get_provider(provider_id: str):
    factory = PROVIDER_REGISTRY.get(provider_id)
    if not factory:
        raise ValueError(f"Unknown provider: '{provider_id}'")
    return factory() if callable(factory) and provider_id not in IMPLEMENTED_PROVIDERS else factory()


def list_providers() -> list[dict]:
    """Return all providers with their implementation status."""
    return [
        {
            "id": pid,
            "implemented": pid in IMPLEMENTED_PROVIDERS,
            "display_name": {
                "gemini": "Gemini (Google)",
                "openai": "OpenAI",
                "anthropic": "Anthropic",
                "groq": "Groq",
                "mlx_local": "MLX Local (Apple Silicon)",
                "ollama": "Ollama (Local)",
            }.get(pid, pid),
        }
        for pid in PROVIDER_REGISTRY
    ]
