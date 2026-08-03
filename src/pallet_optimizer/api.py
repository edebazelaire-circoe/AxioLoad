from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .admin_api import register_admin_routes
from .admin_service import AdminRepository, WebContext
from .catalog import default_vehicle_catalog, vehicle_to_payload
from .domain import DomainError, Severity, to_primitive
from .engine import OptimizationEngine
from .exports import export_csv, export_json, export_pdf, export_xlsx
from .import_template import build_import_template_xlsx
from .normalization import normalize_payload, payload_from_csv, payload_from_xlsx
from .persistence import TenantRegistry, TenantRunRepository
from .platform import build_default_module_registry
from .route_loading_validation import compare_checked, optimise_checked
from .route_optimization import RouteInputError, geocode as route_geocode_service
from .service import OptimizationService
from .stacking import diagnostics_for_payload, install_stacking
from .total_metrics import install_total_metrics
from .total_optimization import TotalOptimizationError
from .total_preprocessing import optimise_total_prepared
from .version import APP_VERSION
from .workflow_history import install_history_metadata, validate_optimization

PACKAGE_ROOT = Path(__file__).resolve().parent


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    install_history_metadata()
    install_stacking()
    install_total_metrics()

    data_path = Path(data_dir or os.getenv("PLO_DATA_DIR", PACKAGE_ROOT / "data"))
    registry = TenantRegistry(data_path)
    registry.create_tenant("local", "Entreprise locale")
    repository = TenantRunRepository(registry)
    service = OptimizationService(OptimizationEngine(), repository, registry.list_vehicles)
    admin = AdminRepository(registry)
    module_registry = build_default_module_registry()

    app = FastAPI(title="AxioLoad", version=APP_VERSION)
    app.state.registry = registry
    app.state.repository = repository
    app.state.service = service
    app.state.admin = admin
    app.state.module_registry = module_registry
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")
    register_admin_routes(app, admin, templates)

    def web_context(request: Request) -> WebContext:
        return admin.resolve_web_context(
            request.cookies.get("axioload_assistance"),
            request.cookies.get("axioload_session"),
        )

    def read_context(context: WebContext = Depends(web_context)) -> WebContext:
        try:
            admin.assert_company_access(context, write=False)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return context

    def write_context(context: WebContext = Depends(web_context)) -> WebContext:
        try:
            admin.assert_company_access(context, write=True)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return context

    def require_permission(permission_key: str, *, write: bool = False):
        def dependency(context: WebContext = Depends(web_context)) -> WebContext:
            try:
                admin.require_permission(context, permission_key, write=write)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            return context

        return dependency

    @app.get("/api/platform/modules")
    def platform_modules(
        context: WebContext = Depends(read_context),
    ) -> dict[str, Any]:
        if context.is_super_admin:
            company = admin.get_company(context.tenant_id)
            permissions = {key: True for key in company["permissions"]}
        else:
            permissions = admin.effective_permissions(
                context.tenant_id,
                None if context.actor_id == "local-user" else context.actor_id,
            )
        return {
            "version": APP_VERSION,
            "modules": module_registry.manifest(
                permissions,
                is_super_admin=context.is_super_admin,
            ),
        }

    def api_tenant(x_api_key: Annotated[str | None, Header()] = None) -> str:
        if not x_api_key:
            raise HTTPException(401, "X-API-Key header is required")
        tenant_id = admin.resolve_api_key(x_api_key, "results.run")
        if not tenant_id:
            legacy_tenant = registry.resolve_api_key(x_api_key)
            if legacy_tenant == "local":
                tenant_id = legacy_tenant
        if not tenant_id:
            raise HTTPException(401, "Invalid, expired, suspended or unauthorized API key")
        return tenant_id

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        context = web_context(request)
        try:
            vehicles = admin.list_vehicles(context)
        except (KeyError, PermissionError):
            vehicles = [vehicle_to_payload(vehicle) for vehicle in default_vehicle_catalog()]
        rendered = templates.TemplateResponse(
            request,
            "index.html",
            {"vehicles": vehicles, "app_version": APP_VERSION},
        )
        html = (
            rendered.body.decode("utf-8")
            .replace(
                "</head>",
                f'<link rel="stylesheet" href="/static/enhancements.css?v={APP_VERSION}"></head>',
            )
            .replace(
                "</body>",
                f'<script src="/static/enhancements.js?v={APP_VERSION}"></script></body>',
            )
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine_version": OptimizationEngine.version}

    @app.post("/v1/optimizations")
    def public_optimize(payload: dict[str, Any], tenant_id: str = Depends(api_tenant)) -> dict[str, Any]:
        result, run_id = service.execute(payload, tenant_id=tenant_id, interactive=False, channel="api")
        body = to_primitive(result)
        body["run_id"] = run_id
        admin.annotate_run(WebContext(tenant_id, "api", "Clé API", "api"), run_id, payload)
        if result.status.value == "invalid_input":
            raise HTTPException(422, detail=body)
        if result.status.value == "internal_error":
            raise HTTPException(500, detail=body)
        return body

    @app.post("/local/optimize")
    def local_optimize(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("results.run", write=True)),
    ) -> dict[str, Any]:
        result, run_id = service.execute(payload, tenant_id=context.tenant_id, interactive=True)
        body = to_primitive(result)
        body["run_id"] = run_id
        admin.annotate_run(context, run_id, payload)
        return body

    @app.post("/demo/optimize", include_in_schema=False)
    def demo_optimize_compatibility(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("results.run", write=True)),
    ) -> dict[str, Any]:
        return local_optimize(payload, context)

    @app.get("/api/route/geocode")
    def route_geocode(q: str = Query(..., min_length=3, max_length=300)) -> dict[str, Any]:
        try:
            return {"results": route_geocode_service(q)}
        except RouteInputError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, "Le service de géocodage est temporairement indisponible.") from exc

    @app.post("/api/route/compare")
    def route_compare(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("route.run", write=True)),
    ) -> dict[str, Any]:
        try:
            return compare_checked(payload, registry.list_vehicles(context.tenant_id))
        except RouteInputError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(500, f"La comparaison des itinéraires a échoué ({type(exc).__name__}).") from exc

    @app.post("/api/route/optimize")
    def route_optimize(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("route.run", write=True)),
    ) -> dict[str, Any]:
        try:
            return optimise_checked(payload, registry.list_vehicles(context.tenant_id))
        except RouteInputError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(500, f"Le calcul d’itinéraire a échoué ({type(exc).__name__}).") from exc

    @app.post("/api/total/optimize")
    def total_optimize(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("total.run", write=True)),
    ) -> dict[str, Any]:
        try:
            catalog = registry.list_vehicles(context.tenant_id)
            result = optimise_total_prepared(payload, catalog)
            loading = payload.get("loading") if isinstance(payload.get("loading"), dict) else {}
            diagnostics = diagnostics_for_payload(loading, catalog)
            result["stacking_diagnostics"] = [to_primitive(diagnostic) for diagnostic in diagnostics]
            warnings = [diagnostic.message for diagnostic in diagnostics if diagnostic.severity == Severity.WARNING]
            if warnings:
                for solution in result.get("solutions", []):
                    solution.setdefault("warnings", []).extend(
                        message for message in warnings if message not in solution.get("warnings", [])
                    )
            return result
        except TotalOptimizationError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(500, f"L’optimisation totale a échoué ({type(exc).__name__}).") from exc

    @app.get("/api/import/template.xlsx")
    def import_template(
        context: WebContext = Depends(require_permission("data.import")),
    ) -> Response:
        del context
        return Response(
            build_import_template_xlsx(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="axioload-modele-import.xlsx"'},
        )

    @app.post("/api/import/preview")
    async def import_preview(
        file: Annotated[UploadFile, File()],
        vehicle_id: str = Query("semi_trailer"),
        context: WebContext = Depends(require_permission("data.import", write=True)),
    ) -> dict[str, Any]:
        content = await file.read()
        suffix = Path(file.filename or "").suffix.lower()
        base = {"vehicle_policy": {"mode": "forced", "forced_vehicle_id": vehicle_id}}
        try:
            if suffix == ".csv":
                payload = payload_from_csv(content, **base)
            elif suffix == ".xlsx":
                payload = payload_from_xlsx(content, **base)
            else:
                raise HTTPException(415, "Only CSV and XLSX files are supported")
            problem = normalize_payload(payload, catalog=registry.list_vehicles(context.tenant_id))
        except DomainError as exc:
            raise HTTPException(422, detail=to_primitive(exc.diagnostic)) from exc
        return {"payload": payload, "expanded_items": len(problem.items), "diagnostics": []}

    @app.get("/api/vehicles")
    def vehicles_list(
        context: WebContext = Depends(require_permission("vehicles.view")),
    ) -> list[dict[str, Any]]:
        return admin.list_vehicles(context)

    @app.post("/api/vehicles")
    def vehicles_save(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("vehicles.create", write=True)),
    ) -> dict[str, Any]:
        try:
            return admin.save_vehicle(context, payload)
        except DomainError as exc:
            raise HTTPException(422, detail=to_primitive(exc.diagnostic)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/vehicles/{model_id}/duplicate")
    def vehicles_duplicate(
        model_id: str,
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("vehicles.create", write=True)),
    ) -> dict[str, Any]:
        try:
            return admin.duplicate_vehicle(
                context,
                model_id,
                str(payload.get("model_id") or ""),
                str(payload.get("name") or ""),
            )
        except KeyError as exc:
            raise HTTPException(404, "Véhicule inconnu") from exc
        except (ValueError, PermissionError, DomainError) as exc:
            raise HTTPException(422 if not isinstance(exc, PermissionError) else 403, str(exc)) from exc

    @app.delete("/api/vehicles/{model_id}", status_code=204)
    def vehicles_delete(
        model_id: str,
        context: WebContext = Depends(require_permission("vehicles.delete", write=True)),
    ) -> Response:
        try:
            admin.delete_vehicle(context, model_id)
        except KeyError as exc:
            raise HTTPException(404, "Véhicule inconnu") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/vehicles/reset-defaults")
    def vehicles_reset(
        context: WebContext = Depends(write_context),
    ) -> list[dict[str, Any]]:
        if not context.is_super_admin and context.tenant_id != "local":
            raise HTTPException(403, "Seul le super administrateur peut restaurer le catalogue global")
        registry.reset_default_vehicles(context.tenant_id, actor=context.actor_label)
        admin._ensure_vehicle_metadata(context.tenant_id)
        return admin.list_vehicles(context)

    @app.post("/api/history/validate")
    def history_validate(
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("history.validate", write=True)),
    ) -> dict[str, Any]:
        candidate = dict(payload)
        candidate["user"] = context.actor_label
        try:
            run = validate_optimization(repository, context.tenant_id, candidate)
            admin.annotate_run(context, run["id"], candidate.get("request") or {})
            admin.touch_run(context, run["id"], "validated", {"title": candidate.get("title")})
            return repository.get_run(context.tenant_id, run["id"])
        except KeyError as exc:
            raise HTTPException(404, "Calcul inconnu") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/history")
    def history(
        limit: int = 50,
        context: WebContext = Depends(require_permission("history.view")),
    ) -> list[dict[str, Any]]:
        return repository.list_runs(context.tenant_id, limit)

    @app.get("/api/history/{run_id}")
    def history_detail(
        run_id: str,
        context: WebContext = Depends(require_permission("history.view")),
    ) -> dict[str, Any]:
        try:
            return repository.get_run(context.tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc

    @app.delete("/api/history/{run_id}", status_code=204)
    def history_delete(
        run_id: str,
        context: WebContext = Depends(require_permission("history.delete", write=True)),
    ) -> Response:
        try:
            admin.touch_run(context, run_id, "deleted")
            repository.delete_run(context.tenant_id, run_id, actor=context.actor_label)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc
        return Response(status_code=204)

    @app.post("/api/history/{run_id}/export-operational.pdf")
    def history_operational_export(
        run_id: str,
        payload: dict[str, Any],
        context: WebContext = Depends(require_permission("exports.use")),
    ) -> Response:
        try:
            run = repository.get_run(context.tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc
        image_data_url = str(payload.get("image_data_url", ""))
        prefix = "data:image/png;base64,"
        if not image_data_url.startswith(prefix):
            raise HTTPException(422, "Une capture PNG de la vue 3D est requise")
        encoded = image_data_url[len(prefix) :]
        if len(encoded) > 16_000_000:
            raise HTTPException(413, "La capture 3D dépasse la taille autorisée")
        try:
            image_png = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "Capture 3D PNG invalide") from exc
        if not image_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(422, "La capture transmise n'est pas un PNG")
        solution_index = int(payload.get("solution_index", 0))
        vehicle_index = int(payload.get("vehicle_index", 0))
        try:
            plan = run["result"]["solutions"][solution_index]["vehicle_plans"][vehicle_index]
        except (IndexError, KeyError, TypeError) as exc:
            raise HTTPException(422, "Solution ou véhicule d'export inconnu") from exc
        displayed = payload.get("displayed_metrics") or {}
        for key, stored_key in (("occupied_length_m", "occupied_length_m"), ("linear_meters", "linear_meters")):
            if key in displayed and abs(float(displayed[key]) - float(plan[stored_key])) > 1e-6:
                raise HTTPException(409, "Les métriques affichées ne correspondent pas au plan enregistré")
        dimensions = payload.get("vehicle_dimensions") or None
        if dimensions is not None:
            required = ("interior_length_mm", "interior_width_mm", "interior_height_mm")
            try:
                dimensions = {key: int(dimensions[key]) for key in required}
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(422, "Dimensions du véhicule invalides") from exc
            if any(value <= 0 for value in dimensions.values()):
                raise HTTPException(422, "Dimensions du véhicule invalides")
        try:
            content = export_pdf(
                run,
                image_png,
                solution_index=solution_index,
                vehicle_index=vehicle_index,
                vehicle_dimensions=dimensions,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        registry.audit(context.tenant_id, context.actor_label, "export.operational_pdf", run_id, {})
        admin.touch_run(context, run_id, "exported")
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="axioload-plan-{run_id}.pdf"'},
        )

    @app.get("/api/history/{run_id}/export.{format}")
    def history_export(
        run_id: str,
        format: str,
        context: WebContext = Depends(require_permission("exports.use")),
    ) -> Response:
        try:
            run = repository.get_run(context.tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc
        exporters = {
            "json": (export_json, "application/json"),
            "csv": (export_csv, "text/csv; charset=utf-8"),
            "xlsx": (export_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "pdf": (export_pdf, "application/pdf"),
        }
        if format not in exporters:
            raise HTTPException(404, "Unsupported export format")
        exporter, media_type = exporters[format]
        try:
            content = exporter(run)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        registry.audit(context.tenant_id, context.actor_label, f"export.{format}", run_id, {})
        admin.touch_run(context, run_id, "exported", {"format": format})
        return Response(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="loading-plan-{run_id}.{format}"'},
        )

    return app


app = create_app()
