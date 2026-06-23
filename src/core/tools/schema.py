"""Tool schema generation for LLM function calling."""

from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, ConfigDict


class ToolParameter(BaseModel):
    """Represents a tool parameter."""

    name: str
    type: str
    description: Optional[str] = None
    required: bool = True
    enum: Optional[List[Any]] = None


class ToolSchema(BaseModel):
    """OpenAI-compatible tool schema."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema format
    parameters_model: Optional[Type[BaseModel]] = None  # Original Pydantic model class

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _sanitize_property(prop: Dict[str, Any], defs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a single JSON Schema property for broad LLM compatibility.

    Gemini (and some other providers) do not support ``anyOf``, ``oneOf``,
    ``$ref``, or ``$defs`` in function-call parameter schemas.  This helper
    resolves those constructs into plain JSON Schema that every provider
    can consume.
    """
    prop = dict(prop)  # shallow copy

    # Resolve $ref first
    if "$ref" in prop:
        ref_path = prop.pop("$ref")  # e.g. "#/$defs/Foo"
        ref_name = ref_path.rsplit("/", 1)[-1]
        if ref_name in defs:
            resolved = dict(defs[ref_name])
            resolved.update({k: v for k, v in prop.items() if k != "$ref"})
            prop = resolved

    # Flatten anyOf produced by Optional[T] — picks the non-null branch
    if "anyOf" in prop:
        non_null = [b for b in prop["anyOf"] if b != {"type": "null"}]
        if len(non_null) == 1:
            branch = dict(non_null[0])
            # Resolve nested $ref inside the branch
            if "$ref" in branch:
                ref_name = branch["$ref"].rsplit("/", 1)[-1]
                if ref_name in defs:
                    branch = dict(defs[ref_name])
            # Carry over description / default from the wrapper
            for key in ("description", "default"):
                if key in prop and key not in branch:
                    branch[key] = prop[key]
            prop = branch
        else:
            # Multiple non-null branches — drop anyOf and fall back to object
            prop.pop("anyOf")
            prop.setdefault("type", "object")

    # Strip fields that add noise and aren't needed by LLM providers
    prop.pop("title", None)
    prop.pop("$defs", None)

    # Recursively sanitize nested object properties
    if prop.get("type") == "object" and "properties" in prop:
        prop["properties"] = {k: _sanitize_property(v, defs) for k, v in prop["properties"].items()}

    # Recursively sanitize array items
    if prop.get("type") == "array" and "items" in prop:
        prop["items"] = _sanitize_property(prop["items"], defs)

    return prop


def pydantic_to_json_schema(model: type[BaseModel]) -> Dict[str, Any]:
    """
    Convert Pydantic model to JSON schema for function parameters.

    The resulting schema is sanitized to remove ``anyOf``, ``$ref``, and
    ``$defs`` constructs that are not supported by all LLM providers
    (notably Gemini).

    Args:
        model: Pydantic model class

    Returns:
        JSON schema dict compatible with OpenAI, Gemini, and other providers
    """
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})

    properties = {k: _sanitize_property(v, defs) for k, v in schema.get("properties", {}).items()}

    return {
        "type": "object",
        "properties": properties,
        "required": schema.get("required", []),
    }


def create_tool_schema(
    name: str,
    description: str,
    parameters_model: Optional[type[BaseModel]] = None,
    parameters_schema: Optional[Dict[str, Any]] = None,
) -> ToolSchema:
    """
    Create tool schema from Pydantic model or raw schema.

    Args:
        name: Tool name (e.g., "google_send_email")
        description: What the tool does
        parameters_model: Pydantic model for parameters
        parameters_schema: Raw JSON schema (if no Pydantic model)

    Returns:
        ToolSchema instance
    """
    if parameters_model:
        params = pydantic_to_json_schema(parameters_model)
    elif parameters_schema:
        params = parameters_schema
    else:
        params = {"type": "object", "properties": {}}

    return ToolSchema(
        name=name,
        description=description,
        parameters=params,
        parameters_model=parameters_model,
    )
