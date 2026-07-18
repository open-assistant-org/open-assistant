"""Pydantic request models for the plugin-builder tools.

The Field descriptions are read by the LLM — they describe what each parameter expects and
how the tool behaves when information is missing.
"""

from typing import Optional

from pydantic import BaseModel, Field


class InstallPluginRequest(BaseModel):
    """Install a plugin from a URL (OpenAPI/Swagger spec or plugin JSON) or from a JSON string.

    Provide exactly one of ``source_url`` or ``definition_json``.  If neither is given the
    tool returns a ``needs_input`` status listing what to provide.  If the source URL points to
    an HTML docs page the tool returns ``needs_input`` with a message telling you to use the
    browser/web-search tools to locate the raw OpenAPI JSON, then retry with that URL or paste
    the JSON directly.  All conversion warnings and the post-install connectivity/auth test are
    included in the response so you can relay them to the user.
    """

    source_url: Optional[str] = Field(
        None,
        description=(
            "A URL that returns the raw plugin or OpenAPI/Swagger JSON when fetched. "
            "For OpenAPI/Swagger specs the tool converts them automatically. "
            "If you only have a link to an HTML documentation page, use the browser tool to find "
            "the actual JSON spec URL first (look for links to openapi.json, swagger.json, or "
            "api-docs endpoints), then pass that URL here."
        ),
    )
    definition_json: Optional[str] = Field(
        None,
        description=(
            "A complete Open Assistant plugin definition as a JSON string. "
            "Use this when you have already read and assembled the plugin JSON manually. "
            "Mutually exclusive with source_url — provide only one."
        ),
    )
    base_url_override: Optional[str] = Field(
        None,
        description=(
            "Override the base URL when converting from an OpenAPI spec that lacks a servers "
            "entry, or whose server URL contains unexpanded template variables. "
            "Example: 'https://api.example.com/v2'. Only used for OpenAPI conversion."
        ),
    )
    plugin_id_override: Optional[str] = Field(
        None,
        description=(
            "Override the auto-derived plugin id (slugified from the spec title). "
            "Must match ^[a-z][a-z0-9_]*$. Use when the generated id is unclear or collides. "
            "Only used for OpenAPI conversion."
        ),
    )


class InspectApiSourceRequest(BaseModel):
    """Fetch a URL and analyse its contents WITHOUT installing anything.

    Use this to find out the detected format, candidate base URL, auth scheme, and endpoint
    list — and exactly what information is still missing — before committing to an install.
    A good workflow when you only have a service name and not a spec URL:
    1. Use web_search to find '{service name} openapi.json' or '{service name} swagger'.
    2. Use browse_page (or browse_url) to open the docs and look for a link to the JSON spec.
    3. Call inspect_api_source with the candidate spec URL.
    4. Review what's missing, fill gaps, then call install_plugin.
    """

    source_url: str = Field(
        ...,
        description=(
            "URL to fetch and analyse. Can be an OpenAPI/Swagger JSON spec URL, an already-formed "
            "plugin-definition JSON URL, or even an HTML docs page (in which case the response "
            "lists obvious spec-link candidates found in the page body)."
        ),
    )


class TestPluginConnectionRequest(BaseModel):
    """Test connectivity and auth for an already-installed plugin.

    Sends an authenticated HEAD request to the plugin's base URL and reports success or the
    reason for failure.  Note: a status below 500 is counted as 'reachable' — so a 401 or 403
    means the server is up but the credentials are likely wrong or missing.  Enter credentials
    in Settings → Plugins → (plugin name), then call this tool again.
    """

    plugin_id: str = Field(
        ...,
        description=(
            "The id of an installed plugin (the snake_case identifier, e.g. 'toggl' or "
            "'azure_devops'). Find installed plugin ids in Settings → Plugins or by asking "
            "the user which integration they want to test."
        ),
    )
