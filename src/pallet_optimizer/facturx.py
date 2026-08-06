from __future__ import annotations

import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping
from xml.etree.ElementTree import Element, SubElement, tostring

from .persistence import TenantRegistry, _connect, utc_now

MONEY = Decimal("0.01")
FACTURX_PROFILES = ("MINIMUM", "BASIC WL", "BASIC", "EN 16931", "EXTENDED")
DOCUMENT_TYPES = ("invoice", "credit_note", "advance_invoice")
DIRECTIONS = ("outgoing", "incoming")


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise ValueError(f"Montant invalide: {value}") from exc


def select_profile(invoice: Mapping[str, Any]) -> str:
    if invoice.get("reverse_charge") or invoice.get("allowances") or invoice.get("charges"):
        return "EXTENDED"
    if invoice.get("lines") and invoice.get("seller") and invoice.get("buyer"):
        return "EN 16931"
    if invoice.get("lines"):
        return "BASIC"
    return "MINIMUM"


def validate_invoice(invoice: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    required = {
        "invoice_number": "Numéro de facture manquant",
        "issue_date": "Date d’émission manquante",
        "currency": "Devise manquante",
        "seller": "Vendeur manquant",
        "buyer": "Acheteur manquant",
        "lines": "Aucune ligne de facture",
    }
    for field, message in required.items():
        if not invoice.get(field):
            errors.append({"field": field, "message": message})

    lines = invoice.get("lines") if isinstance(invoice.get("lines"), list) else []
    computed_net = Decimal("0")
    computed_tax = Decimal("0")
    for index, line in enumerate(lines, start=1):
        quantity = money(line.get("quantity"))
        unit_price = money(line.get("unit_price"))
        rate = money(line.get("vat_rate"))
        expected = (quantity * unit_price).quantize(MONEY, rounding=ROUND_HALF_UP)
        line_net = money(line.get("line_net_amount", expected))
        if line_net != expected:
            errors.append({"field": f"lines.{index}.line_net_amount", "message": "Le montant de ligne ne correspond pas à quantité × prix unitaire"})
        computed_net += line_net
        computed_tax += (line_net * rate / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)

    declared_net = money(invoice.get("total_net", computed_net))
    declared_tax = money(invoice.get("total_tax", computed_tax))
    declared_gross = money(invoice.get("total_gross", declared_net + declared_tax))
    if declared_net != computed_net:
        errors.append({"field": "total_net", "message": "Le total HT ne correspond pas aux lignes"})
    if declared_tax != computed_tax:
        errors.append({"field": "total_tax", "message": "Le total de TVA est incohérent"})
    if declared_gross != declared_net + declared_tax:
        errors.append({"field": "total_gross", "message": "Le total TTC est incohérent"})

    for side in ("seller", "buyer"):
        party = invoice.get(side) if isinstance(invoice.get(side), Mapping) else {}
        if not party.get("legal_name"):
            errors.append({"field": f"{side}.legal_name", "message": "Raison sociale manquante"})
        if not party.get("country_code"):
            errors.append({"field": f"{side}.country_code", "message": "Pays manquant"})
        if not party.get("siren") and not party.get("vat_number"):
            warnings.append({"field": side, "message": "Aucun SIREN ou numéro de TVA n’est renseigné"})

    return {
        "valid": not errors,
        "profile": select_profile(invoice),
        "errors": errors,
        "warnings": warnings,
        "totals": {
            "net": str(computed_net.quantize(MONEY)),
            "tax": str(computed_tax.quantize(MONEY)),
            "gross": str((computed_net + computed_tax).quantize(MONEY)),
        },
    }


def build_facturx_xml(invoice: Mapping[str, Any]) -> bytes:
    report = validate_invoice(invoice)
    if not report["valid"]:
        raise ValueError("La facture contient des erreurs bloquantes")
    root = Element("CrossIndustryInvoice", {"profile": report["profile"]})
    header = SubElement(root, "Header")
    SubElement(header, "InvoiceNumber").text = str(invoice["invoice_number"])
    SubElement(header, "IssueDate").text = str(invoice["issue_date"])
    SubElement(header, "Currency").text = str(invoice["currency"])
    parties = SubElement(root, "Parties")
    for key in ("seller", "buyer"):
        party_data = invoice[key]
        party = SubElement(parties, key.title())
        for field in ("legal_name", "siren", "siret", "vat_number", "address_line1", "postal_code", "city", "country_code"):
            value = party_data.get(field)
            if value not in (None, ""):
                SubElement(party, field).text = str(value)
    lines_node = SubElement(root, "Lines")
    for index, line_data in enumerate(invoice["lines"], start=1):
        line = SubElement(lines_node, "Line", {"number": str(index)})
        for field in ("description", "quantity", "unit_code", "unit_price", "vat_rate", "line_net_amount"):
            value = line_data.get(field)
            if value not in (None, ""):
                SubElement(line, field).text = str(value)
    totals = SubElement(root, "Totals")
    for key, value in report["totals"].items():
        SubElement(totals, key).text = value
    return tostring(root, encoding="utf-8", xml_declaration=True)


class FacturXRepository:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry

    def _path(self, tenant_id: str):
        return self.registry.tenant_path(tenant_id)

    def migrate(self, tenant_id: str) -> None:
        with _connect(self._path(tenant_id)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS invoice_parties (
                    id TEXT PRIMARY KEY,
                    party_type TEXT NOT NULL,
                    legal_name TEXT NOT NULL,
                    trade_name TEXT,
                    siren TEXT,
                    siret TEXT,
                    vat_number TEXT,
                    email TEXT,
                    phone TEXT,
                    address_json TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_party_siret ON invoice_parties(siret) WHERE siret IS NOT NULL AND siret <> '';
                CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_party_vat ON invoice_parties(vat_number) WHERE vat_number IS NOT NULL AND vat_number <> '';
                CREATE TABLE IF NOT EXISTS electronic_invoices (
                    id TEXT PRIMARY KEY,
                    direction TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    profile TEXT,
                    invoice_number TEXT,
                    payload_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    source_name TEXT,
                    source_deleted INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validated_at TEXT,
                    validated_by TEXT
                );
                CREATE TABLE IF NOT EXISTS electronic_invoice_events (
                    id TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL REFERENCES electronic_invoices(id) ON DELETE CASCADE,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def create_invoice(self, tenant_id: str, actor_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.migrate(tenant_id)
        direction = str(payload.get("direction") or "outgoing")
        document_type = str(payload.get("document_type") or "invoice")
        if direction not in DIRECTIONS or document_type not in DOCUMENT_TYPES:
            raise ValueError("Type ou sens de facture invalide")
        invoice_id = str(uuid.uuid4())
        normalized = dict(payload)
        report = validate_invoice(normalized)
        now = utc_now()
        with _connect(self._path(tenant_id)) as db:
            db.execute("""INSERT INTO electronic_invoices(
                id,direction,document_type,status,profile,invoice_number,payload_json,validation_json,
                source_name,source_deleted,created_by,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?)""", (
                invoice_id, direction, document_type, "draft", report["profile"], normalized.get("invoice_number"),
                json.dumps(normalized, ensure_ascii=False), json.dumps(report, ensure_ascii=False),
                normalized.get("source_name"), actor_id, now, now,
            ))
        return self.get_invoice(tenant_id, invoice_id)

    def get_invoice(self, tenant_id: str, invoice_id: str) -> dict[str, Any]:
        self.migrate(tenant_id)
        with _connect(self._path(tenant_id)) as db:
            row = db.execute("SELECT * FROM electronic_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not row:
            raise KeyError(invoice_id)
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["validation"] = json.loads(result.pop("validation_json"))
        return result

    def list_invoices(self, tenant_id: str) -> list[dict[str, Any]]:
        self.migrate(tenant_id)
        with _connect(self._path(tenant_id)) as db:
            rows = db.execute("SELECT id FROM electronic_invoices ORDER BY created_at DESC").fetchall()
        return [self.get_invoice(tenant_id, str(row["id"])) for row in rows]

    def validate_human(self, tenant_id: str, invoice_id: str, actor_id: str) -> dict[str, Any]:
        invoice = self.get_invoice(tenant_id, invoice_id)
        report = validate_invoice(invoice["payload"])
        if not report["valid"]:
            raise ValueError("La facture contient des erreurs bloquantes")
        now = utc_now()
        with _connect(self._path(tenant_id)) as db:
            db.execute("UPDATE electronic_invoices SET status='validated',profile=?,validation_json=?,validated_at=?,validated_by=?,updated_at=? WHERE id=?", (
                report["profile"], json.dumps(report, ensure_ascii=False), now, actor_id, now, invoice_id,
            ))
            db.execute("INSERT INTO electronic_invoice_events(id,invoice_id,actor_id,event_type,event_json,created_at) VALUES (?,?,?,?,?,?)", (
                str(uuid.uuid4()), invoice_id, actor_id, "human_validation", "{}", now,
            ))
        return self.get_invoice(tenant_id, invoice_id)
