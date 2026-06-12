"""Entrypoint ASGI: `uv run uvicorn main:app --port 8080`."""

from juscraper_mcp.server import create_app
from juscraper_mcp.settings import settings

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
