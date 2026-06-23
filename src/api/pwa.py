"""PWA (Progressive Web App) endpoints for manifest and app configuration."""

from typing import Dict
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src import __version__

router = APIRouter(prefix="/api/pwa", tags=["pwa"])


@router.get("/manifest.json")
async def get_manifest() -> JSONResponse:
    """
    Serve the web app manifest dynamically with current version.

    Returns:
        Web app manifest with app metadata and icons
    """
    manifest = {
        "name": "Open Assistant",
        "short_name": "Assistant",
        "description": "AI-powered personal assistant for task automation and integration",
        "version": __version__,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#00ff00",
        "orientation": "any",
        "scope": "/",
        "icons": [
            {
                "src": "/static/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/robot-logo.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
        "screenshots": [],
        "shortcuts": [
            {
                "name": "New Chat",
                "short_name": "Chat",
                "description": "Start a new conversation",
                "url": "/?action=new-chat",
                "icons": [
                    {
                        "src": "/static/icons/icon-192x192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
            {
                "name": "Settings",
                "short_name": "Settings",
                "description": "Open settings",
                "url": "/settings",
                "icons": [
                    {
                        "src": "/static/icons/icon-192x192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
        ],
        "categories": ["productivity", "utilities"],
        "prefer_related_applications": False,
    }

    return JSONResponse(
        content=manifest,
        headers={"Content-Type": "application/manifest+json", "Cache-Control": "no-cache"},
    )
