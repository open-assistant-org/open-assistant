"""Browser tool request models."""

from typing import Optional

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
