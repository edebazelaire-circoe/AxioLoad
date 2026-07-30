from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from .api import create_app
from .operations import backup_all, restore_all
from .persistence import TenantRegistry


def main() -> None:
    parser = argparse.ArgumentParser(prog="pallet-optimizer")
    parser.add_argument("--data-dir", default="data")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    tenant = sub.add_parser("create-tenant")
    tenant.add_argument("tenant_id"); tenant.add_argument("name")
    key = sub.add_parser("issue-api-key")
    key.add_argument("tenant_id"); key.add_argument("--label", default="default")
    user = sub.add_parser("create-user")
    user.add_argument("tenant_id"); user.add_argument("email"); user.add_argument("password")
    user.add_argument("--role", choices=["operator", "company_admin"], default="operator")
    stats = sub.add_parser("stats"); stats.add_argument("tenant_id")
    backup = sub.add_parser("backup"); backup.add_argument("backup_dir")
    restore = sub.add_parser("restore"); restore.add_argument("backup_path"); restore.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    registry = TenantRegistry(Path(args.data_dir))
    if args.command == "serve":
        uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port)
    elif args.command == "create-tenant":
        path = registry.create_tenant(args.tenant_id, args.name)
        print(json.dumps({"tenant_id": args.tenant_id, "database": str(path)}, ensure_ascii=False))
    elif args.command == "issue-api-key":
        print(registry.issue_api_key(args.tenant_id, args.label))
    elif args.command == "create-user":
        print(registry.create_user(args.tenant_id, args.email, args.password, args.role))
    elif args.command == "stats":
        print(json.dumps(registry.usage_stats(args.tenant_id), ensure_ascii=False, indent=2))
    elif args.command == "backup":
        print(backup_all(registry, args.backup_dir))
    elif args.command == "restore":
        print(restore_all(args.backup_path, args.data_dir, overwrite=args.overwrite).data_dir)


if __name__ == "__main__":
    main()
