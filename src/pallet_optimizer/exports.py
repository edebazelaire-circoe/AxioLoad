from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from PIL import Image
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PACKAGE_ROOT = Path(__file__).resolve().parent
BRAND_LOGO = PACKAGE_ROOT / "static" / "brand" / "axioload-horizontal-dark.png"
NAVY = (6 / 255, 59 / 255, 91 / 255)
TEAL = (22 / 255, 184 / 255, 176 / 255)
MUTED = (82 / 255, 108 / 255, 126 / 255)


def _solution(run: dict[str, Any], index: int = 0) -> dict[str, Any]:
    solutions = run["result"].get("solutions", [])
    if not solutions:
        raise ValueError("run has no solution")
    if index < 0 or index >= len(solutions):
        raise ValueError("unknown solution index")
    return solutions[index]


def _best_solution(run: dict[str, Any]) -> dict[str, Any]:
    return _solution(run, 0)


def export_json(run: dict[str, Any]) -> bytes:
    return json.dumps(run, ensure_ascii=False, indent=2).encode("utf-8")


def _placement_rows(run: dict[str, Any], solution_index: int = 0) -> list[dict[str, Any]]:
    solution = _solution(run, solution_index)
    rows = []
    for vehicle_index, plan in enumerate(solution["vehicle_plans"], start=1):
        for p in plan["placements"]:
            rows.append({
                "method_code": solution.get("method_code", ""),
                "method_name": solution.get("method_name", ""),
                "vehicle": vehicle_index,
                "vehicle_version": plan["vehicle_version_id"],
                "item_id": p["item_id"],
                "source_id": p["source_id"],
                "destination": p["destination"],
                "delivery_order": p["delivery_order"],
                "x_mm": p["x_mm"], "y_mm": p["y_mm"], "z_mm": p["z_mm"],
                "orientation_deg": p["orientation_deg"],
                "length_mm": p["actual_length_mm"], "width_mm": p["actual_width_mm"],
                "height_mm": p["actual_height_mm"], "weight_kg": p["weight_kg"],
                "occupied_length_m": plan["occupied_length_m"],
                "linear_meters": plan["linear_meters"],
            })
    return rows


def export_csv(run: dict[str, Any]) -> bytes:
    rows = _placement_rows(run)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def export_xlsx(run: dict[str, Any]) -> bytes:
    rows = _placement_rows(run)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Plan de chargement"
    sheet.append(list(rows[0]))
    for row in rows:
        sheet.append(list(row.values()))
    summary = workbook.create_sheet("Synthèse")
    solution = _best_solution(run)
    summary.append(["Run", run["id"]])
    summary.append(["Statut", run["status"]])
    summary.append(["Méthode de calcul", solution.get("method_name", "Méthode historique")])
    summary.append(["Nombre de véhicules", solution["vehicle_count"]])
    summary.append(["Mètres linéaires", solution["total_linear_meters"]])
    summary.append(["Longueur réellement occupée (m)", solution["occupied_length_m"]])
    summary.append([])
    summary.append(["Véhicule", "Nom", "Longueur occupée (m)", "Mètres linéaires"])
    for index, plan in enumerate(solution["vehicle_plans"], start=1):
        summary.append([index, plan["vehicle_name"], plan["occupied_length_m"], plan["linear_meters"]])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _fit_image(image: ImageReader, max_width: float, max_height: float) -> tuple[float, float]:
    image_width, image_height = image.getSize()
    ratio = min(max_width / image_width, max_height / image_height)
    return image_width * ratio, image_height * ratio


def _split_vehicle_images(plan_image_png: bytes | None, vehicle_count: int) -> list[bytes | None]:
    if not plan_image_png:
        return [None] * vehicle_count
    try:
        source = Image.open(io.BytesIO(plan_image_png)).convert("RGB")
        if vehicle_count <= 1:
            return [plan_image_png]
        cell_height = source.height / vehicle_count
        output: list[bytes | None] = []
        for index in range(vehicle_count):
            top = round(index * cell_height)
            bottom = round((index + 1) * cell_height)
            crop = source.crop((0, top, source.width, bottom))
            binary = io.BytesIO()
            crop.save(binary, format="PNG")
            output.append(binary.getvalue())
        return output
    except Exception:
        return [plan_image_png] + [None] * max(0, vehicle_count - 1)


def _draw_vehicle_header(pdf: canvas.Canvas, width: float, height: float, vehicle_index: int, plan: dict[str, Any]) -> float:
    pdf.setFillColorRGB(*NAVY)
    pdf.rect(0, height - 64, width, 64, stroke=0, fill=1)
    if BRAND_LOGO.exists():
        pdf.drawImage(str(BRAND_LOGO), 28, height - 54, width=155, height=38, preserveAspectRatio=True, mask="auto")
    else:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(28, height - 40, "AxioLoad")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawRightString(width - 28, height - 33, f"Véhicule {vehicle_index} · {plan['vehicle_name']}")
    return height - 82


def _draw_manifest_table(pdf: canvas.Canvas, width: float, height: float, plan: dict[str, Any], start_y: float) -> None:
    y = start_y
    pdf.setFillColorRGB(*NAVY)
    pdf.setFont("Helvetica-Bold", 9)
    headers = ((30, "Référence"), (145, "Client"), (300, "Dimensions L × l × H"), (480, "Poids"), (565, "Gerbé"))
    for x, label in headers:
        pdf.drawString(x, y, label)
    y -= 8
    pdf.setStrokeColorRGB(.78, .86, .9)
    pdf.line(28, y, width - 28, y)
    y -= 12
    for placement in plan.get("placements", []):
        if y < 35:
            pdf.showPage()
            y = height - 42
            pdf.setFillColorRGB(*NAVY)
            pdf.setFont("Helvetica-Bold", 9)
            for x, label in headers:
                pdf.drawString(x, y, label)
            y -= 18
        pdf.setFillColorRGB(.08, .18, .23)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(30, y, str(placement.get("item_id") or placement.get("source_id") or "")[:22])
        pdf.drawString(145, y, str(placement.get("destination") or "")[:28])
        pdf.drawString(
            300,
            y,
            f"{placement.get('actual_length_mm', 0)} × {placement.get('actual_width_mm', 0)} × {placement.get('actual_height_mm', 0)} mm",
        )
        pdf.drawString(480, y, f"{float(placement.get('weight_kg', 0)):.1f} kg")
        pdf.drawString(565, y, "Oui" if float(placement.get("z_mm", 0)) > 0 else "Non")
        y -= 12


def export_pdf(
    run: dict[str, Any],
    plan_image_png: bytes | None = None,
    solution_index: int = 0,
    vehicle_index: int = 0,
    vehicle_dimensions: dict[str, Any] | None = None,
) -> bytes:
    del vehicle_index, vehicle_dimensions
    output = io.BytesIO()
    page = landscape(A4)
    pdf = canvas.Canvas(output, pagesize=page)
    width, height = page
    solution = _solution(run, solution_index)
    plans = solution.get("vehicle_plans", [])
    if not plans:
        raise ValueError("run has no vehicle plan")
    images = _split_vehicle_images(plan_image_png, len(plans))
    pdf.setTitle(f"AxioLoad - Plan de chargement {run['id']}")

    for index, plan in enumerate(plans, start=1):
        if index > 1:
            pdf.showPage()
        y = _draw_vehicle_header(pdf, width, height, index, plan)
        image_bytes = images[index - 1] if index - 1 < len(images) else None
        if image_bytes:
            try:
                image = ImageReader(io.BytesIO(image_bytes))
                image_width, image_height = _fit_image(image, width - 56, 300)
                image_x = (width - image_width) / 2
                image_y = y - image_height
                pdf.setStrokeColorRGB(*TEAL)
                pdf.roundRect(image_x - 3, image_y - 3, image_width + 6, image_height + 6, 6, stroke=1, fill=0)
                pdf.drawImage(image, image_x, image_y, width=image_width, height=image_height, preserveAspectRatio=True, mask="auto")
                y = image_y - 18
            except Exception:
                pdf.setFillColorRGB(*MUTED)
                pdf.setFont("Helvetica", 8)
                pdf.drawString(30, y, "Le plan 3D de ce véhicule n’a pas pu être intégré.")
                y -= 16
        pdf.setFillColorRGB(*NAVY)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(30, y, "Liste des colis")
        y -= 18
        _draw_manifest_table(pdf, width, height, plan, y)

    pdf.save()
    return output.getvalue()
