"""Tests for the extended Azure DevOps plugin.

Covers:
- All 13 tool names are registered / visible after plugin load
- Existing built-in plugins (toggl, wordpress) are unaffected
- Body builders produce correct JSON Patch payloads
- Content-Type override fires for JSON Patch endpoints
- HTTP call uses content= (not json=) when the override is active
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.plugin_service import (
    PluginService,
    _ADO_JSON_PATCH_ENDPOINTS,
    _build_ado_add_comment_body,
    _build_ado_move_work_item_body,
    _build_ado_update_work_item_body,
    _build_ado_work_item_body,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_ADO_TOOLS = {
    "plugin_azure_devops_query_work_items",
    "plugin_azure_devops_get_work_item",
    "plugin_azure_devops_create_work_item",
    "plugin_azure_devops_list_repositories",
    "plugin_azure_devops_list_pipelines",
    # new lookup tools
    "plugin_azure_devops_get_work_item_with_relations",
    "plugin_azure_devops_list_iterations",
    "plugin_azure_devops_list_areas",
    "plugin_azure_devops_list_work_item_types",
    "plugin_azure_devops_list_states",
    # new edit tools
    "plugin_azure_devops_update_work_item",
    "plugin_azure_devops_move_work_item",
    "plugin_azure_devops_add_work_item_comment",
}


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


# ---------------------------------------------------------------------------
# Plugin loading — registration and existing plugins
# ---------------------------------------------------------------------------


class TestPluginLoading:
    def setup_method(self):
        self.svc = _make_plugin_service()

    def test_azure_devops_has_13_endpoints(self):
        ado = self.svc._definitions["azure_devops"]
        assert len(ado.endpoints) == 13

    def test_all_ado_tool_names_registered(self):
        ado = self.svc._definitions["azure_devops"]
        registered = {f"plugin_azure_devops_{ep.name}" for ep in ado.endpoints}
        assert registered == _EXPECTED_ADO_TOOLS

    def test_toggl_unaffected(self):
        toggl = self.svc._definitions["toggl"]
        assert len(toggl.endpoints) == 6

    def test_wordpress_unaffected(self):
        wp = self.svc._definitions["wordpress"]
        assert len(wp.endpoints) == 4

    def test_all_three_builtins_present(self):
        assert {"azure_devops", "toggl", "wordpress"}.issubset(self.svc._definitions)


# ---------------------------------------------------------------------------
# _ADO_JSON_PATCH_ENDPOINTS constant
# ---------------------------------------------------------------------------


class TestAdoJsonPatchEndpoints:
    def test_contains_create(self):
        assert "create_work_item" in _ADO_JSON_PATCH_ENDPOINTS

    def test_contains_update(self):
        assert "update_work_item" in _ADO_JSON_PATCH_ENDPOINTS

    def test_contains_move(self):
        assert "move_work_item" in _ADO_JSON_PATCH_ENDPOINTS

    def test_does_not_contain_comment(self):
        # add_work_item_comment uses regular application/json
        assert "add_work_item_comment" not in _ADO_JSON_PATCH_ENDPOINTS

    def test_does_not_contain_get(self):
        assert "get_work_item" not in _ADO_JSON_PATCH_ENDPOINTS


# ---------------------------------------------------------------------------
# _build_ado_update_work_item_body
# ---------------------------------------------------------------------------


class TestBuildAdoUpdateWorkItemBody:
    def _paths(self, patch):
        return {op["path"]: op["value"] for op in patch}

    def test_title_maps_correctly(self):
        result = _build_ado_update_work_item_body({"title": "New Title"})
        assert {"op": "add", "path": "/fields/System.Title", "value": "New Title"} in result

    def test_description_maps_correctly(self):
        result = _build_ado_update_work_item_body({"description": "<p>Hello</p>"})
        paths = self._paths(result)
        assert paths["/fields/System.Description"] == "<p>Hello</p>"

    def test_acceptance_criteria_maps_correctly(self):
        result = _build_ado_update_work_item_body({"acceptance_criteria": "AC text"})
        paths = self._paths(result)
        assert paths["/fields/Microsoft.VSTS.Common.AcceptanceCriteria"] == "AC text"

    def test_state_maps_correctly(self):
        result = _build_ado_update_work_item_body({"state": "Active"})
        paths = self._paths(result)
        assert paths["/fields/System.State"] == "Active"

    def test_iteration_path_maps_correctly(self):
        result = _build_ado_update_work_item_body({"iteration_path": "Project\\Sprint 1"})
        paths = self._paths(result)
        assert paths["/fields/System.IterationPath"] == "Project\\Sprint 1"

    def test_area_path_maps_correctly(self):
        result = _build_ado_update_work_item_body({"area_path": "Project\\Backend"})
        paths = self._paths(result)
        assert paths["/fields/System.AreaPath"] == "Project\\Backend"

    def test_priority_maps_correctly(self):
        result = _build_ado_update_work_item_body({"priority": 2})
        paths = self._paths(result)
        assert paths["/fields/Microsoft.VSTS.Common.Priority"] == 2

    def test_assigned_to_maps_correctly(self):
        result = _build_ado_update_work_item_body({"assigned_to": "user@example.com"})
        paths = self._paths(result)
        assert paths["/fields/System.AssignedTo"] == "user@example.com"

    def test_tags_maps_correctly(self):
        result = _build_ado_update_work_item_body({"tags": "backend; perf"})
        paths = self._paths(result)
        assert paths["/fields/System.Tags"] == "backend; perf"

    def test_multiple_fields_all_present(self):
        result = _build_ado_update_work_item_body({"title": "T", "state": "Closed", "priority": 1})
        paths = self._paths(result)
        assert "/fields/System.Title" in paths
        assert "/fields/System.State" in paths
        assert "/fields/Microsoft.VSTS.Common.Priority" in paths

    def test_only_supplied_fields_included(self):
        result = _build_ado_update_work_item_body({"state": "Active"})
        assert len(result) == 1

    def test_all_ops_are_add(self):
        result = _build_ado_update_work_item_body({"title": "X", "state": "Y"})
        assert all(op["op"] == "add" for op in result)

    def test_empty_params_raises(self):
        with pytest.raises(ValueError, match="update_work_item requires"):
            _build_ado_update_work_item_body({})

    def test_unrecognised_key_raises(self):
        with pytest.raises(ValueError):
            _build_ado_update_work_item_body({"unknown_field": "value"})


# ---------------------------------------------------------------------------
# _build_ado_move_work_item_body
# ---------------------------------------------------------------------------


class TestBuildAdoMoveWorkItemBody:
    def test_adds_new_parent_relation(self):
        result = _build_ado_move_work_item_body({"new_parent_id": 42}, "my-org")
        add_ops = [op for op in result if op["op"] == "add"]
        assert len(add_ops) == 1
        val = add_ops[0]["value"]
        assert val["rel"] == "System.LinkTypes.Hierarchy-Reverse"
        assert "my-org" in val["url"]
        assert "42" in val["url"]

    def test_parent_url_format(self):
        result = _build_ado_move_work_item_body({"new_parent_id": 99}, "contoso")
        add_op = next(op for op in result if op["op"] == "add")
        assert add_op["value"]["url"] == ("https://dev.azure.com/contoso/_apis/wit/workitems/99")

    def test_removes_old_parent_when_index_supplied(self):
        result = _build_ado_move_work_item_body(
            {"new_parent_id": 10, "current_parent_relation_index": 2}, "org"
        )
        ops = {op["op"] for op in result}
        assert "remove" in ops
        remove_op = next(op for op in result if op["op"] == "remove")
        assert remove_op["path"] == "/relations/2"

    def test_no_remove_when_index_omitted(self):
        result = _build_ado_move_work_item_body({"new_parent_id": 10}, "org")
        assert not any(op["op"] == "remove" for op in result)

    def test_remove_comes_before_add(self):
        result = _build_ado_move_work_item_body(
            {"new_parent_id": 10, "current_parent_relation_index": 0}, "org"
        )
        ops = [op["op"] for op in result]
        assert ops == ["remove", "add"]

    def test_add_path_is_append(self):
        result = _build_ado_move_work_item_body({"new_parent_id": 5}, "org")
        add_op = next(op for op in result if op["op"] == "add")
        assert add_op["path"] == "/relations/-"


# ---------------------------------------------------------------------------
# _build_ado_add_comment_body
# ---------------------------------------------------------------------------


class TestBuildAdoAddCommentBody:
    def test_wraps_text(self):
        result = _build_ado_add_comment_body({"text": "Hello world"})
        assert result == {"text": "Hello world"}

    def test_empty_text_fallback(self):
        result = _build_ado_add_comment_body({})
        assert result == {"text": ""}


# ---------------------------------------------------------------------------
# _build_ado_work_item_body (existing — must remain unchanged)
# ---------------------------------------------------------------------------


class TestBuildAdoWorkItemBody:
    def test_title_required(self):
        result = _build_ado_work_item_body({"title": "My ticket"})
        assert result[0] == {
            "op": "add",
            "path": "/fields/System.Title",
            "value": "My ticket",
        }

    def test_description_optional(self):
        result = _build_ado_work_item_body({"title": "T", "description": "D"})
        paths = [op["path"] for op in result]
        assert "/fields/System.Description" in paths

    def test_no_description_gives_single_op(self):
        result = _build_ado_work_item_body({"title": "T"})
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Content-Type override — HTTP call site integration
# ---------------------------------------------------------------------------


class TestContentTypeOverride:
    """Verify that update_work_item and move_work_item trigger the
    application/json-patch+json override, while other endpoints do not."""

    def setup_method(self):
        self.svc = _make_plugin_service()
        self.svc._definitions["azure_devops"].endpoints  # ensure loaded

    def _make_mock_response(self, body: Dict[str, Any] | None = None):
        resp = MagicMock()
        resp.content = b'{"id":1}' if body is None else json.dumps(body).encode()
        resp.json.return_value = body or {"id": 1}
        resp.raise_for_status = MagicMock()
        return resp

    def _mock_credentials(self):
        self.svc.credentials_repo.get.return_value = {"credential_data": {"token": "fake-pat"}}
        self.svc.settings_repo.get.side_effect = lambda key: (
            "my-org" if key == "plugin.azure_devops.organization" else None
        )

    @pytest.mark.asyncio
    async def test_update_work_item_sends_patch_content_type(self):
        self._mock_credentials()
        mock_response = self._make_mock_response()
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint(
                "azure_devops",
                "update_work_item",
                {"project": "MyProj", "id": 1, "state": "Active"},
            )

        assert captured["headers"]["Content-Type"] == "application/json-patch+json"
        # Must use content=, not json=
        assert captured.get("content") is not None
        assert captured.get("json") is None

    @pytest.mark.asyncio
    async def test_move_work_item_sends_patch_content_type(self):
        self._mock_credentials()
        mock_response = self._make_mock_response()
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint(
                "azure_devops",
                "move_work_item",
                {"project": "MyProj", "id": 5, "new_parent_id": 10},
            )

        assert captured["headers"]["Content-Type"] == "application/json-patch+json"
        assert captured.get("content") is not None
        assert captured.get("json") is None

    @pytest.mark.asyncio
    async def test_create_work_item_sends_patch_content_type(self):
        """create_work_item was previously broken — verify the fix."""
        self._mock_credentials()
        mock_response = self._make_mock_response()
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint(
                "azure_devops",
                "create_work_item",
                {"project": "MyProj", "type": "Task", "title": "Do something"},
            )

        assert captured["headers"]["Content-Type"] == "application/json-patch+json"
        assert captured.get("content") is not None
        assert captured.get("json") is None

    @pytest.mark.asyncio
    async def test_add_comment_uses_standard_json(self):
        """add_work_item_comment should NOT use the patch content type."""
        self._mock_credentials()
        mock_response = self._make_mock_response()
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint(
                "azure_devops",
                "add_work_item_comment",
                {"project": "MyProj", "id": 1, "text": "LGTM"},
            )

        assert captured["headers"]["Content-Type"] == "application/json"
        assert captured.get("json") is not None
        assert captured.get("content") is None

    @pytest.mark.asyncio
    async def test_get_endpoint_uses_standard_json(self):
        """GET endpoints should never trigger the patch content type override."""
        self._mock_credentials()
        mock_response = self._make_mock_response()
        captured: Dict[str, Any] = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=fake_request)
            mock_cls.return_value = mock_client

            await self.svc._execute_endpoint(
                "azure_devops",
                "get_work_item",
                {"project": "MyProj", "id": 1},
            )

        assert captured["headers"]["Content-Type"] == "application/json"
