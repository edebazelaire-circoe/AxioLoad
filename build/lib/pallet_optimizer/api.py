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

from .catalog import default_vehicle_catalog, vehicle_to_payload
from .domain import DomainError, to_primitive
from .engine import OptimizationEngine
from .exports import export_csv, export_json, export_pdf, export_xlsx
from .normalization import normalize_payload, payload_from_csv, payload_from_xlsx
from .persistence import TenantRegistry, TenantRunRepository
from .service import OptimizationService


PACKAGE_ROOT = Path(__file__).resolve().parent


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    data_path = Path(data_dir or os.getenv("PLO_DATA_DIR", PACKAGE_ROOT / "data"))
    registry = TenantRegistry(data_path)
    # The browser application is a local, single-company tool and never requires an API key.
    # API keys remain limited to the optional public /v1 integration endpoint.
    registry.create_tenant("local", "Entreprise locale")
    repository = TenantRunRepository(registry)
    service = OptimizationService(OptimizationEngine(), repository, registry.list_vehicles)

    app = FastAPI(title="AxioLoad", version="0.6.1")
    app.state.registry = registry
    app.state.repository = repository
    app.state.service = service
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")

    def api_tenant(x_api_key: Annotated[str | None, Header()] = None) -> str:
        if not x_api_key:
            raise HTTPException(401, "X-API-Key header is required")
        tenant_id = registry.resolve_api_key(x_api_key)
        if not tenant_id:
            raise HTTPException(401, "Invalid or revoked API key")
        return tenant_id

    def web_tenant() -> str:
        """Tenant used by the local browser UI. No authentication is required."""
        return "local"

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        try:
            vehicles = registry.list_vehicles("local")
        except KeyError:
            vehicles = default_vehicle_catalog()
        response = templates.TemplateResponse(request, "index.html", {
            "vehicles": [vehicle_to_payload(v) for v in vehicles],
            "app_version": OptimizationEngine.version,
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine_version": OptimizationEngine.version}

    @app.post("/v1/optimizations")
    def public_optimize(payload: dict[str, Any], tenant_id: str = Depends(api_tenant)) -> dict[str, Any]:
        result, run_id = service.execute(payload, tenant_id=tenant_id, interactive=False, channel="api")
        body = to_primitive(result)
        body["run_id"] = run_id
        if result.status.value == "invalid_input":
            raise HTTPException(422, detail=body)
        if result.status.value == "internal_error":
            raise HTTPException(500, detail=body)
        return body

    @app.post("/local/optimize")
    def local_optimize(payload: dict[str, Any]) -> dict[str, Any]:
        result, run_id = service.execute(payload, tenant_id="local", interactive=True)
        body = to_primitive(result)
        body["run_id"] = run_id
        return body

    @app.post("/demo/optimize", include_in_schema=False)
    def demo_optimize_compatibility(payload: dict[str, Any]) -> dict[str, Any]:
        # Backward-compatible alias for browsers that still have the V2 JavaScript cached.
        return local_optimize(payload)

    @app.post("/api/import/preview")
    async def import_preview(
        file: Annotated[UploadFile, File()],
        vehicle_id: str = Query("semi_trailer"),
        tenant_id: str = Depends(web_tenant),
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
            problem = normalize_payload(payload, catalog=registry.list_vehicles(tenant_id))
        except DomainError as exc:
            raise HTTPException(422, detail=to_primitive(exc.diagnostic)) from exc
        return {"payload": payload, "expanded_items": len(problem.items), "diagnostics": []}

    @app.get("/api/vehicles")
    def vehicles_list(tenant_id: str = Depends(web_tenant)) -> list[dict[str, Any]]:
        return [vehicle_to_payload(vehicle) for vehicle in registry.list_vehicles(tenant_id)]

    @app.post("/api/vehicles")
    def vehicles_save(payload: dict[str, Any], tenant_id: str = Depends(web_tenant)) -> dict[str, Any]:
        try:
            vehicle = registry.save_vehicle(tenant_id, payload)
        except DomainError as exc:
            raise HTTPException(422, detail=to_primitive(exc.diagnostic)) from exc
        return vehicle_to_payload(vehicle)

    @app.delete("/api/vehicles/{model_id}", status_code=204)
    def vehicles_delete(model_id: str, tenant_id: str = Depends(web_tenant)) -> Response:
        try:
            registry.delete_vehicle(tenant_id, model_id)
        except KeyError as exc:
            raise HTTPException(404, "Véhicule inconnu") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/vehicles/reset-defaults")
    def vehicles_reset(tenant_id: str = Depends(web_tenant)) -> list[dict[str, Any]]:
        return [vehicle_to_payload(vehicle) for vehicle in registry.reset_default_vehicles(tenant_id)]

    @app.get("/api/history")
    def history(tenant_id: str = Depends(web_tenant), limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_runs(tenant_id, limit)

    @app.get("/api/history/{run_id}")
    def history_detail(run_id: str, tenant_id: str = Depends(web_tenant)) -> dict[str, Any]:
        try:
            return repository.get_run(tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc

    @app.delete("/api/history/{run_id}", status_code=204)
    def history_delete(run_id: str, tenant_id: str = Depends(web_tenant)) -> Response:
        try:
            repository.delete_run(tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc
        return Response(status_code=204)

    @app.post("/api/history/{run_id}/export-operational.pdf")
    def history_operational_export(
        run_id: str, payload: dict[str, Any], tenant_id: str = Depends(web_tenant)
    ) -> Response:
        try:
            run = repository.get_run(tenant_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown run") from exc
        image_data_url = str(payload.get("image_data_url", ""))
        prefix = "data:image/png;base64,"
        if not image_data_url.startswith(prefix):
            raise HTTPException(422, "Une capture PNG de la vue 3D est requise")
        encoded = image_data_url[len(prefix):]
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
            solution = run["result"]["solutions"][solution_index]
            plan = solution["vehicle_plans"][vehicle_index]
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
                run, image_png, solution_index=solution_index, vehicle_index=vehicle_index,
                vehicle_dimensions=dimensions,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(
            content, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="axioload-plan-{run_id}.pdf"'},
        )

    @app.get("/api/history/{run_id}/export.{format}")
    def history_export(run_id: str, format: str, tenant_id: str = Depends(web_tenant)) -> Response:
        try:
            run = repository.get_run(tenant_id, run_id)
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
        return Response(content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="loading-plan-{run_id}.{format}"'})

    return app


app = create_app()
