"""Browser tool request models."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BrowseUrlRequest(BaseModel):
    """Request model for browsing a URL."""

    url: str = Field(..., description="The URL to navigate to")
    wait_until: Optional[str] = Field(
        "domcontentloaded",
        description="Wait condition: 'load', 'domcontentloaded', 'networkidle'",
    )


class BrowseGetTreeRequest(BaseModel):
    """Request model for getting accessibility tree."""

    mode: Optional[str] = Field(
        "interactive",
        description="Tree filter mode: 'full' (all elements), 'interactive' (links/buttons/inputs), 'forms' (form fields only)",
    )


class BrowseActionRequest(BaseModel):
    """Request model for executing action by reference."""

    ref_id: int = Field(..., description="Element reference ID from accessibility tree")
    action: str = Field(..., description="Action: 'click', 'type', 'focus', 'check', 'uncheck'")
    value: Optional[str] = Field(None, description="Value for 'type' action")


class BrowseScrollRequest(BaseModel):
    """Request model for scrolling the page."""

    direction: str = Field("down", description="Scroll direction: 'up' or 'down'")
    amount: int = Field(3, description="Number of scroll ticks (each ~100px)", ge=1, le=20)


class BrowseExtractRequest(BaseModel):
    """Request model for extracting text from the current page."""

    pass  # No parameters needed


class BrowseFetchRequest(BaseModel):
    """Request model for fetching content using Scrapling."""

    url: str = Field(..., description="The URL to fetch content from")
    mode: Optional[str] = Field(
        None,
        description=(
            "Fetcher mode: 'http' (fast TLS-impersonated HTTP, no JS), "
            "'stealth' (Camoufox with Cloudflare bypass), "
            "'dynamic' (Playwright with anti-detection for JS-heavy pages). "
            "Defaults to server setting (usually 'http')."
        ),
    )
    selector: Optional[str] = Field(
        None,
        description="CSS selector to extract specific content from the page",
    )
    wait_for: Optional[str] = Field(
        None,
        description="CSS selector to wait for before extraction (only used with 'dynamic' mode)",
    )


# ----------------------------------------------------------------------------
# Authenticated sessions (cookies). Write-only: responses never carry values.
# ----------------------------------------------------------------------------


class BrowserSessionCreate(BaseModel):
    """Create a saved browser login from a cookie export."""

    name: str = Field(..., description="Label, e.g. 'Personal Gmail' (unique, max 64 chars)")
    format: Literal["auto", "playwright", "cookie_editor", "netscape", "header"] = Field(
        "auto", description="Export format; 'auto' detects it"
    )
    payload: str = Field(
        ..., repr=False, description="The pasted export (cookies and optionally localStorage)"
    )
    domain: Optional[str] = Field(None, description="Required for the raw 'Cookie:' header format")
    persist_updates: bool = Field(
        True, description="Save cookies the site rotates while the browser is in use"
    )


class BrowserSessionUpdate(BaseModel):
    """Change a saved login. Supplying `payload` replaces its cookies."""

    name: Optional[str] = None
    enabled: Optional[bool] = None
    persist_updates: Optional[bool] = None
    format: Literal["auto", "playwright", "cookie_editor", "netscape", "header"] = "auto"
    payload: Optional[str] = Field(None, repr=False)
    domain: Optional[str] = None


class BrowserSessionTestRequest(BaseModel):
    """Open a page with one saved login to check it still works."""

    url: str = Field(..., description="An http(s) page that requires the login")


class BrowserSessionMetadata(BaseModel):
    """Non-secret summary of a saved login (no cookie names or values)."""

    id: str
    name: str
    enabled: bool
    persist_updates: bool
    domains: List[str]
    cookie_count: int
    expired_count: int
    earliest_expiry: Optional[str] = None
    latest_expiry: Optional[str] = None
    has_local_storage: bool
    created_at: str
    updated_at: str


class BrowserSessionResponse(BaseModel):
    """A saved login plus any import warnings."""

    session: BrowserSessionMetadata
    warnings: List[str] = Field(default_factory=list)


class BrowserSessionTestResponse(BaseModel):
    """Where a test navigation landed. No page content, no cookies."""

    final_url: str
    title: str
    redirected_to_login: bool
