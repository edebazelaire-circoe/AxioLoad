from __future__ import annotations

from typing import Any

from .document_control import DocumentControlRepository


def install_company_ai_privacy() -> None:
    current = DocumentControlRepository.get_ai_config
    if getattr(current, "_axioload_company_ai_privacy", False):
        return

    def get_ai_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        result = current(self, tenant_id, include_secret=include_secret)
        if not include_secret:
            result["key_hint"] = ""
        return result

    get_ai_config._axioload_company_ai_privacy = True  # type: ignore[attr-defined]
    DocumentControlRepository.get_ai_config = get_ai_config  # type: ignore[method-assign]
