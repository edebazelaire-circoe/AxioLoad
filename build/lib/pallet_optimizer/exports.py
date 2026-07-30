from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PACKAGE_ROOT = Path(__file__).resolve().parent
BRAND_LOGO = PACKAGE_ROOT / "static" / "brand" / "axioload-horizontal-dark.png"
NAVY = (6 / 255, 59 / 255, 91 / 255)
CYAN = (0 / 255, 168 / 255, 191 / 255)
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


def _draw_header(pdf: canvas.Canvas, width: float, height: float, run: dict[str, Any], solution: dict[str, Any]) -> float:
    pdf.setFillColorRGB(*NAVY)
    pdf.rect(0, height - 84, width, 84, stroke=0, fill=1)
    if BRAND_LOGO.exists():
        pdf.drawImage(str(BRAND_LOGO), 30, height - 69, width=190, height=48, preserveAspectRatio=True, mask="auto")
    else:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(32, height - 48, "AxioLoad")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawRightString(width - 32, height - 37, "Plan opérationnel de chargement")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawRightString(width - 32, height - 55, f"Calcul {run['id']} · statut {run['status']}")
    pdf.setFillColorRGB(*NAVY)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(32, height - 105, f"Solution {solution.get('rank', 1)}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(130, height - 105, f"{solution['vehicle_count']} véhicule(s)")
    pdf.drawString(260, height - 105, f"Longueur occupée : {solution['occupied_length_m']:.3f} m")
    pdf.drawString(475, height - 105, f"Mètres linéaires : {solution['total_linear_meters']:.3f} m.l.")
    return height - 124


def _fit_image(image: ImageReader, max_width: float, max_height: float) -> tuple[float, float]:
    image_width, image_height = image.getSize()
    ratio = min(max_width / image_width, max_height / image_height)
    return image_width * ratio, image_height * ratio


def _draw_plan_table(pdf: canvas.Canvas, page_width: float, page_height: float, solution: dict[str, Any], start_y: float) -> None:
    y = start_y
    for vehicle_index, plan in enumerate(solution["vehicle_plans"], start=1):
        if y < 105:
            pdf.showPage()
            y = page_height - 45
        pdf.setFillColorRGB(*NAVY)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.drawString(32, y, f"Véhicule {vehicle_index} · {plan['vehicle_name']}")
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColorRGB(*MUTED)
        pdf.drawRightString(page_width - 32, y, f"{plan['occupied_length_m']:.3f} m occupés · {plan['linear_meters']:.3f} m.l.")
        y -= 14
        pdf.setFillColorRGB(*NAVY)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(42, y, "Référence")
        pdf.drawString(125, y, "Destination")
        pdf.drawString(250, y, "Position longitudinale / transversale")
        pdf.drawString(440, y, "Dimensions L × l × H")
        pdf.drawString(590, y, "Orientation")
        y -= 10
        pdf.setStrokeColorRGB(.82, .88, .91)
        pdf.line(40, y + 5, page_width - 35, y + 5)
        for p in plan["placements"]:
            if y < 42:
                pdf.showPage()
                y = page_height - 45
            pdf.setFillColorRGB(.08, .18, .23)
            pdf.setFont("Helvetica", 7.2)
            pdf.drawString(42, y, str(p["item_id"])[:17])
            pdf.drawString(125, y, str(p["destination"])[:25])
            pdf.drawString(250, y, f"{p['y_mm']} / {p['x_mm']} mm")
            pdf.drawString(440, y, f"{p['actual_length_mm']} × {p['actual_width_mm']} × {p['actual_height_mm']} mm")
            pdf.drawString(590, y, f"{p['orientation_deg']}°")
            y -= 10
        y -= 10


def export_pdf(
    run: dict[str, Any],
    plan_image_png: bytes | None = None,
    solution_index: int = 0,
    vehicle_index: int = 0,
    vehicle_dimensions: dict[str, Any] | None = None,
) -> bytes:
    output = io.BytesIO()
    page = landscape(A4)
    pdf = canvas.Canvas(output, pagesize=page)
    width, height = page
    solution = _solution(run, solution_index)
    if vehicle_index < 0 or vehicle_index >= len(solution["vehicle_plans"]):
        raise ValueError("unknown vehicle index")
    plan = solution["vehicle_plans"][vehicle_index]
    pdf.setTitle(f"AxioLoad - Plan de chargement {run['id']}")
    y = _draw_header(pdf, width, height, run, solution)

    if vehicle_dimensions:
        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(
            32,
            y,
            "Véhicule affiché : "
            f"{plan['vehicle_name']} · L {vehicle_dimensions['interior_length_mm']} mm · "
            f"l {vehicle_dimensions['interior_width_mm']} mm · H {vehicle_dimensions['interior_height_mm']} mm",
        )
        y -= 14

    if plan_image_png:
        try:
            image = ImageReader(io.BytesIO(plan_image_png))
            image_width, image_height = _fit_image(image, width - 64, 330)
            image_x = (width - image_width) / 2
            image_y = y - image_height
            pdf.setStrokeColorRGB(*TEAL)
            pdf.roundRect(image_x - 3, image_y - 3, image_width + 6, image_height + 6, 6, stroke=1, fill=0)
            pdf.drawImage(image, image_x, image_y, width=image_width, height=image_height, preserveAspectRatio=True, mask="auto")
            y = image_y - 18
        except Exception as exc:  # report remains usable even when the optional capture is invalid
            pdf.setFillColorRGB(.72, .15, .25)
            pdf.setFont("Helvetica", 8)
            pdf.drawString(32, y, f"Capture 3D non intégrée : {type(exc).__name__}")
            y -= 16

    _draw_plan_table(pdf, width, height, solution, y)
    pdf.save()
    return output.getvalue()
