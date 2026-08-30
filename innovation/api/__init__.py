"""Front Door HTTP API. Every capability of the system is reachable through it."""

from innovation.api.app import create_app

__all__ = ["create_app"]
