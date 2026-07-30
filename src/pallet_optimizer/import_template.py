from __future__ import annotations

import io
from typing import Final

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

TABLE_COLUMNS: Final[tuple[str, ...]] = (
    "Référence", "Qté", "Forme", "L (mm)", "l (mm)", "H (mm)", "Poids (kg)", "Destination",
    "Point d’enlèvement", "Point de livraison", "Ordre", "Rotation autorisée", "Gerbable",
    "Groupe ensemble", "Groupe séparé", "Tags compatibles", "Tags incompatibles", "Séparation (mm)",
)


def build_import_template_xlsx() -> bytes:
    workbook = Workbook(); sheet = workbook.active; sheet.title = "Marchandises"
    sheet.append(TABLE_COLUMNS)
    sheet.append(("PAL-001",1,"pallet",1200,800,1200,500,"Client A","49.493660, 0.114000",
                  "48.856600, 2.352200",1,"Oui","Non","","","alimentaire","chimique",0))
    for cell in sheet[1]:
        cell.font = Font(bold=True); cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"; sheet.auto_filter.ref = "A1:R2"
    widths = (18,8,16,12,12,12,14,22,28,28,10,20,14,18,18,22,22,18)
    for index, width in enumerate(widths, 1): sheet.column_dimensions[chr(64 + index)].width = width
    yes_no = DataValidation(type="list", formula1='"Oui,Non"', allow_blank=False)
    shapes = DataValidation(type="list", formula1='"pallet,box,roll,cylinder,sheet,post,bar_rect,bar_cyl"', allow_blank=False)
    sheet.add_data_validation(yes_no); sheet.add_data_validation(shapes)
    yes_no.add("L2:L500"); yes_no.add("M2:M500"); shapes.add("C2:C500")
    output = io.BytesIO(); workbook.save(output); return output.getvalue()
