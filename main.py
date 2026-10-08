"""Compatibility entrypoint: uvicorn main:app; implementation in app.server."""

from app.server import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from app.core.config import get_settings

    settings = get_settings()
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT)
