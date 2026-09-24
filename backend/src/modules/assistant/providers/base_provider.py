"""Shared Gemini assistant interface and exceptions."""

from abc import ABC, abstractmethod


class AssistantProviderError(Exception):
    """Base class for Gemini assistant failures."""


class ProviderNotConfiguredError(AssistantProviderError):
    """Raised when Gemini is missing required configuration."""


class ProviderConnectionError(AssistantProviderError):
    """Raised when Gemini cannot be reached."""


class ProviderRateLimitError(ProviderConnectionError):
    """Raised when Gemini rejects a request because of quota/rate limits."""


class ProviderResponseError(AssistantProviderError):
    """Raised when Gemini returns an unexpected response."""


class BaseProvider(ABC):
    """Small interface used by the Gemini adapter."""

    provider_name = "gemini"
    provider_type = "api"
    model = ""

    @abstractmethod
    def chat(self, message, system_prompt):
        raise NotImplementedError

    @abstractmethod
    def health(self):
        raise NotImplementedError

    def metadata(self):
        return {
            "provider": self.provider_name,
            "type": self.provider_type,
            "model": self.model,
        }
