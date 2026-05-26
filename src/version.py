"""SkinLens Version Information

This module provides version information for the SkinLens project.
All version information should be sourced from this single file to ensure consistency.
"""
from __future__ import annotations

__version__ = "1.0.0"
__project_name__ = "SkinLens"
__project_description__ = "AI-powered skin analysis engine"


def get_version() -> str:
    """Return the current version string."""
    return __version__


def get_project_name() -> str:
    """Return the project name."""
    return __project_name__


def get_version_info() -> Dict[str, str]:
    """Return version information as a dictionary."""
    return {
        "name": __project_name__,
        "version": __version__,
        "description": __project_description__,
    }


def __repr__() -> str:
    return f"{__project_name__} v{__version__}"
