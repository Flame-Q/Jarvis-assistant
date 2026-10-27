"""Domain-level errors with a single root for easier handling."""

from __future__ import annotations


class JarvisError(Exception):
    """Base class for all expected application errors."""


class ConfigError(JarvisError):
    """Invalid or unsupported configuration."""


class ProviderError(JarvisError):
    """Speech, LLM or network provider failed."""


class OllamaUnavailable(ProviderError):
    """Local Ollama service is not reachable."""


class SkillError(JarvisError):
    """A skill could not execute the requested action."""


class InvalidTransition(JarvisError):
    """State machine transition is not allowed."""
