"""Model-agnostic provider layer for DESK's orchestrator.

DESK owns engineering rules and state; a model is a replaceable component. Every provider speaks
one contract (base.ModelProvider) over stdlib urllib:

    openai_compat  OpenAI, xAI Grok, NVIDIA NIM, Ollama, llama.cpp, vLLM (preset data in catalog.py)
    anthropic      Anthropic Messages API
    gemini         Google Gemini generateContent
    prompt_tools   prompt-based tool calling for models without native tools

registry.py (registration, credentials, discovery), catalog.py (capability descriptors),
resilience.py (timeouts, bounded retry, fallback chain), accounting.py (tokens and cost),
allocation.py (task class -> model tier policy, independent verifier), bridge.py (adapters to
agent_loop and the L0-L4 router).

Software-tested with fixtures and a fake in-process provider; not validated against live
endpoints or on a live design.
"""
from desk.orchestrator.providers.base import (ChatRequest, ChatResponse, ModelProvider, ModelRoute, ProviderError,
                                              StreamEvent, ToolCall, Transport, Usage)
from desk.orchestrator.providers.catalog import PRESETS, ModelCatalog, ModelDescriptor, ProviderPreset
from desk.orchestrator.providers.registry import ModelProviderRegistry, get_provider_registry

__all__ = ["ChatRequest", "ChatResponse", "ModelProvider", "ModelRoute", "ProviderError", "StreamEvent", "ToolCall",
           "Transport", "Usage", "PRESETS", "ModelCatalog", "ModelDescriptor", "ProviderPreset",
           "ModelProviderRegistry", "get_provider_registry"]
