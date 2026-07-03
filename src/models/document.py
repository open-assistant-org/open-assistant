"""Document generation request models."""

from typing import Optional

from pydantic import BaseModel, Field


class ComposeDocumentRequest(BaseModel):
    """Request model for AI-powered document composition with planning and review."""

    topic: str = Field(..., description="What to write about (e.g. 'Guide to setting up Proxmox')")
    instructions: str = Field(
        ...,
        description="Tone, audience, length, format, and key points to cover "
        "(e.g. 'Write a detailed technical guide for beginners, ~2000 words')",
    )
    context: Optional[str] = Field(
        "",
        description="Research findings, reference material, or background information to incorporate",
    )
    format: Optional[str] = Field(
        "markdown",
        description="Output format: 'markdown' or 'plain'",
    )
    length: Optional[str] = Field(
        "short",
        description=(
            "Output length: 'short' (default, single-pass write), "
            "'medium' (section-by-section, ~6-8 sections with good detail), "
            "or 'long' (section-by-section, 8-12 sections with in-depth coverage). "
            "medium and long overcome LLM token limits by writing each section individually."
        ),
    )


class CreateDocxRequest(BaseModel):
    """Request model for creating a .docx document."""

    filename: str = Field(
        ..., description="Output filename (e.g. 'report.docx'). Will be saved to temp storage."
    )
    content: str = Field(
        ...,
        description="Document content in markdown format. Supports headings (# ## ###), "
        "bullet lists (- item), numbered lists (1. item), bold (**text**), "
        "italic (*text*), and paragraphs separated by blank lines.",
    )
    title: Optional[str] = Field(
        None, description="Optional document title (added as a large heading at the top)"
    )


class CreatePdfRequest(BaseModel):
    """Request model for creating a PDF from markdown content."""

    filename: str = Field(
        ..., description="Output filename (e.g. 'report.pdf'). Will be saved to temp storage."
    )
    content: str = Field(
        ...,
        description="Document content in markdown format. Supports headings (# ## ###), "
        "bullet lists (- item), numbered lists (1. item), bold (**text**), "
        "italic (*text*), code blocks (```), blockquotes (>), horizontal rules (---), "
        "and paragraphs separated by blank lines.",
    )
    title: Optional[str] = Field(
        None, description="Optional document title (added as a large heading at the top)"
    )


class CreateHtmlRequest(BaseModel):
    """Request model for LLM-generated HTML page."""

    prompt: str = Field(
        ...,
        description="Plain-English description of the HTML page to generate "
        "(e.g. 'A sales dashboard with a bar chart and summary KPI cards').",
    )
    filename: str = Field(
        ..., description="Output filename (e.g. 'dashboard.html'). Saved to temp storage."
    )
    context: Optional[str] = Field(
        None,
        description="Optional data or content to embed in the page "
        "(e.g. CSV data, JSON, text to display). The LLM will incorporate it.",
    )


class StoreArtifactRequest(BaseModel):
    """Request model for persisting a generated file into the artifact store."""

    source_path: str = Field(
        ...,
        description="Path to the file to persist — typically the 'filepath' returned by "
        "create_html, create_pdf, create_docx, or a file written by python_execute "
        "(e.g. '/app/tmp/assistant_docs/dashboard.html').",
    )
    title: Optional[str] = Field(
        None,
        description="Optional human-readable title shown in the Artifacts tab "
        "(e.g. 'Q3 Sales Dashboard').",
    )
    make_public: bool = Field(
        False,
        description="If true, the artifact gets a permanent public shareable link immediately. "
        "If false (default), it stays private and can only be shared via a temporary "
        "5-minute link created from the Artifacts tab.",
    )
