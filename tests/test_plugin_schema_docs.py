"""Schema drift-guard: validate built-ins, doc examples, and converter output.

This test prevents the plugin schema, Pydantic models, built-in plugins, and
``docs/plugin-schema.md`` examples from silently going out of sync.

If any of these fail:
- Fix the schema / Pydantic model AND update the affected doc examples / built-ins in the
  same PR — the tests enforce they are consistent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.models.plugin import PluginDefinition
from src.plugins.openapi_import import openapi_to_plugin_definition

REPO_ROOT = Path(__file__).parent.parent
BUILTINS_DIR = REPO_ROOT / "src" / "plugins" / "builtins"
PLUGIN_SCHEMA_DOC = REPO_ROOT / "docs" / "plugin-schema.md"


# ---------------------------------------------------------------------------
# 1. All built-in plugin files validate against the Pydantic model.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("json_path", sorted(BUILTINS_DIR.glob("*.json")))
def test_builtin_plugin_validates(json_path):
    """Every built-in plugin JSON must satisfy PluginDefinition."""
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    try:
        defn = PluginDefinition.model_validate(raw)
    except Exception as exc:
        pytest.fail(f"Built-in plugin {json_path.name!r} failed validation: {exc}")
    assert (
        defn.id == json_path.stem
    ), f"Plugin id {defn.id!r} in {json_path.name!r} doesn't match the filename stem."


# ---------------------------------------------------------------------------
# 2. Full JSON examples in docs/plugin-schema.md validate.
# ---------------------------------------------------------------------------


def _extract_json_blocks(md_text: str):
    """Yield (label, parsed_dict) for each ```json block that looks like a full plugin."""
    blocks = re.findall(r"```json\n(.*?)```", md_text, re.DOTALL)
    results = []
    for block in blocks:
        try:
            obj = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        # Only test blocks that look like a complete plugin definition.
        if isinstance(obj, dict) and "id" in obj and "endpoints" in obj and "auth" in obj:
            results.append(obj)
    return results


@pytest.mark.skipif(not PLUGIN_SCHEMA_DOC.exists(), reason="docs/plugin-schema.md not found")
def test_doc_json_examples_validate():
    """All full plugin-definition JSON blocks in docs/plugin-schema.md must validate."""
    md_text = PLUGIN_SCHEMA_DOC.read_text(encoding="utf-8")
    examples = _extract_json_blocks(md_text)
    assert examples, "Expected at least one full plugin JSON block in docs/plugin-schema.md"
    for obj in examples:
        try:
            PluginDefinition.model_validate(obj)
        except Exception as exc:
            pytest.fail(
                f"docs/plugin-schema.md contains an invalid plugin JSON block (id={obj.get('id')!r}): {exc}"
            )


# ---------------------------------------------------------------------------
# 3. Converter output validates for representative specs.
# ---------------------------------------------------------------------------

SAMPLE_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Test Service", "version": "1.0.0"},
    "servers": [{"url": "https://api.test.example.com/v2"}],
    "components": {
        "securitySchemes": {
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        }
    },
    "paths": {
        "/resources": {
            "get": {
                "operationId": "list_resources",
                "summary": "List resources",
                "description": "Returns all resources.",
                "parameters": [
                    {
                        "name": "page",
                        "in": "query",
                        "schema": {"type": "integer"},
                        "description": "Page number.",
                        "required": False,
                    }
                ],
            },
            "post": {
                "operationId": "create_resource",
                "summary": "Create resource",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string", "description": "Resource name."},
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Tags to apply.",
                                    },
                                },
                            }
                        }
                    }
                },
            },
        },
        "/resources/{id}": {
            "get": {
                "operationId": "get_resource",
                "summary": "Get resource",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Resource identifier.",
                    }
                ],
            },
            "delete": {
                "operationId": "delete_resource",
                "summary": "Delete resource",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Resource identifier.",
                    }
                ],
            },
        },
    },
}


def test_converter_output_validates():
    """openapi_to_plugin_definition output must pass PluginDefinition validation."""
    defn, warnings = openapi_to_plugin_definition(SAMPLE_OPENAPI)
    try:
        parsed = PluginDefinition.model_validate(defn)
    except Exception as exc:
        pytest.fail(f"Converter output failed PluginDefinition validation: {exc}\nOutput: {defn}")
    assert parsed.auth.type == "header"
    assert parsed.auth.header_name == "X-API-Key"
    assert len(parsed.endpoints) == 4
    # Check array param is present and valid
    create_ep = next(e for e in parsed.endpoints if e.name == "create_resource")
    tags_param = next(p for p in create_ep.parameters if p.name == "tags")
    assert tags_param.type == "array"
    assert tags_param.items is not None
    assert tags_param.items.type == "string"


def test_converter_no_warnings_for_clean_spec():
    """A well-formed spec with standard auth should produce no warnings."""
    defn, warnings = openapi_to_plugin_definition(SAMPLE_OPENAPI)
    assert warnings == [], f"Unexpected warnings for clean spec: {warnings}"


# ---------------------------------------------------------------------------
# 4. Plugin-builder tools are registered in the ToolRegistry after init.
# ---------------------------------------------------------------------------


def test_plugin_builder_tools_registered():
    """install_plugin, inspect_api_source, test_plugin_connection must be in the ToolRegistry."""
    from src.core.tools.definitions import initialize_all_tools
    import src.core.tools.registry as reg_module

    registry = reg_module.ToolRegistry()
    # Temporarily redirect the global registry to our local instance

    original = reg_module._registry
    reg_module._registry = registry
    try:
        initialize_all_tools()
        names = set(registry._tools.keys())
    finally:
        reg_module._registry = original

    assert "install_plugin" in names, "install_plugin not registered"
    assert "inspect_api_source" in names, "inspect_api_source not registered"
    assert "test_plugin_connection" in names, "test_plugin_connection not registered"
