# -*- coding: utf-8 -*-
"""
Rutas HTTP relacionadas con ERPNext.
- Mantiene el main limpio (solo registra blueprints).
- Reusa el cliente de ERP en erp_client.py (sin Flask adentro).
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json

# Import tardío del cliente ERP. Este módulo NO debe importar main.py
try:
    from erp_client import _erp_get, list_unpaid_invoices
except Exception:
    _erp_get = None
    list_unpaid_invoices = None

# ---------- helpers ----------
def _calc_dpd_local(due_date_str: str) -> int:
    """DPD a partir de due_date (YYYY-MM-DD o ISO)."""
    try:
        s = (due_date_str or "").strip()
        if not s:
            return 0
        if len(s) == 10:
            d = datetime.fromisoformat(s + "T00:00:00").date()
        else:
            d = datetime.fromisoformat(s).date()
        return max(0, (datetime.utcnow().date() - d).days)
    except Exception:
        return 0

# ========== Blueprints ==========
# Conservamos las rutas EXACTAS que ya probabas para evitar 404:
debug_bp = Blueprint("erp_debug", __name__, url_prefix="/debug/erp")
bp       = Blueprint("erp", __name__, url_prefix="/erp")

# ---------- /debug/erp/* ----------
@debug_bp.get("/whoami")
def debug_erp_whoami():
    """Prueba de credenciales: devuelve el usuario autenticado en ERPNext."""
    if _erp_get is None:
        return jsonify(ok=False, error="erp_client no disponible"), 500
    try:
        data = _erp_get("/api/method/frappe.auth.get_logged_user")
        return jsonify(ok=True, who=data), 200
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 502

@debug_bp.get("/raw")
def debug_erp_raw():
    """Listado crudo de Sales Invoice (impagas) para validar acceso/campos."""
    if _erp_get is None:
        return jsonify(ok=False, error="erp_client no disponible"), 500

    params = {
        "fields": json.dumps([
            "name","customer","due_date","outstanding_amount",
            "grand_total","status","company","currency"
        ]),
        "filters": json.dumps([
            ["docstatus","in",[0,1]],
            ["outstanding_amount",">","0"],
        ]),
        "limit_page_length": "20",
        "order_by": "due_date asc",
    }
    try:
        data = _erp_get("/api/resource/Sales%20Invoice", params=params)
        return jsonify(ok=True, data=data), 200
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 502

# ---------- /erp/* (endpoints “de negocio”) ----------
@bp.get("/invoices/unpaid")
def erp_invoices_unpaid():
    """
    Lista de facturas con saldo pendiente (impagas).
    Query params:
      - limit, offset, order_by
      - q (opcional: filtra por customer)
      - include_draft=1 (incluye borradores si aplica)
    """
    if list_unpaid_invoices is None:
        return jsonify(ok=False, error="erp_client no disponible"), 500

    try:
        limit   = int(request.args.get("limit", 25))
        offset  = int(request.args.get("offset", 0))
        q       = request.args.get("q")
        order   = request.args.get("order_by") or "due_date asc"
        include_draft = (request.args.get("include_draft","0").lower() in ("1","true","yes","on"))

        rows = list_unpaid_invoices(
            limit=limit, offset=offset, q=q, order_by=order, include_draft=include_draft
        )

        items = [{
            "invoice_id":  inv.get("name"),
            "customer_id": inv.get("customer"),
            "due_date":    inv.get("due_date"),
            "dias_atraso": _calc_dpd_local(inv.get("due_date")),
            "amount":      inv.get("outstanding_amount"),
            "grand_total": inv.get("grand_total"),
            "status":      inv.get("status"),
            "company":     inv.get("company"),
            "currency":    inv.get("currency"),
        } for inv in rows]

        return jsonify({"ok": True, "count": len(items), "items": items}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

