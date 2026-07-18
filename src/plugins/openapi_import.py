"""Convert an OpenAPI / Swagger specification into an Open Assistant plugin definition.

This is a best-effort, dependency-free converter used by the plugin-builder tools
(``install_plugin`` / ``inspect_api_source``).  It maps the parts of an OpenAPI 3.x or
Swagger 2.0 document that the plugin schema can represent (``src/plugins/plugin_schema.json``)
and records everything it has to drop or approximate in a ``warnings`` list so the calling
agent can surface it to the user.

The output is a plain ``dict`` that is validated by ``PluginDefinition`` at install time — this
module deliberately does not import the Pydantic model, so it stays a pure transformation that
is easy to unit-test.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Cap the number of imported operations so a large spec doesn't register hundreds of tools.
MAX_ENDPOINTS = 50

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def looks_like_openapi(obj: Any) -> bool:
    """True if ``obj`` looks like an OpenAPI 3.x or Swagger 2.0 document."""
    return isinstance(obj, dict) and (
        "openapi" in obj or "swagger" in obj or "paths" in obj
    )


def looks_like_plugin(obj: Any) -> bool:
    """True if ``obj`` already looks like an Open Assistant plugin definition."""
    return (
        isinstance(obj, dict)
        and "id" in obj
        and "endpoints" in obj
        and "auth" in obj
    )


def slugify(text: str, fallback: str = "api") -> str:
    """Turn arbitrary text into a valid id/name matching ``^[a-z][a-z0-9_]*$``."""
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if not slug:
        slug = fallback
    if not slug[0].isalpha():
        slug = f"p_{slug}"
    return slug


def _resolve_ref(spec: Dict[str, Any], node: Any) -> Any:
    """Resolve a single local ``$ref`` (``#/...``) one level deep; return node unchanged otherwise."""
    if isinstance(node, dict) and "$ref" in node and isinstance(node["$ref"], str):
        ref = node["$ref"]
        if ref.startswith("#/"):
            target: Any = spec
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    return node  # unresolvable — leave as-is
            return target
    return node


def _json_type(schema: Optional[Dict[str, Any]]) -> str:
    """Map a JSON-Schema ``type`` to one of the plugin parameter types."""
    if not isinstance(schema, dict):
        return "string"
    t = schema.get("type")
    if t in ("integer", "number", "boolean", "array", "string"):
        return t
    return "string"


def _base_url(spec: Dict[str, Any], override: Optional[str], warnings: List[str]) -> str:
    """Derive the base URL from the spec (OpenAPI 3 ``servers`` or Swagger 2 host/basePath)."""
    if override:
        return override.rstrip("/")

    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        url = (servers[0] or {}).get("url", "") if isinstance(servers[0], dict) else ""
        if len(servers) > 1:
            warnings.append(
                f"Spec declares {len(servers)} servers; used the first ({url!r}). "
                "Pass a base URL explicitly to override."
            )
        if url and "{" in url:
            warnings.append(
                f"Base URL {url!r} contains server variables that were kept verbatim; "
                "edit the plugin if they need substituting."
            )
        return url.rstrip("/")

    # Swagger 2.0
    host = spec.get("host")
    if host:
        schemes = spec.get("schemes") or ["https"]
        scheme = "https" if "https" in schemes else schemes[0]
        base_path = spec.get("basePath", "") or ""
        return f"{scheme}://{host}{base_path}".rstrip("/")

    warnings.append(
        "No server/base URL found in the spec — set base_url before this plugin can be used."
    )
    return ""


def _auth(spec: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    """Map the first usable security scheme to a plugin ``auth`` object."""
    schemes: Dict[str, Any] = {}
    # OpenAPI 3
    comp = spec.get("components")
    if isinstance(comp, dict) and isinstance(comp.get("securitySchemes"), dict):
        schemes = comp["securitySchemes"]
    # Swagger 2
    elif isinstance(spec.get("securityDefinitions"), dict):
        schemes = spec["securityDefinitions"]

    for name, scheme in schemes.items():
        if not isinstance(scheme, dict):
            continue
        stype = (scheme.get("type") or "").lower()
        if stype == "basic":
            # Swagger 2.0 uses type: "basic" directly
            return {"type": "basic"}
        if stype == "http":
            http_scheme = (scheme.get("scheme") or "").lower()
            if http_scheme == "basic":
                return {"type": "basic"}
            # bearer or unspecified http → bearer
            return {"type": "bearer"}
        if stype == "apikey":
            location = (scheme.get("in") or "").lower()
            header_name = scheme.get("name") or "X-API-Key"
            if location == "header":
                return {"type": "header", "header_name": header_name}
            warnings.append(
                f"Security scheme {name!r} sends an API key in '{location}', which the plugin "
                "schema can't represent as auth; defaulted to bearer — adjust manually."
            )
            return {"type": "bearer"}
        if stype in ("oauth2", "openidconnect"):
            warnings.append(
                f"Security scheme {name!r} uses {stype}, which isn't supported by the four plugin "
                "auth types; defaulted to bearer (paste a token manually) — adjust if needed."
            )
            return {"type": "bearer"}

    warnings.append(
        "No supported security scheme detected; defaulted auth to 'bearer'. "
        "Change it if the API needs no auth, a custom header, or basic auth."
    )
    return {"type": "bearer"}


def _params_from_operation(
    spec: Dict[str, Any],
    path_item: Dict[str, Any],
    operation: Dict[str, Any],
    warnings: List[str],
    op_label: str,
) -> List[Dict[str, Any]]:
    """Build the plugin ``parameters`` list from an operation's parameters + request body."""
    params: List[Dict[str, Any]] = []
    seen: set = set()

    # Path-level params apply to every operation on that path, plus operation-level params.
    raw_params = list(path_item.get("parameters", []) or []) + list(
        operation.get("parameters", []) or []
    )
    for raw in raw_params:
        raw = _resolve_ref(spec, raw)
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        location = (raw.get("in") or "query").lower()
        if not name or name in seen:
            continue
        if location == "cookie":
            warnings.append(f"{op_label}: dropped cookie parameter {name!r} (unsupported).")
            continue
        # OpenAPI 3 puts type under 'schema'; Swagger 2 inlines it.
        schema = raw.get("schema") if isinstance(raw.get("schema"), dict) else raw
        ptype = _json_type(schema)
        entry: Dict[str, Any] = {
            "name": name,
            "in": location,
            "type": ptype,
            "description": raw.get("description") or f"{name} parameter.",
            "required": bool(raw.get("required", location == "path")),
        }
        if ptype == "array":
            if location in ("path", "header"):
                warnings.append(
                    f"{op_label}: array parameter {name!r} in '{location}' is unsupported; "
                    "converted to string."
                )
                entry["type"] = "string"
            else:
                items = schema.get("items") if isinstance(schema, dict) else None
                entry["items"] = {"type": _json_type(items) if _json_type(items) != "array" else "string"}
        params.append(entry)
        seen.add(name)

    # Request body (OpenAPI 3) → flat body params.
    body = _resolve_ref(spec, operation.get("requestBody")) if operation.get("requestBody") else None
    if isinstance(body, dict):
        content = body.get("content", {})
        json_schema = None
        if isinstance(content, dict):
            for ct, media in content.items():
                if "json" in ct and isinstance(media, dict):
                    json_schema = _resolve_ref(spec, media.get("schema"))
                    break
        _body_params_from_schema(spec, json_schema, params, seen, warnings, op_label)

    # Swagger 2 body / formData params.
    for raw in raw_params:
        raw = _resolve_ref(spec, raw)
        if isinstance(raw, dict) and (raw.get("in") or "").lower() == "body":
            body_schema = _resolve_ref(spec, raw.get("schema"))
            _body_params_from_schema(spec, body_schema, params, seen, warnings, op_label)

    return params


def _body_params_from_schema(
    spec: Dict[str, Any],
    schema: Any,
    params: List[Dict[str, Any]],
    seen: set,
    warnings: List[str],
    op_label: str,
) -> None:
    """Flatten a JSON object schema into primitive/array body params."""
    schema = _resolve_ref(spec, schema)
    if not isinstance(schema, dict):
        return
    if schema.get("type") and schema.get("type") != "object":
        warnings.append(
            f"{op_label}: request body is not a flat object; body parameters were omitted — "
            "add them manually if the API needs a structured body."
        )
        return
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    required = set(schema.get("required", []) or [])
    for pname, pschema in props.items():
        pschema = _resolve_ref(spec, pschema)
        if pname in seen or not isinstance(pschema, dict):
            continue
        ptype = _json_type(pschema)
        if ptype == "object" or (ptype == "array" and _json_type(pschema.get("items")) == "array"):
            warnings.append(
                f"{op_label}: nested body field {pname!r} was skipped (only flat objects and "
                "arrays of primitives are supported) — add it manually if required."
            )
            continue
        entry: Dict[str, Any] = {
            "name": pname,
            "in": "body",
            "type": ptype,
            "description": pschema.get("description") or f"{pname} field.",
            "required": pname in required,
        }
        if ptype == "array":
            items = pschema.get("items")
            item_type = _json_type(items)
            if item_type == "array":
                item_type = "string"
            if isinstance(items, dict) and items.get("type") == "object":
                warnings.append(
                    f"{op_label}: body field {pname!r} is an array of objects (unsupported); "
                    "skipped — add manually if required."
                )
                continue
            entry["items"] = {"type": item_type}
        params.append(entry)
        seen.add(pname)


def openapi_to_plugin_definition(
    spec: Dict[str, Any],
    base_url_override: Optional[str] = None,
    plugin_id: Optional[str] = None,
    max_endpoints: int = MAX_ENDPOINTS,
) -> Tuple[Dict[str, Any], List[str]]:
    """Convert an OpenAPI/Swagger dict into a plugin definition dict.

    Returns ``(definition, warnings)``.  The definition still needs to pass ``PluginDefinition``
    validation at install time; ``warnings`` lists everything that was approximated or dropped.
    """
    warnings: List[str] = []
    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    title = info.get("title") or "Imported API"

    definition: Dict[str, Any] = {
        "id": slugify(plugin_id or title),
        "display_name": title,
        "description": (info.get("description") or title)[:500],
        "icon": "🔌",
        "base_url": _base_url(spec, base_url_override, warnings),
        "auth": _auth(spec, warnings),
        "config_fields": [],
        "endpoints": [],
    }

    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        warnings.append("Spec has no paths; no endpoints were generated.")
        return definition, warnings

    used_names: set = set()
    total_ops = 0
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            total_ops += 1
            if len(definition["endpoints"]) >= max_endpoints:
                continue

            op_id = operation.get("operationId")
            name = slugify(op_id) if op_id else slugify(f"{method}_{path}")
            base_name = name
            n = 2
            while name in used_names:
                name = f"{base_name}_{n}"
                n += 1
            used_names.add(name)

            op_label = f"{method.upper()} {path}"
            description = (
                operation.get("description")
                or operation.get("summary")
                or op_label
            )
            endpoint: Dict[str, Any] = {
                "name": name,
                "display_name": (operation.get("summary") or name.replace("_", " ").title())[:80],
                "description": description[:500],
                "method": method.upper(),
                "path": path,
                "parameters": _params_from_operation(
                    spec, path_item, operation, warnings, op_label
                ),
            }
            definition["endpoints"].append(endpoint)

    if total_ops > len(definition["endpoints"]):
        warnings.append(
            f"Spec had {total_ops} operations; imported the first {len(definition['endpoints'])} "
            f"(cap {max_endpoints}). Edit the plugin to add more."
        )

    return definition, warnings
