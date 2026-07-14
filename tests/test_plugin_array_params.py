"""Tests for native ``array`` parameter type support in plugin endpoints.

Covers:
- The Pydantic model accepts ``type: "array"`` with a valid ``items`` block.
- Validation rejects array-without-items, items-on-non-array, bad element
  types, and array on path/header placements — each with a readable message.
- Tool-schema generation emits a real JSON-Schema array (``type: array`` +
  ``items``) so the LLM emits an array, not a stringified one.
- Body array parameters serialize to a native JSON array in the outbound
  request; query array parameters serialize as repeated query params.
- Existing primitive-only parameters are unaffected.
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.models.plugin import (
    PARAM_TYPES,
    PluginDefinition,
    PluginEndpointParameter,
)
from src.services.plugin_service import PluginService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin_service() -> PluginService:
    settings_repo = MagicMock()
    settings_repo.get.return_value = None
    credentials_repo = MagicMock()
    credentials_repo.get.return_value = None
    return PluginService(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        data_dir="/tmp",
    )


def _array_plugin_dict(param_in: str = "body") -> Dict[str, Any]:
    """A minimal plugin whose single endpoint takes array params."""
    return {
        "id": "array_test",
        "display_name": "Array Test",
        "description": "Plugin exercising array parameter types.",
        "base_url": "https://api.example.com",
        "auth": {"type": "bearer"},
        "endpoints": [
            {
                "name": "create_post",
                "display_name": "Create Post",
                "description": "Create a post across social accounts.",
                "method": "POST",
                "path": "/v1/posts",
                "parameters": [
                    {
                        "name": "caption",
                        "in": param_in,
                        "type": "string",
                        "description": "Post caption.",
                        "required": True,
                    },
                    {
                        "name": "social_accounts",
                        "in": param_in,
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Numeric social account IDs.",
                        "required": True,
                    },
                    {
                        "name": "media_urls",
                        "in": param_in,
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Media URLs.",
                        "required": False,
                    },
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestArrayParameterValidation:
    def test_array_in_param_types(self):
        assert "array" in PARAM_TYPES

    def test_valid_array_param_accepted(self):
        param = PluginEndpointParameter.model_validate(
            {
                "name": "ids",
                "in": "body",
                "type": "array",
                "items": {"type": "integer"},
                "description": "IDs.",
            }
        )
        assert param.type == "array"
        assert param.items is not None
        assert param.items.type == "integer"

    def test_full_plugin_with_array_params_validates(self):
        defn = PluginDefinition.model_validate(_array_plugin_dict("body"))
        param = defn.endpoints[0].parameters[1]
        assert param.type == "array"
        assert param.items.type == "integer"

    def test_array_without_items_rejected(self):
        with pytest.raises(ValidationError, match="missing the required 'items'"):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "body",
                    "type": "array",
                    "description": "IDs.",
                }
            )

    def test_items_on_non_array_rejected(self):
        with pytest.raises(ValidationError, match="only allowed when type is 'array'"):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "body",
                    "type": "string",
                    "items": {"type": "integer"},
                    "description": "IDs.",
                }
            )

    def test_invalid_element_type_rejected(self):
        with pytest.raises(ValidationError):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "body",
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "IDs.",
                }
            )

    def test_nested_array_element_type_rejected(self):
        with pytest.raises(ValidationError):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "body",
                    "type": "array",
                    "items": {"type": "array"},
                    "description": "IDs.",
                }
            )

    def test_invalid_param_type_rejected(self):
        with pytest.raises(ValidationError, match="invalid type 'object'"):
            PluginEndpointParameter.model_validate(
                {
                    "name": "blob",
                    "in": "body",
                    "type": "object",
                    "description": "Blob.",
                }
            )

    def test_array_in_path_rejected(self):
        with pytest.raises(ValidationError, match="not supported"):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "path",
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs.",
                }
            )

    def test_array_in_header_rejected(self):
        with pytest.raises(ValidationError, match="not supported"):
            PluginEndpointParameter.model_validate(
                {
                    "name": "ids",
                    "in": "header",
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs.",
                }
            )

    def test_array_in_query_accepted(self):
        param = PluginEndpointParameter.model_validate(
            {
                "name": "types",
                "in": "query",
                "type": "array",
                "items": {"type": "string"},
                "description": "Types.",
            }
        )
        assert param.type == "array"


# ---------------------------------------------------------------------------
# Tool-schema generation
# ---------------------------------------------------------------------------


class TestArrayToolSchema:
    def setup_method(self):
        self.svc = _make_plugin_service()

    def _build_schema(self, param_in: str = "body") -> Dict[str, Any]:
        defn = PluginDefinition.model_validate(_array_plugin_dict(param_in))
        tool = self.svc._create_tool("array_test", defn, defn.endpoints[0])
        return tool.schema.parameters

    def test_array_param_emits_json_schema_array(self):
        props = self._build_schema()["properties"]
        assert props["social_accounts"]["type"] == "array"
        assert props["social_accounts"]["items"] == {"type": "integer"}

    def test_string_array_items_type(self):
        props = self._build_schema()["properties"]
        assert props["media_urls"]["type"] == "array"
        assert props["media_urls"]["items"] == {"type": "string"}

    def test_primitive_param_has_no_items(self):
        props = self._build_schema()["properties"]
        assert props["caption"]["type"] == "string"
        assert "items" not in props["caption"]

    def test_required_list_reflects_required_flag(self):
        schema = self._build_schema()
        assert "social_accounts" in schema["required"]
        assert "media_urls" not in schema["required"]


# ---------------------------------------------------------------------------
# Runtime serialization
# ---------------------------------------------------------------------------


class TestArraySerialization:
    def setup_method(self):
        self.svc = _make_plugin_service()

    def _install_array_plugin(self, param_in: str = "body"):
        defn = PluginDefinition.model_validate(_array_plugin_dict(param_in))
        self.svc._definitions["array_test"] = defn
        self.svc.credentials_repo.get.return_value = {
            "credential_data": {"token": "fake-token"}
        }

    def _make_mock_response(self):
        resp = MagicMock()
        resp.content = b'{"id": 1}'
        resp.json.return_value = {"id": 1}
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        return resp

    async def _run(self, param_in: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self._install_array_plugin(param_in)
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return self._make_mock_response()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint("array_test", "create_post", arguments)

        return captured

    @pytest.mark.asyncio
    async def test_body_array_is_native_json_array(self):
        captured = await self._run(
            "body",
            {"caption": "hi", "social_accounts": [75205, 75209]},
        )
        # httpx json= receives the raw Python structure
        assert captured["json"]["social_accounts"] == [75205, 75209]
        assert isinstance(captured["json"]["social_accounts"], list)
        # And it serializes to a genuine JSON array, not a quoted string
        serialized = json.dumps(captured["json"])
        assert '"social_accounts": [75205, 75209]' in serialized
        assert '"[75205' not in serialized

    @pytest.mark.asyncio
    async def test_query_array_is_list(self):
        captured = await self._run(
            "query",
            {"caption": "hi", "media_urls": ["a.png", "b.png"]},
        )
        # httpx serializes a list value as repeated query params.
        assert captured["params"]["media_urls"] == ["a.png", "b.png"]

    @pytest.mark.asyncio
    async def test_single_element_array_stays_array(self):
        captured = await self._run(
            "body",
            {"caption": "hi", "social_accounts": [75205]},
        )
        assert captured["json"]["social_accounts"] == [75205]
        assert isinstance(captured["json"]["social_accounts"], list)


# ---------------------------------------------------------------------------
# Existing built-in plugins remain unaffected
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def setup_method(self):
        self.svc = _make_plugin_service()

    def test_builtins_still_load(self):
        assert {"azure_devops", "toggl", "wordpress"}.issubset(self.svc._definitions)

    def test_primitive_params_generate_unchanged_schema(self):
        toggl = self.svc._definitions["toggl"]
        for ep in toggl.endpoints:
            tool = self.svc._create_tool("toggl", toggl, ep)
            for prop in tool.schema.parameters["properties"].values():
                # No primitive param should ever carry an items block.
                assert "items" not in prop
                assert prop["type"] in {"string", "integer", "number", "boolean"}
