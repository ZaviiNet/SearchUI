"""
settings.py — LLM Provider Configuration Storage
Manages named provider configurations: known cloud APIs and custom local endpoints.
"""
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

KNOWN_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "api_style": "openai",
        "notes": "Requires an OpenAI API key from platform.openai.com"
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-haiku-20240307",
        "api_style": "anthropic",
        "notes": "Requires an Anthropic API key from console.anthropic.com"
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama3-8b-8192",
        "api_style": "openai",
        "notes": "Free tier available. Get key from console.groq.com"
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
        "api_style": "openai",
        "notes": "Unified gateway for many models. Get key from openrouter.ai"
    },
    "together": {
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3-8b-chat-hf",
        "api_style": "openai",
        "notes": "Fast inference. Get key from api.together.xyz"
    },
    "mistral": {
        "name": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "api_style": "openai",
        "notes": "European AI. Get key from console.mistral.ai"
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434",
        "default_model": "llama3",
        "api_style": "ollama",
        "notes": "No API key needed. Run 'ollama serve' locally."
    },
    "lmstudio": {
        "name": "LM Studio (Local)",
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "api_style": "openai",
        "notes": "No API key needed. Start the local server in LM Studio."
    },
    "custom": {
        "name": "Custom Endpoint",
        "base_url": "",
        "default_model": "",
        "api_style": "openai",
        "notes": "Any OpenAI-compatible endpoint."
    }
}


def _load() -> dict:
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"active_provider": None, "providers": {}}


def _save(data: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def list_providers() -> list:
    """Return all configured providers as a list."""
    data = _load()
    result = []
    for pid, cfg in data.get("providers", {}).items():
        result.append({"id": pid, **cfg})
    return result


def get_provider(provider_id: str):
    data = _load()
    return data.get("providers", {}).get(provider_id)


def set_provider(provider_id: str, config: dict):
    data = _load()
    if "providers" not in data:
        data["providers"] = {}
    data["providers"][provider_id] = config
    _save(data)


def delete_provider(provider_id: str):
    data = _load()
    data.get("providers", {}).pop(provider_id, None)
    if data.get("active_provider") == provider_id:
        data["active_provider"] = None
    _save(data)


def get_active_provider():
    data = _load()
    active_id = data.get("active_provider")
    if active_id:
        return data.get("providers", {}).get(active_id)
    return None


def set_active_provider(provider_id: str):
    data = _load()
    data["active_provider"] = provider_id
    _save(data)


def get_known_providers() -> dict:
    return KNOWN_PROVIDERS
