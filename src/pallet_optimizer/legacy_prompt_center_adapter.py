from __future__ import annotations

from fastapi import FastAPI

from . import prompt_center_system


def install_legacy_prompt_center_system() -> None:
    """Preserve the legacy FastAPI installer until prompt routes become explicit."""

    prompt_center_system._original_fastapi_init = FastAPI.__init__
    prompt_center_system.install_prompt_center_system()
