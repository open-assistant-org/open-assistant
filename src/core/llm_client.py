"""LLM client for API calls through OpenRouter or other providers."""

import logging
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default base URLs for each provider
PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
}

# Providers that serve a single local model per endpoint. For these, the
# auxiliary roles (media/worker/writer) always reuse the main model because the
# server can't swap models per-request the way a hosted gateway can.
SINGLE_MODEL_PROVIDERS = {"ollama", "vllm"}


def get_default_base_url(provider: str) -> str:
    """
    Get the default base URL for a given provider.

    Args:
        provider: LLM provider name

    Returns:
        Default base URL for the provider
    """
    return PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["openrouter"])


class LLMConfig(BaseModel):
    """Configuration for LLM client."""

    provider: str = Field(
        default="openrouter", description="LLM provider (openrouter, groq, ollama, vllm, custom)"
    )
    model: str = Field(default="anthropic/claude-3.5-sonnet", description="Model identifier")
    api_key: str = Field(
        default="", description="API key for the provider (not required for Ollama)"
    )
    base_url: str | None = Field(
        default="https://openrouter.ai/api/v1", description="Base URL for API requests"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=4096, gt=0, description="Maximum tokens in response")
    media_model: str | None = Field(
        default=None,
        description="Model for processing non-textual media (images, etc.). Defaults to main model.",
    )
    worker_model: str | None = Field(
        default=None,
        description="Model for background worker tasks. Defaults to main model.",
    )
    writer_model: str | None = Field(
        default=None,
        description="Model for document composition tasks. Defaults to main model.",
    )

    def get_media_model(self) -> str:
        """Return the media model, falling back to the main model.

        Single-model providers (Ollama, vLLM) always reuse the main model.
        """
        if self.provider in SINGLE_MODEL_PROVIDERS:
            return self.model
        return self.media_model or self.model

    def get_worker_model(self) -> str:
        """Return the worker model, falling back to the main model.

        Single-model providers (Ollama, vLLM) always reuse the main model.
        """
        if self.provider in SINGLE_MODEL_PROVIDERS:
            return self.model
        return self.worker_model or self.model

    def get_writer_model(self) -> str:
        """Return the writer model, falling back to the main model.

        Single-model providers (Ollama, vLLM) always reuse the main model.
        """
        if self.provider in SINGLE_MODEL_PROVIDERS:
            return self.model
        return self.writer_model or self.model

    @classmethod
    def from_settings(cls, settings_service, **overrides) -> "LLMConfig":
        """Build an LLMConfig from a settings_service.

        Fetches all LLM settings and normalises empty strings to ``None``
        for optional fields.  Callers can pass ``**overrides`` to replace
        specific values (e.g. ``temperature=0.0`` for the classifier).
        """
        provider = settings_service.get_config_with_fallback("llm.provider", "openrouter")
        kwargs = {
            "api_key": settings_service.get_config_with_fallback("llm.api_key"),
            "provider": provider,
            "model": settings_service.get_config_with_fallback(
                "llm.model", "anthropic/claude-sonnet-4.6"
            ),
            "base_url": settings_service.get_config_with_fallback(
                "llm.base_url", get_default_base_url(provider)
            ),
            "temperature": float(settings_service.get_config_with_fallback("llm.temperature", 0.7)),
            "max_tokens": int(settings_service.get_config_with_fallback("llm.max_tokens", 4096)),
        }
        for key in ("media_model", "worker_model", "writer_model"):
            value = settings_service.get_config_with_fallback(f"llm.{key}", "")
            kwargs[key] = value or None
        kwargs.update(overrides)
        return cls(**kwargs)


class LLMClient:
    """
    Client for making LLM API calls.

    Supports OpenRouter, Groq, and other OpenAI-compatible APIs.
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config

        if config.provider == "groq":
            try:
                from groq import Groq
            except ImportError as e:
                raise ImportError("Groq SDK not installed. Run: uv add groq") from e

            # Groq SDK handles its own base URL - don't pass base_url to avoid path duplication
            self._client = Groq(api_key=config.api_key)
            logger.info(f"Initialized Groq LLM client for model: {config.model}")
        else:
            # Initialize OpenAI client (works with OpenRouter too)
            extra_headers = {}
            if config.provider == "openrouter":
                extra_headers["HTTP-Referer"] = "https://open-assistant.org"
                extra_headers["X-Title"] = "Open Assistant"

            self._client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                default_headers=extra_headers if extra_headers else None,
            )

            logger.info(
                f"Initialized OpenAI LLM client for provider: {config.provider}, model: {config.model}"
            )

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for provider compatibility.

        Handles edge cases for providers that don't allow ending with
        assistant/system role (e.g., Amazon Bedrock).

        For Groq: Removes unsupported fields (annotations, audio) that cause API errors.
        """
        if not messages:
            return messages

        sanitized = messages.copy()

        # Groq/Ollama/vLLM sanitization: remove non-standard fields that these
        # stricter OpenAI-compatible servers reject.
        if self.config.provider in ("groq", "ollama", "vllm"):
            unsupported_fields = {"annotations", "audio", "executed_tools"}
            # Remove function_call/tool_calls if null/empty, but keep valid values

            def is_nullish(v):
                """Check if value is null, empty, or string 'null'/'undefined'."""
                if v is None:
                    return True
                if isinstance(v, (list, dict, str)) and not v:
                    return True
                if isinstance(v, str) and v.lower() in ("null", "undefined", "none"):
                    return True
                return False

            result = []
            for msg in sanitized:
                # Remove unsupported fields entirely
                filtered_msg = {k: v for k, v in msg.items() if k not in unsupported_fields}
                # Remove function_call if null/empty
                if "function_call" in filtered_msg and is_nullish(filtered_msg["function_call"]):
                    del filtered_msg["function_call"]
                # Remove tool_calls if null/empty
                if "tool_calls" in filtered_msg and is_nullish(filtered_msg["tool_calls"]):
                    del filtered_msg["tool_calls"]
                # Only add non-empty messages
                if filtered_msg:
                    result.append(filtered_msg)
            sanitized = result

        # Handle last message role for providers that don't allow ending with assistant/system
        # (e.g., Amazon Bedrock)
        last = sanitized[-1]
        if last.get("role") in ("assistant", "system"):
            sanitized[-1] = {**last, "role": "user"}
            logger.debug(
                "Sanitized last message role from '%s' to 'user' for provider compatibility",
                last.get("role"),
            )

        return sanitized

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        model_override: str | None = None,
        **kwargs,
    ) -> Any:
        """
        Generate a completion from the LLM.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            stream: Whether to stream the response
            model_override: Override model (e.g. media model for images)
            **kwargs: Additional parameters to pass to the API

        Returns:
            API response object
        """
        try:
            messages = self._sanitize_messages(messages)
            response = self._client.chat.completions.create(
                model=model_override or self.config.model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                stream=stream,
                **kwargs,
            )
            return response
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise

    def _is_groq_tool_use_failed(self, e: Exception) -> bool:
        """Check if an exception is a Groq tool_use_failed error."""
        try:
            from groq import BadRequestError

            return (
                isinstance(e, BadRequestError)
                and isinstance(e.body, dict)
                and e.body.get("error", {}).get("code") == "tool_use_failed"
            )
        except ImportError:
            return False

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tool_choice: str = "auto",
        model_override: str | None = None,
    ) -> Any:
        """
        Generate completion with tool/function calling support.

        Args:
            messages: Conversation messages
            tools: List of tool definitions in OpenAI format
            temperature: Sampling temperature
            max_tokens: Max tokens in response
            tool_choice: "auto", "none", or {"type": "function", "function": {"name": "..."}}
            model_override: Override model (e.g. media model for images)

        Returns:
            API response with potential tool_calls
        """
        try:
            messages = self._sanitize_messages(messages)
            response = self._client.chat.completions.create(
                model=model_override or self.config.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
            )
            return response
        except Exception as e:
            # Groq-specific: on tool_use_failed, retry once with a nudge to produce
            # valid tool calls. This avoids surfacing a raw API error to the user.
            if self.config.provider == "groq" and self._is_groq_tool_use_failed(e):
                logger.warning(
                    "Groq tool_use_failed error — retrying with a nudge to fix tool call format"
                )
                try:
                    nudged_messages = messages + [
                        {
                            "role": "user",
                            "content": (
                                "Your previous tool call could not be parsed. "
                                "Please try again using simple, valid JSON arguments."
                            ),
                        }
                    ]
                    return self._client.chat.completions.create(
                        model=model_override or self.config.model,
                        messages=nudged_messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        temperature=temperature or self.config.temperature,
                        max_tokens=max_tokens or self.config.max_tokens,
                    )
                except Exception as retry_e:
                    logger.error(f"Groq tool_use_failed retry also failed: {retry_e}")
                    raise retry_e
            logger.error(f"Error calling LLM API with tools: {e}")
            raise

    def complete_text(
        self,
        prompt: str,
        system_message: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_override: str | None = None,
    ) -> str:
        """
        Generate a text completion from a simple prompt.

        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            model_override: Override model identifier

        Returns:
            Generated text
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = self.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model_override=model_override,
        )

        return response.choices[0].message.content


def get_llm_client(
    api_key: str,
    provider: str = "openrouter",
    model: str = "anthropic/claude-sonnet-4.6",
    base_url: str | None = None,
    **kwargs,
) -> LLMClient:
    """
    Factory function to create an LLM client.

    Args:
        api_key: API key for the provider
        provider: LLM provider name
        model: Model identifier
        base_url: Optional base URL override (if None, uses provider default)
        **kwargs: Additional config parameters

    Returns:
        LLMClient instance
    """
    if base_url is None:
        base_url = get_default_base_url(provider)

    config = LLMConfig(provider=provider, model=model, api_key=api_key, base_url=base_url, **kwargs)

    return LLMClient(config)
