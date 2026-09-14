from .gemini import GeminiProvider

# Stub providers
class OpenAIProvider:
    provider_id = "openai"
class AnthropicProvider:
    provider_id = "anthropic"
class GroqProvider:
    provider_id = "groq"
class MLXLocalProvider:
    provider_id = "mlx_local"
class OllamaProvider:
    provider_id = "ollama"

PROVIDER_REGISTRY = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
    "mlx_local": MLXLocalProvider,
    "ollama": OllamaProvider
}

def get_provider(provider_id: str):
    provider_cls = PROVIDER_REGISTRY.get(provider_id)
    if not provider_cls:
        raise ValueError(f"Unknown provider: {provider_id}")
    return provider_cls()
