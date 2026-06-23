from unittest.mock import patch

import pytest

from src.core.llm_client import LLMClient, LLMConfig, get_llm_client

# Ensure groq is importable for patching
try:
    import groq
except ImportError as e:
    print(f"Failed to import groq: {e}")
    groq = None


class TestLLMClient:
    def test_groq_initialization(self):
        """Test initialization for Groq provider."""
        if groq is None:
            pytest.skip("Groq SDK not installed")

        config = LLMConfig(
            provider="groq",
            model="llama3-70b-8192",
            api_key="test-key",
            base_url="https://api.groq.com/openai/v1",
        )

        # Patch groq.Groq directly since it is imported inside __init__
        with patch("groq.Groq") as mock_groq:
            client = LLMClient(config)

            # Verify Groq client was initialized
            mock_groq.assert_called_once()
            _, kwargs = mock_groq.call_args
            assert kwargs["api_key"] == "test-key"
            # Groq SDK should be initialized WITHOUT base_url (uses its own default)
            assert "base_url" not in kwargs

            # Verify internal client is set
            assert client._client == mock_groq.return_value

    def test_openrouter_initialization(self):
        """Test initialization for OpenRouter provider with extra headers."""
        config = LLMConfig(
            provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
        )

        with patch("src.core.llm_client.OpenAI") as mock_openai:
            LLMClient(config)

            # Verify OpenAI client was initialized with extra headers
            mock_openai.assert_called_once()
            _, kwargs = mock_openai.call_args
            assert kwargs["default_headers"] == {
                "HTTP-Referer": "https://open-assistant.org",
                "X-Title": "Open Assistant",
            }

    def test_sanitize_messages(self):
        """Test message sanitization logic."""
        config = LLMConfig(
            provider="openrouter", model="anthropic/claude-3.5-sonnet", api_key="test-key"
        )

        with patch("src.core.llm_client.OpenAI"):
            client = LLMClient(config)

            # Case 1: Normal messages
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
            sanitized = client._sanitize_messages(messages)
            # The last message is assistant, so it should be changed to user for compatibility
            assert sanitized[0]["role"] == "user"
            assert sanitized[-1]["role"] == "user"

            # Case 2: Last message is user (no change)
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
                {"role": "user", "content": "How are you?"},
            ]
            sanitized = client._sanitize_messages(messages)
            assert sanitized[-1]["role"] == "user"
            assert sanitized[1]["role"] == "assistant"

    def test_groq_sanitize_messages(self):
        """Test Groq-specific message sanitization removes unsupported fields."""
        if groq is None:
            pytest.skip("Groq SDK not installed")

        config = LLMConfig(provider="groq", model="llama3", api_key="test-key")

        with patch("groq.Groq"):
            client = LLMClient(config)

            # Messages with unsupported fields for Groq
            messages = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Hi there",
                    "annotations": [{"type": "test"}],
                    "audio": {"id": "123"},
                    "executed_tools": [{"tool": "web_search", "result": "test"}],
                    "function_call": None,  # Null function_call should be removed
                    "tool_calls": [],  # Empty tool_calls should be removed
                },
            ]
            sanitized = client._sanitize_messages(messages)

            # Verify unsupported fields are removed
            assert "annotations" not in sanitized[1]
            assert "audio" not in sanitized[1]
            assert "executed_tools" not in sanitized[1]
            assert "function_call" not in sanitized[1]
            assert "tool_calls" not in sanitized[1]
            # But content should remain
            assert sanitized[1]["content"] == "Hi there"

            # Test that valid tool_calls are preserved
            messages_with_tool_calls = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": "{}"},
                        }
                    ],
                },
            ]
            sanitized = client._sanitize_messages(messages_with_tool_calls)
            assert "tool_calls" in sanitized[1]
            assert len(sanitized[1]["tool_calls"]) == 1

            # Test that function_call is removed when null/empty but kept when valid
            messages_with_function_call = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Using function",
                    "function_call": None,  # Should be removed
                },
            ]
            sanitized = client._sanitize_messages(messages_with_function_call)
            assert "function_call" not in sanitized[1]
            # But content should remain
            assert sanitized[1]["content"] == "Using function"

            # Test with valid function_call - should be kept
            messages_with_valid_function_call = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Using function",
                    "function_call": {"name": "test", "arguments": "{}"},
                },
            ]
            sanitized = client._sanitize_messages(messages_with_valid_function_call)
            # function_call should be kept when it has valid content
            assert "function_call" in sanitized[1]

    def test_ollama_initialization(self):
        """Test Ollama uses the OpenAI SDK path with the local base URL."""
        config = LLMConfig(
            provider="ollama",
            model="llama3.1",
            api_key="",
            base_url="http://localhost:11434/v1",
        )

        with patch("src.core.llm_client.OpenAI") as mock_openai:
            client = LLMClient(config)

            # Ollama uses the OpenAI-compatible client, not the Groq SDK
            mock_openai.assert_called_once()
            _, kwargs = mock_openai.call_args
            assert kwargs["base_url"] == "http://localhost:11434/v1"
            # No extra headers for Ollama
            assert kwargs.get("default_headers") is None

    def test_ollama_empty_api_key(self):
        """Test that LLMConfig accepts an empty api_key for Ollama."""
        # Should not raise — api_key is no longer a required field
        config = LLMConfig(provider="ollama", model="llama3.1", api_key="")
        assert config.api_key == ""

    def test_ollama_no_api_key_defaults(self):
        """Test that LLMConfig can be created without api_key for Ollama."""
        # api_key defaults to "" when omitted
        config = LLMConfig(provider="ollama", model="llama3.1")
        assert config.api_key == ""

    def test_ollama_default_base_url(self):
        """Test that get_default_base_url returns the Ollama local endpoint."""
        from src.core.llm_client import get_default_base_url

        assert get_default_base_url("ollama") == "http://localhost:11434/v1"

    def test_ollama_sanitize_messages(self):
        """Test that Ollama gets the same field sanitization as Groq."""
        config = LLMConfig(provider="ollama", model="llama3.1", api_key="")

        with patch("src.core.llm_client.OpenAI"):
            client = LLMClient(config)

            messages = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Hi",
                    "annotations": [{"type": "test"}],
                    "audio": {"id": "123"},
                    "executed_tools": [{"tool": "search"}],
                    "function_call": None,
                    "tool_calls": [],
                },
            ]
            sanitized = client._sanitize_messages(messages)

            assert "annotations" not in sanitized[1]
            assert "audio" not in sanitized[1]
            assert "executed_tools" not in sanitized[1]
            assert "function_call" not in sanitized[1]
            assert "tool_calls" not in sanitized[1]
            assert sanitized[1]["content"] == "Hi"

            # Valid tool_calls must be preserved
            messages_with_tools = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
            ]
            sanitized = client._sanitize_messages(messages_with_tools)
            assert "tool_calls" in sanitized[1]
            assert len(sanitized[1]["tool_calls"]) == 1

    def test_vllm_initialization(self):
        """Test vLLM uses the OpenAI SDK path with the local base URL."""
        config = LLMConfig(
            provider="vllm",
            model="mistralai/Mistral-7B-Instruct-v0.2",
            api_key="",
            base_url="http://localhost:8000/v1",
        )

        with patch("src.core.llm_client.OpenAI") as mock_openai:
            client = LLMClient(config)

            # vLLM uses the OpenAI-compatible client, not the Groq SDK
            mock_openai.assert_called_once()
            _, kwargs = mock_openai.call_args
            assert kwargs["base_url"] == "http://localhost:8000/v1"
            # No extra headers for vLLM (those are OpenRouter-only)
            assert kwargs.get("default_headers") is None

    def test_vllm_empty_api_key(self):
        """Test that LLMConfig accepts an empty api_key for vLLM."""
        config = LLMConfig(provider="vllm", model="my-model", api_key="")
        assert config.api_key == ""

    def test_vllm_default_base_url(self):
        """Test that get_default_base_url returns the vLLM local endpoint."""
        from src.core.llm_client import get_default_base_url

        assert get_default_base_url("vllm") == "http://localhost:8000/v1"

    def test_vllm_sanitize_messages(self):
        """Test that vLLM gets the same field sanitization as Groq/Ollama."""
        config = LLMConfig(provider="vllm", model="my-model", api_key="")

        with patch("src.core.llm_client.OpenAI"):
            client = LLMClient(config)

            messages = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Hi",
                    "annotations": [{"type": "test"}],
                    "audio": {"id": "123"},
                    "executed_tools": [{"tool": "search"}],
                    "function_call": None,
                    "tool_calls": [],
                },
            ]
            sanitized = client._sanitize_messages(messages)

            assert "annotations" not in sanitized[1]
            assert "audio" not in sanitized[1]
            assert "executed_tools" not in sanitized[1]
            assert "function_call" not in sanitized[1]
            assert "tool_calls" not in sanitized[1]
            assert sanitized[1]["content"] == "Hi"

    def test_single_model_providers_ignore_aux_models(self):
        """Ollama and vLLM always use the main model for aux roles.

        Even when media/worker/writer models are explicitly configured, these
        single-model providers must fall back to the main model.
        """
        for provider in ("ollama", "vllm"):
            config = LLMConfig(
                provider=provider,
                model="main-model",
                api_key="",
                media_model="other-media",
                worker_model="other-worker",
                writer_model="other-writer",
            )
            assert config.get_media_model() == "main-model"
            assert config.get_worker_model() == "main-model"
            assert config.get_writer_model() == "main-model"

    def test_hosted_providers_respect_aux_models(self):
        """Hosted providers still honour explicit aux model overrides."""
        config = LLMConfig(
            provider="openrouter",
            model="main-model",
            api_key="test-key",
            media_model="other-media",
            worker_model="other-worker",
            writer_model="other-writer",
        )
        assert config.get_media_model() == "other-media"
        assert config.get_worker_model() == "other-worker"
        assert config.get_writer_model() == "other-writer"

    def test_aux_models_fall_back_when_unset(self):
        """All providers fall back to the main model when aux models are unset."""
        config = LLMConfig(provider="openrouter", model="main-model", api_key="test-key")
        assert config.get_media_model() == "main-model"
        assert config.get_worker_model() == "main-model"
        assert config.get_writer_model() == "main-model"

    def test_factory_function(self):
        """Test the get_llm_client factory function."""
        # Use groq here to verify default URL
        if groq is None:
            pytest.skip("Groq SDK not installed")

        # Need to patch Groq here too because get_llm_client calls LLMClient()
        with patch("groq.Groq") as mock_groq:
            client = get_llm_client(api_key="test-key", provider="groq", model="llama3")

            # Verify Groq was initialized with correct config
            mock_groq.assert_called_once()
            _, kwargs = mock_groq.call_args

            # Groq should be initialized without explicit base_url
            assert "base_url" not in kwargs
            assert client.config.provider == "groq"
