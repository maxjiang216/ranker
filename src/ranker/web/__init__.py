"""Localhost web app for running ranking sessions (optional extra: ``ranker[web]``)."""

from .app import create_app

__all__ = ["create_app"]
