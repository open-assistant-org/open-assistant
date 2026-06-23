"""Screenshot capture and optimization for vision LLM processing."""

import base64
import io
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScreenshotConfig:
    """Configuration for screenshot capture and optimization."""

    format: str = "jpeg"
    quality: int = 85
    max_width: int = 1280
    max_height: int = 720


@dataclass
class Screenshot:
    """Represents a captured and optimized screenshot."""

    data: bytes
    width: int
    height: int
    format: str
    url: str
    title: str
    timestamp: str

    @property
    def base64(self) -> str:
        """Return base64-encoded screenshot data."""
        return base64.b64encode(self.data).decode("utf-8")

    @property
    def size_kb(self) -> float:
        """Return screenshot size in kilobytes."""
        return len(self.data) / 1024

    @property
    def media_type(self) -> str:
        """Return the MIME type for the screenshot format."""
        if self.format == "jpeg":
            return "image/jpeg"
        return f"image/{self.format}"

    def to_vision_payload(self) -> dict:
        """
        Format screenshot for vision LLM consumption.

        Returns:
            Dict suitable for inclusion in a vision LLM message.
        """
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.media_type,
                "data": self.base64,
            },
        }

    def to_summary(self) -> dict:
        """
        Return a metadata summary (without image data) for logging.

        Returns:
            Dict with screenshot metadata.
        """
        return {
            "url": self.url,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_kb": round(self.size_kb, 1),
            "timestamp": self.timestamp,
        }


def optimize_screenshot(
    raw_bytes: bytes,
    config: ScreenshotConfig,
) -> bytes:
    """
    Optimize a screenshot for vision LLM processing.

    Resizes if larger than max dimensions and compresses to target quality.
    Requires Pillow (PIL) for image processing.

    Args:
        raw_bytes: Raw screenshot bytes (PNG from Playwright).
        config: Screenshot optimization configuration.

    Returns:
        Optimized screenshot bytes in the configured format.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; returning raw screenshot without optimization")
        return raw_bytes

    img = Image.open(io.BytesIO(raw_bytes))
    original_size = len(raw_bytes)

    # Resize if larger than max dimensions, preserving aspect ratio
    if img.width > config.max_width or img.height > config.max_height:
        img.thumbnail((config.max_width, config.max_height), Image.LANCZOS)
        logger.debug(f"Resized screenshot to {img.width}x{img.height}")

    # Convert RGBA to RGB for JPEG
    if config.format == "jpeg" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    output = io.BytesIO()
    if config.format == "jpeg":
        img.save(output, format="JPEG", quality=config.quality, optimize=True)
    else:
        img.save(output, format=config.format.upper())

    optimized = output.getvalue()
    logger.debug(
        f"Screenshot optimized: {original_size / 1024:.1f}KB -> {len(optimized) / 1024:.1f}KB "
        f"({config.format}, quality={config.quality})"
    )
    return optimized
