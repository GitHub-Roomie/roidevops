# erp_client.py
import os
import datetime as dt
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# ===== Config (.env) =====
ERP_URL    = os.getenv("ERP_URL", "").rstrip("/")
API_KEY    = os.getenv("ERP_API_KEY", "")
API_SECRET = os.getenv("ERP_API_SECRET", "")
ERP_DEBUG  = (os.getenv("ERP_DEBUG", "false").lower() in ("1", "true", "yes", "on"))

if not (ERP_URL and API_KEY and API_SECRET):
    print("[ERP] Faltan variables ERP_URL / ERP_API_KEY / ERP_API_SECRET en .env")

# ===== HTTP session =====
_session = requests.Session()
_session.headers.update({
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Accept": "application/json",
})

def _erp_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{ERP_URL}/{path.lstrip('/')}"
    if ERP_DEBUG:
        print("[ERP] GET", url, "| params=", params)
    r = _session.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def _json_list(v) -> str:
    # ERPNext espera listas JSON como string con comillas dobles
    return str(v).replace("'", '"')

# ===== Utilidades =====
def calc_dias_atraso(due_date_str: Optional[str]) -> int:
    if not due_date_str:
        return 0
    try:
        due = dt.date.fromisoformat(str(due_date_str))
    except Exception:
        return 0
    today = dt.date.today()
    return max((today - due).days, 0)

# ===== API Helpers =====
def list_sales_invoices(
    limit: int = 20,
    offset: int = 0,
    order_by: Optional[str] = "due_date asc",
) -> List[Dict[str, Any]]:
    fields = [
        "name", "customer", "posting_date", "due_date",
        "outstanding_amount", "grand_total", "status",
        "company", "currency",
    ]
    params = {
        "fields": _json_list(fields),
        "order_by": order_by or "due_date asc",
        "limit_page_length": str(limit),
        "limit_start": str(offset),
    }
    data = _erp_get(f"/api/resource/{quote('Sales Invoice')}", params=params)
    return data.get("data") or data.get("message") or []

def list_unpaid_invoices(
    limit: int = 20,
    offset: int = 0,
    q: Optional[str] = None,
    order_by: Optional[str] = "due_date asc",
    include_draft: bool = False,
) -> List[Dict[str, Any]]:
    # Filtros: con saldo pendiente; docstatus configurable
    filters = [
        ["outstanding_amount", ">", "0"],
    ]
    if include_draft:
        filters.append(["docstatus", "in", [0, 1]])  # Draft (0) o Submit (1)
    else:
        filters.append(["docstatus", "=", "1"])      # Solo Submit

    if q:
        # Búsqueda por cliente (agrega name si lo necesitas)
        filters.append(["customer", "like", f"%{q}%"])
        # filters.append(["name", "like", f"%{q}%"])

    fields = [
        "name", "customer", "posting_date", "due_date",
        "outstanding_amount", "grand_total", "status",
        "company", "currency",
    ]
    params = {
        "filters": _json_list(filters),
        "fields": _json_list(fields),
        "order_by": order_by or "due_date asc",
        "limit_page_length": str(limit),
        "limit_start": str(offset),
    }
    data = _erp_get(f"/api/resource/{quote('Sales Invoice')}", params=params)
    return data.get("data") or data.get("message") or []

def get_invoice(name: str) -> Optional[Dict[str, Any]]:
    data = _erp_get(f"/api/resource/{quote('Sales Invoice')}/{name}")
    doc = data.get("data") or data.get("message") or {}
    if not doc:
        return None
    keep = (
        "name", "customer", "posting_date", "due_date",
        "outstanding_amount", "grand_total", "status",
        "company", "currency",
    )
    return {k: doc.get(k) for k in keep}

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(filename=".env", usecwd=True), override=False)
except Exception:
    pass
