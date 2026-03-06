"""Compatibility shim: keep imports stable while settings live in app/config."""

from app.config.settings import TOKEN, read_bool, read_int, read_required_secret, read_str

__all__ = [
    "TOKEN",
    "read_bool",
    "read_int",
    "read_required_secret",
    "read_str",
]
