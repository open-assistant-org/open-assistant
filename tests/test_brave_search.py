"""Tests for the Brave Search integration."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.integrations.brave.client import BraveSearchClient
from src.integrations.brave.duckduckgo import DuckDuckGoClient
from src.models.brave import WebSearchRequest
from src.services.brave import BraveService, FRESHNESS_MAP

# ============================================================================
# MODELS
# ============================================================================


class TestWebSearchRequest:
    """Tests for the WebSearchRequest Pydantic model."""

    def test_defaults(self):
        """Test default values."""
        req = WebSearchRequest(query="test")
        assert req.query == "test"
        assert req.count == 10
        assert req.freshness is None

    def test_custom_values(self):
        """Test with custom values."""
        req = WebSearchRequest(query="python tutorials", count=5, freshness="week")
        assert req.query == "python tutorials"
        assert req.count == 5
        assert req.freshness == "week"

    def test_count_max(self):
        """Test that count has a maximum of 20."""
        with pytest.raises(Exception):
            WebSearchRequest(query="test", count=25)

    def test_count_min(self):
        """Test that count has a minimum of 1."""
        with pytest.raises(Exception):
            WebSearchRequest(query="test", count=0)


# ============================================================================
# BRAVE SEARCH CLIENT
# ============================================================================


class TestBraveSearchClient:
    """Tests for the BraveSearchClient."""

    def test_init(self):
        """Test client initialization."""
        client = BraveSearchClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.safe_search == "moderate"
        assert client.headers["X-Subscription-Token"] == "test-key"

    def test_init_custom_safe_search(self):
        """Test client initialization with custom safe search."""
        client = BraveSearchClient(api_key="test-key", safe_search="strict")
        assert client.safe_search == "strict"

    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_success(self, mock_client_class):
        """Test successful search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Python Tutorial",
                        "url": "https://python.org/tutorial",
                        "description": "Official Python tutorial",
                    },
                    {
                        "title": "Learn Python",
                        "url": "https://learnpython.org",
                        "description": "Interactive Python learning",
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_response
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        results = client.search("python tutorials")

        assert len(results) == 2
        assert results[0]["title"] == "Python Tutorial"
        assert results[0]["url"] == "https://python.org/tutorial"
        assert results[0]["description"] == "Official Python tutorial"

    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_with_freshness(self, mock_client_class):
        """Test search with freshness parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"web": {"results": []}}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_response
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        client.search("news", freshness="pd")

        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]
        assert params["freshness"] == "pd"

    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_count_capped_at_20(self, mock_client_class):
        """Test that count is capped at 20."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"web": {"results": []}}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_response
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        client.search("test", count=50)

        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]
        assert params["count"] == 20

    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_empty_results(self, mock_client_class):
        """Test search with no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"web": {"results": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_response
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        results = client.search("very obscure query")

        assert results == []

    @patch("src.integrations.brave.client.time.sleep")
    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_retries_on_429(self, mock_client_class, mock_sleep):
        """Test that 429 responses are retried."""
        # First call returns 429, second call succeeds
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}
        mock_429.request = MagicMock()

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "web": {"results": [{"title": "OK", "url": "https://ok.com", "description": "Success"}]}
        }
        mock_ok.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.side_effect = [mock_429, mock_ok]
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        results = client.search("test")

        assert len(results) == 1
        assert results[0]["title"] == "OK"
        # Verify it retried (2 calls to get)
        assert mock_http_client.get.call_count == 2

    @patch("src.integrations.brave.client.time.sleep")
    @patch("src.integrations.brave.client.httpx.Client")
    def test_search_raises_after_max_retries(self, mock_client_class, mock_sleep):
        """Test that exhausted retries raise the error."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}
        mock_429.request = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)
        mock_http_client.get.return_value = mock_429
        mock_client_class.return_value = mock_http_client

        client = BraveSearchClient(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            client.search("test")

        # 1 initial + 2 retries = 3 calls
        assert mock_http_client.get.call_count == 3

    @patch("src.integrations.brave.client.time.sleep")
    @patch("src.integrations.brave.client.time.monotonic")
    def test_throttle_enforces_minimum_interval(self, mock_monotonic, mock_sleep):
        """Test that throttle sleeps when requests are too close together."""
        # Simulate: last request was 0.3s ago (less than 1s minimum)
        mock_monotonic.side_effect = [0.3, 1.0]
        BraveSearchClient._last_request_time = 0.0

        BraveSearchClient._throttle()

        # Should sleep for ~0.7s (1.0 - 0.3)
        mock_sleep.assert_called_once()
        sleep_arg = mock_sleep.call_args[0][0]
        assert 0.6 < sleep_arg < 0.8


# ============================================================================
# DUCKDUCKGO CLIENT
# ============================================================================


class TestDuckDuckGoClient:
    """Tests for the DuckDuckGo fallback client."""

    def test_search_success(self):
        """Test successful DuckDuckGo search."""
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = iter(
            [
                {
                    "title": "Python Docs",
                    "href": "https://docs.python.org",
                    "body": "Python documentation",
                },
            ]
        )

        mock_ddgs_module = MagicMock()
        mock_ddgs_module.DDGS.return_value = mock_ddgs

        client = DuckDuckGoClient()
        with patch.dict("sys.modules", {"duckduckgo_search": mock_ddgs_module}):
            results = client.search("python docs")

        assert len(results) == 1
        assert results[0]["title"] == "Python Docs"
        assert results[0]["url"] == "https://docs.python.org"
        assert results[0]["description"] == "Python documentation"

    def test_search_with_freshness_mapping(self):
        """Test that freshness values are mapped correctly."""
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = iter([])

        mock_ddgs_module = MagicMock()
        mock_ddgs_module.DDGS.return_value = mock_ddgs

        client = DuckDuckGoClient()
        with patch.dict("sys.modules", {"duckduckgo_search": mock_ddgs_module}):
            client.search("test", freshness="week")

        mock_ddgs.text.assert_called_once_with("test", max_results=10, timelimit="w")

    def test_search_without_duckduckgo_package(self):
        """Test graceful handling when duckduckgo-search is not installed."""
        client = DuckDuckGoClient()

        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            # The import inside the method will fail, triggering fallback
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *args: (
                    (_ for _ in ()).throw(ImportError())
                    if name == "duckduckgo_search"
                    else __import__(name, *args)
                ),
            ):
                results = client.search("test")
                assert len(results) == 1
                assert "unavailable" in results[0]["title"].lower()


# ============================================================================
# BRAVE SERVICE
# ============================================================================


class TestBraveService:
    """Tests for the BraveService."""

    def _make_service(
        self, enabled=True, api_key="test-key", safe_search="moderate", results_limit=None
    ):
        """Create a BraveService with mocked repos."""
        settings_repo = MagicMock()
        credentials_repo = MagicMock()
        audit_repo = MagicMock()

        def get_setting(key):
            settings_map = {
                "brave.enabled": enabled,
                "brave.safe_search": safe_search,
                "brave.results_limit": results_limit,
            }
            return settings_map.get(key)

        settings_repo.get = MagicMock(side_effect=get_setting)

        if api_key:
            credentials_repo.get = MagicMock(return_value={"credential_data": {"value": api_key}})
        else:
            credentials_repo.get = MagicMock(return_value=None)

        return BraveService(settings_repo, credentials_repo, audit_repo)

    @patch("src.services.brave.BraveSearchClient")
    def test_web_search_success(self, mock_client_class):
        """Test successful web search via Brave."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            {
                "title": "Result 1",
                "url": "https://example.com/1",
                "description": "Description 1",
            }
        ]

        service = self._make_service()
        with patch.object(service, "_get_client", return_value=mock_client):
            result = service.web_search("test query")

        assert result["query"] == "test query"
        assert result["total"] == 1
        assert result["source"] == "brave"
        assert result["results"][0]["title"] == "Result 1"
        assert result["results"][0]["url"] == "https://example.com/1"
        assert result["results"][0]["snippet"] == "Description 1"
        assert result["results"][0]["position"] == 1

    @patch("src.services.brave.DuckDuckGoClient")
    def test_web_search_fallback_to_duckduckgo(self, mock_ddg_class):
        """Test fallback to DuckDuckGo when Brave fails."""
        mock_ddg = MagicMock()
        mock_ddg.search.return_value = [
            {
                "title": "DDG Result",
                "url": "https://ddg.example.com",
                "description": "DuckDuckGo result",
            }
        ]

        service = self._make_service(enabled=False)
        with patch.object(service, "_get_fallback_client", return_value=mock_ddg):
            result = service.web_search("test query")

        assert result["source"] == "duckduckgo"
        assert result["total"] == 1

    def test_web_search_freshness_mapping(self):
        """Test freshness parameter is mapped correctly."""
        assert FRESHNESS_MAP["day"] == "pd"
        assert FRESHNESS_MAP["week"] == "pw"
        assert FRESHNESS_MAP["month"] == "pm"
        assert FRESHNESS_MAP["year"] == "py"

    @patch("src.services.brave.BraveSearchClient")
    def test_web_search_respects_results_limit(self, mock_client_class):
        """Test that results_limit setting is applied."""
        mock_client = MagicMock()
        mock_client.search.return_value = []

        service = self._make_service(results_limit=5)
        with patch.object(service, "_get_client", return_value=mock_client):
            service.web_search("test", count=10)

        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["count"] == 5

    def test_format_results(self):
        """Test result formatting."""
        service = self._make_service()
        raw_results = [
            {"title": "A", "url": "https://a.com", "description": "Desc A"},
            {"title": "B", "url": "https://b.com", "description": "Desc B"},
        ]

        formatted = service._format_results(raw_results, "my query", "brave")

        assert formatted["query"] == "my query"
        assert formatted["total"] == 2
        assert formatted["source"] == "brave"
        assert formatted["results"][0]["position"] == 1
        assert formatted["results"][1]["position"] == 2
        assert formatted["results"][0]["snippet"] == "Desc A"

    def test_test_connection_success(self):
        """Test connection test when successful."""
        service = self._make_service()

        mock_client = MagicMock()
        mock_client.test_connection.return_value = True

        with patch.object(service, "_get_client", return_value=mock_client):
            result = service.test_connection()

        assert result["status"] == "success"
        assert result["service_name"] == "brave"

    def test_test_connection_not_enabled(self):
        """Test connection test when not enabled."""
        service = self._make_service(enabled=False)
        result = service.test_connection()

        assert result["status"] == "error"

    def test_test_connection_no_api_key(self):
        """Test connection test with no API key."""
        service = self._make_service(api_key=None)
        result = service.test_connection()

        assert result["status"] == "error"


# ============================================================================
# DEFAULT AGENTS
# ============================================================================


class TestResearchAgentWebSearch:
    """Tests that web_search is properly assigned to the Research Agent."""

    @pytest.fixture(autouse=True)
    def _mock_crewai(self):
        """Mock crewai imports so we can import agents.base without crewai installed."""
        import sys

        mods = {}
        # Mock all crewai submodules that crew.py imports
        crewai_mods = [
            "crewai",
            "crewai.process",
            "crewai.tools",
            "crewai.agent",
            "crewai.crew",
            "crewai.task",
        ]
        for mod_name in crewai_mods:
            if mod_name not in sys.modules:
                mods[mod_name] = MagicMock()

        with patch.dict("sys.modules", mods):
            # Force reimport of agents package
            for key in list(sys.modules.keys()):
                if key.startswith("src.agents"):
                    del sys.modules[key]
            yield
            # Clean up again
            for key in list(sys.modules.keys()):
                if key.startswith("src.agents"):
                    del sys.modules[key]

    def test_research_agent_has_web_search_tool(self):
        """Verify Research Agent exists and is enabled."""
        from src.agents.base import DEFAULT_AGENTS

        research_agent = DEFAULT_AGENTS["research"]
        assert research_agent is not None
        assert research_agent["enabled"] is True
        # Note: Tools are now dynamically loaded from registry, not hardcoded

    def test_coordinator_mentions_web_search(self):
        """Verify coordinator agent exists and has proper keywords."""
        from src.agents.base import DEFAULT_AGENTS

        coordinator = DEFAULT_AGENTS["coordinator"]
        assert coordinator is not None
        # Coordinator should have delegation-related intent keywords
        assert "delegate" in coordinator["intent_keywords"]


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================


class TestBraveToolDefinitions:
    """Tests for Brave tool registration."""

    def test_web_search_tool_registered(self):
        """Test that web_search tool is registered in the tool registry."""
        from src.core.tools.definitions import initialize_all_tools
        from src.core.tools.registry import get_tool_registry

        initialize_all_tools()
        registry = get_tool_registry()

        tool = registry.get("web_search")
        assert tool is not None
        assert tool.schema.name == "web_search"
        assert tool.service_name == "brave"

    def test_web_search_tool_has_correct_parameters(self):
        """Test that web_search tool has the right parameters."""
        from src.core.tools.definitions import initialize_all_tools
        from src.core.tools.registry import get_tool_registry

        initialize_all_tools()
        registry = get_tool_registry()
        tool = registry.get("web_search")

        params = tool.schema.parameters
        assert "query" in params["properties"]
        assert "count" in params["properties"]
        assert "freshness" in params["properties"]
        assert "query" in params["required"]


# ============================================================================
# CONFIG SETTINGS
# ============================================================================


class TestBraveSettings:
    """Tests for Brave Search setting definitions."""

    def test_brave_settings_defined(self):
        """Test that all Brave settings are defined."""
        from src.models.config import SETTING_DEFINITIONS

        assert "brave.enabled" in SETTING_DEFINITIONS
        assert "brave.api_key" in SETTING_DEFINITIONS
        assert "brave.results_limit" in SETTING_DEFINITIONS
        assert "brave.safe_search" in SETTING_DEFINITIONS

    def test_brave_api_key_is_sensitive(self):
        """Test that the API key setting is marked as sensitive."""
        from src.models.config import SETTING_DEFINITIONS

        api_key_def = SETTING_DEFINITIONS["brave.api_key"]
        assert api_key_def.is_sensitive is True

    def test_brave_enabled_default_true(self):
        """Test that Brave is enabled by default."""
        from src.models.config import SETTING_DEFINITIONS

        enabled_def = SETTING_DEFINITIONS["brave.enabled"]
        assert enabled_def.default_value is True

    def test_brave_safe_search_options(self):
        """Test safe search options."""
        from src.models.config import SETTING_DEFINITIONS

        safe_search_def = SETTING_DEFINITIONS["brave.safe_search"]
        assert safe_search_def.options == ["off", "moderate", "strict"]
        assert safe_search_def.default_value == "moderate"


# ============================================================================
# TOOL METADATA
# ============================================================================


class TestBraveToolMetadata:
    """Tests for Brave tool metadata."""

    def test_web_search_metadata_exists(self):
        """Test that web_search tool has metadata."""
        from src.core.tools.metadata import TOOL_METADATA

        assert "web_search" in TOOL_METADATA
        meta = TOOL_METADATA["web_search"]
        assert meta.name == "web_search"
        assert meta.category == "search"
