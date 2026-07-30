from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .persistence import TenantRegistry


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def backup_all(registry: TenantRegistry, backup_dir: str | Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = Path(backup_dir) / f"plo-backup-{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    _sqlite_backup(registry.registry_path, target / "registry.sqlite")
    with sqlite3.connect(registry.registry_path) as db:
        rows = db.execute("SELECT id, db_path FROM tenants").fetchall()
    manifest: dict[str, Any] = {"created_at": stamp, "tenants": []}
    for tenant_id, db_path in rows:
        destination = target / "tenants" / f"{tenant_id}.sqlite"
        _sqlite_backup(Path(db_path), destination)
        manifest["tenants"].append({"id": tenant_id, "file": str(destination.relative_to(target))})
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def restore_all(backup_path: str | Path, data_dir: str | Path, *, overwrite: bool = False) -> TenantRegistry:
    source = Path(backup_path)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    target = Path(data_dir)
    if target.exists() and any(target.iterdir()):
        if not overwrite:
            raise FileExistsError("target data directory is not empty")
        shutil.rmtree(target)
    (target / "tenants").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "registry.sqlite", target / "registry.sqlite")
    for tenant in manifest["tenants"]:
        shutil.copy2(source / tenant["file"], target / "tenants" / f"{tenant['id']}.sqlite")
    # Rewrite absolute tenant paths for the restored location.
    with sqlite3.connect(target / "registry.sqlite") as db:
        for tenant in manifest["tenants"]:
            db.execute("UPDATE tenants SET db_path=? WHERE id=?",
                       (str(target / "tenants" / f"{tenant['id']}.sqlite"), tenant["id"]))
    return TenantRegistry(target)
