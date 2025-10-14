# ──────────────────────────────────────────────────────────────────────────────
# main.py — API de Cobranza unificada (FastAPI)
# ──────────────────────────────────────────────────────────────────────────────

import os
import sys
import json, unicodedata
import re
import re as _re
import re
import re as _re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

# Asegura imports relativos
sys.path.append(os.path.dirname(__file__))

# ========== Entorno ==========
from dotenv import load_dotenv, find_dotenv
ENV_PATH = find_dotenv(filename=".env", usecwd=True)
DOTENV_LOADED = load_dotenv(ENV_PATH, override=True)

# ========== FastAPI ==========
from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Motor de Cobranza", version="1.0")

# ========== CORS ==========
origins = [
    "http://localhost:3000",
    "http://localhost:5050",
    "http://localhost:5173",  # Lovable local
    "https://preview--*.lovable.app",
    "https://*.lovableproject.com",
    "https://*.lovable.app",
    "https://96a6af52b70e.ngrok-free.app",  # Para demo - en producción especifica dominios
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Para demo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Importar Blueprint de Reportes (Flask) ==========
try:
    from app.reports import bp as reportes_bp
    print("✅ Reportes (Flask Blueprint) importado")
except Exception as e:
    print(f"⚠️ Error importando reportes: {e}")
    reportes_bp = None

# ========== Importar módulos propios ==========
try:
    from decision import compute_decision
    print("✅ decision.py importado")
except Exception as e:
    print(f"⚠️ Error importando decision.py: {e}")
    compute_decision = None


# Línea ~52 - Agrega estas variables
N8N_WEBHOOK_NOTIFY = os.getenv("N8N_WEBHOOK_NOTIFY", "").strip()
N8N_WEBHOOK_REPORT = os.getenv("N8N_WEBHOOK_REPORT", "").strip()
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_NOTIFY", "").strip()  # Para compatibilidad

# Variables de ERP
ERP_URL = os.getenv("ERP_URL", "").strip()
ERP_API_KEY = os.getenv("ERP_API_KEY", "").strip()
ERP_API_SECRET = os.getenv("ERP_API_SECRET", "").strip()
ERP_DEBUG = os.getenv("ERP_DEBUG", "false").lower() == "true"

try:
    from erp_client import (
        list_sales_invoices,
        list_unpaid_invoices,
        get_invoice,
        calc_dias_atraso,
        _erp_get,
    )
    print("✅ erp_client.py importado")
except Exception as e:
    print(f"⚠️ Error importando erp_client.py: {e}")
    _erp_get = None

try:
    from app.services.db import SessionLocal, ActionLog, Evaluation
    print("✅ services/db.py importado")
except Exception as e:
    print(f"⚠️ Error importando db.py: {e}")
    SessionLocal = None

try:
    from app.services.metrics import build_kpis, build_timeseries
    print("✅ services/metrics.py importado")
except Exception as e:
    print(f"⚠️ Error importando metrics.py: {e}")
    build_kpis = None

# ========== Twilio / OpenAI ==========
try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.twiml.voice_response import VoiceResponse
    from twilio.rest import Client as TwilioClient
    from langchain_openai import ChatOpenAI
    from langchain.schema import SystemMessage, HumanMessage
    print("✅ Twilio y OpenAI importados")
except Exception as e:
    print(f"⚠️ Error importando Twilio/OpenAI: {e}")

# ========== Variables de entorno ==========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4-mini")
LLM_TEMP = float(os.getenv("LLM_TEMPERATURE", "0.5"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5050").rstrip("/")

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://localhost:5050")
VOICE = os.getenv("TTS_VOICE", "Polly.Mia-Neural")

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").strip()
N8N_INGEST_URL = os.getenv("N8N_INGEST_URL", "").strip()

# Inicializar Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("✅ Twilio client inicializado")
    except Exception as e:
        print(f"⚠️ Error inicializando Twilio: {e}")


# ========== Flask App ==========
from flask import Flask
from flask_cors import CORS as FlaskCORS

flask_app = Flask(__name__)
FlaskCORS(flask_app, resources={r"/*": {"origins": ["*"]}})

# Registrar blueprint de reportes
if reportes_bp:
    flask_app.register_blueprint(reportes_bp)
    print("✅ Blueprint de reportes registrado en Flask")

try:
    from app.stalled_flask import bp as stalled_bp
    flask_app.register_blueprint(stalled_bp)
    print("✅ Stalled (Flask) registrado")
except Exception as e:
    print(f"⚠️ Error importando stalled: {e}")

# ========== Endpoints ERP (Flask) ==========
from flask import request, jsonify
import json

@flask_app.get("/erp/invoices/unpaid")
def erp_invoices_unpaid():
    """Lista facturas impagas desde ERP"""
    try:
        if not list_unpaid_invoices:
            return jsonify({"ok": False, "error": "ERP client no disponible"}), 500

        limit = int(request.args.get("limit", 25))
        offset = int(request.args.get("offset", 0))
        q = request.args.get("q")
        order = request.args.get("order_by") or "due_date asc"
        
        include_draft_param = request.args.get("include_draft")
        include_draft = (include_draft_param or "").lower() in ("1", "true", "yes", "on")

        rows = list_unpaid_invoices(
            limit=limit,
            offset=offset,
            q=q,
            order_by=order,
            include_draft=include_draft
        )

        # Fallback: si no mandaste include_draft y vino vacío, intenta con Draft
        used_fallback = False
        if not rows and include_draft_param is None:
            rows = list_unpaid_invoices(
                limit=limit, offset=offset, q=q, order_by=order, include_draft=True
            )
            used_fallback = True

        items = [{
            "invoice_id": inv.get("name"),
            "customer_id": inv.get("customer"),
            "due_date": inv.get("due_date"),
            "dias_atraso": calc_dias_atraso(inv.get("due_date")) if calc_dias_atraso else 0,
            "amount": inv.get("outstanding_amount"),
            "grand_total": inv.get("grand_total"),
            "status": inv.get("status"),
            "company": inv.get("company"),
            "currency": inv.get("currency"),
        } for inv in rows]

        resp = jsonify({"ok": True, "count": len(items), "items": items})
        if used_fallback:
            resp.headers["X-ERP-Include-Draft"] = "fallback"
        return resp, 200

    except Exception as e:
        print(f"Error en erp_invoices_unpaid: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@flask_app.post("/erp/trigger-cobranza")
def erp_trigger_cobranza():
    """Dispara proceso de cobranza para una factura"""
    try:
        body = request.get_json(silent=True) or {}
        invoice_name = body.get("invoice") or request.args.get("invoice")
        
        if not invoice_name:
            return jsonify({"ok": False, "error": "Falta parámetro 'invoice'"}), 400

        if not get_invoice:
            return jsonify({"ok": False, "error": "ERP client no disponible"}), 500

        inv = get_invoice(invoice_name)
        if not inv:
            return jsonify({"ok": False, "error": f"Factura '{invoice_name}' no encontrada"}), 404

        dias = calc_dias_atraso(inv.get("due_date")) if calc_dias_atraso else 0
        monto = float(inv.get("outstanding_amount") or 0.0)
        nombre = inv.get("customer") or "Cliente"

        # Decisión
        if compute_decision:
            dec_payload = {
                "nombre": nombre,
                "score": 60,
                "dias_atraso": dias,
                "monto": monto,
            }
            decision = compute_decision(dec_payload)
        else:
            decision = {}

        return jsonify({
            "ok": True,
            "invoice": inv["name"],
            "cliente": nombre,
            "status": inv.get("status"),
            "due_date": inv.get("due_date"),
            "dias_atraso": dias,
            "monto": monto,
            "decision": decision,
        }), 200

    except Exception as e:
        print(f"Error en erp_trigger_cobranza: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ========== Endpoints de Predicción (Flask) ==========

@flask_app.route("/prediccion/health", methods=["GET"])
def prediccion_health():
    """Health check del módulo de predicción"""
    try:
        import sys
        from pathlib import Path
        
        root_dir = Path(__file__).parent
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))
        
        from prediction.serve import model_health
        return jsonify(model_health()), 200
    except Exception as e:
        print(f"❌ ERROR en prediccion_health: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.route("/prediccion/pago", methods=["POST"])
def prediccion_pago():
    """Predice probabilidad de pago para una factura"""
    try:
        # Import absoluto (sin "app.")
        import sys
        from pathlib import Path
        
        # Asegurar que el directorio raíz está en el path
        root_dir = Path(__file__).parent
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))
        
        # Ahora sí importar
        from prediction.serve import predict_pago_dict
        
        data = request.get_json(force=True) or {}
        
        print(f"[DEBUG] Datos recibidos: {data}")
        
        # Si viene invoice_id, buscar datos de la factura
        invoice_id = data.get("invoice_id")
        if invoice_id and get_invoice:
            inv = get_invoice(invoice_id)
            if inv:
                data["nombre"] = data.get("nombre") or inv.get("customer")
                data["monto"] = data.get("monto") or float(inv.get("outstanding_amount") or 0)
                data["dias_atraso"] = data.get("dias_atraso") or (
                    calc_dias_atraso(inv.get("due_date")) if calc_dias_atraso else 0
                )
        
        # Valores por defecto
        data.setdefault("nombre", "Cliente")
        data.setdefault("score", 60)
        data.setdefault("dias_atraso", 0)
        data.setdefault("monto", 0)
        data.setdefault("pais", "MX")
        data.setdefault("sector", "retail")
        data.setdefault("recordatorios_enviados", 0)
        data.setdefault("pagos_previos", 0)
        data.setdefault("moras_previas", 0)
        
        print(f"[DEBUG] Datos procesados: {data}")
        
        out = predict_pago_dict(data)
        
        print(f"[DEBUG] Resultado: {out}")
        
        return jsonify(out), 200
        
    except Exception as e:
        print(f"❌ ERROR en prediccion_pago: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "ok": False, 
            "error": str(e),
            "type": type(e).__name__
        }), 500

@flask_app.get("/debug/erp/ping")
def debug_erp_ping():
    """Prueba de auth contra ERP"""
    try:
        if not _erp_get:
            return jsonify({"ok": False, "error": "ERP client no disponible"}), 500
            
        who = _erp_get("/api/method/frappe.auth.get_logged_user")
        return jsonify({"ok": True, "who": who}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

print("✅ Endpoints ERP registrados en Flask")




# Inicializar LLM
llm = None
if OPENAI_API_KEY:
    try:
        llm = ChatOpenAI(model_name=LLM_MODEL, temperature=LLM_TEMP)
        print("✅ LLM inicializado")
    except Exception as e:
        print(f"⚠️ Error inicializando LLM: {e}")

# ========== Estado de sesiones (para llamadas) ==========
# =========================================================
# SESIONES / PROMPTS
# =========================================================
SESSIONS = {}  # { call_sid: { system, history, intensity, resists } }

SYSTEM_TEMPLATE = (
    "Te llamas “Gabriel”, agente de cobranza profesional. Objetivo: cerrar pago con empatía mínima y FIRMEZA proporcional al nivel.\n"
    "Contexto del cliente:\n"
    "- Nombre: {nombre}\n"
    "- Días de atraso: {dias}\n"
    "- Monto pendiente: {monto} MXN\n"
    "- Score: {score}\n"
    "- Nivel de cobro (1=bajo, 2=medio, 3=alto): {nivel}\n"
    "- Abono mínimo exigido (nivel 3): {min_parcial} MXN\n\n"
    "REGLAS GLOBALES (obligatorias):\n"
    "- Español México. Frases cortas (≤16 palabras). UNA idea por turno. Termina SIEMPRE con UNA pregunta clara.\n"
    "- Sé directo y específico. Evita rodeos. Nada de muletillas.\n"
    "- No inventes datos: usa solo el contexto.\n"
    "- Mantén profesionalismo: sin insultos ni descalificaciones, aunque el tono sea muy firme.\n"
    "- No inicies con “Aviso”. Inicia mencionando saldo y días. Luego confirma identidad.\n\n"
    "DIRECCIÓN AL CLIENTE (MUY IMPORTANTE):\n"
    "- Cuando NECESITES mencionar al cliente, usa exactamente el marcador [[NOMBRE]].\n"
    "- No repitas [[NOMBRE]] más de una vez por turno.\n"
    "- Apertura: usa [[NOMBRE]] una sola vez en la primera frase.\n"
    "- Turnos siguientes: si corresponde, vuelve a usar [[NOMBRE]] como vocativo breve.\n"
    "- En nivel 3, el tono debe sonar más formal (el marcador se reemplazará por tratamiento formal si aplica).\n\n"
    "APERTURA (todos los niveles, orden pedido por negocio):\n"
    "1) PRIMERA frase: menciona saldo y días de atraso.\n"
    "2) SEGUNDA frase: confirma identidad con pregunta cerrada.\n"
    "Ejemplo: “[[NOMBRE]], soy Sofía. Tu saldo es {monto}, con {dias} días de atraso. ¿Eres [[NOMBRE]]?”\n\n"
    "GUÍA POR TURNOS:\n"
    "1) Tras confirmar identidad, explica el motivo en UNA oración.\n"
    "2) Ofrece UNA opción por turno: pago hoy / promesa con fecha fija / parcial hoy + resto en X días.\n"
    "3) Objeciones:\n"
    "   - “Ya pagué”: pide fecha y medio para verificar.\n"
    "   - “No tengo”: propone parcial REALISTA y fecha FIRME.\n"
    "   - “No soy yo”: solicita teléfono u horario del titular.\n"
    "4) Al acordar: repite acuerdo y pide canal de seguimiento (WhatsApp/SMS/correo).\n"
    "5) Si detectas resistencia repetida, incrementa el tono un nivel (máx 3).\n\n"
    "TONO POR NIVEL:\n"
    "- Nivel 1 (1–5 días): cordial y preventivo. Evita “urgente” o “exigimos”. Enfatiza beneficios y evitar recargos.\n"
    "- Nivel 2 (6–15 días): FIRME y directo. Menciona intereses activos y riesgo de suspensión temporal de beneficios. Exige acuerdo HOY; pago total o parcial con fecha ≤72 horas. No menciones área jurídica.\n"
    "- Nivel 3 (≥16 días o riesgo alto): MUY FIRME y EXIGENTE.\n"
    "  • Usa verbos: “exigimos”, “debes”, “último aviso operativo”.\n"
    "  • Comunica: intereses acumulándose, suspensión inmediata de beneficios/servicio.\n"
    "  • Advierte posible escalamiento a área jurídica conforme contrato y normatividad.\n"
    "  • EXIGE un abono mínimo HOY de {min_parcial} MXN o fecha inamovible con monto.\n"
    "  • Si hay resistencia, incrementa urgencia y pide compromiso concreto EN ESTA LLAMADA.\n\n"
    "PLANTILLAS RÁPIDAS (usa y varía, mantén intención):\n"
    "- Nivel 1 (apertura cordial): “[[NOMBRE]], soy Sofía. Saldo {monto}, {dias} días de atraso. ¿Eres [[NOMBRE]]?”\n"
    "- Nivel 1 (motivo/acción): “Para mantener tus beneficios, ¿pagas hoy o agendamos fecha cercana?”\n"
    "- Nivel 2 (apertura firme): “[[NOMBRE]], soy Sofía. Saldo {monto} con {dias} días. ¿Eres [[NOMBRE]]?”\n"
    "- Nivel 2 (marco 72h): “Hay intereses activos y riesgo de suspensión. Define pago hoy o fecha dentro de 72 horas. ¿Cuál confirmas?”\n"
    "- Nivel 2 (sin total): “Propón un parcial realista hoy y fecha fija. ¿Qué monto cubres y cuándo?”\n"
    "- Nivel 3 (apertura dura): “[[NOMBRE]], soy Sofía. Saldo {monto}, {dias} días de atraso. Exigimos regularización hoy. ¿Eres [[NOMBRE]]?”\n"
    "- Nivel 3 (consecuencia 1): “Los intereses crecen y beneficios están suspendidos. ¿Vas a regularizar hoy?”\n"
    "- Nivel 3 (consecuencia 2): “Sin acuerdo hoy, escalaremos a área jurídica conforme contrato. ¿Confirmas pago?”\n"
    "- Nivel 3 (acción mínima): “Requerimos un abono hoy de {min_parcial} MXN. ¿Lo realizas ahora por SPEI?”\n"
    "- Nivel 3 (no tengo): “Entiendo. Exigimos {min_parcial} hoy y fecha fija para el resto. ¿Cuál confirmas?”\n"
    "- Cierre de acuerdo: “Queda pactado el monto y fecha. ¿Envío confirmación por WhatsApp o correo?”\n"
)


CLOSERS = [
    r"\bes todo\b", r"\bya no\b", r"\bgracias\b", r"\bno necesito\b", r"\bno quiero\b",
    r"\badios\b", r"\badiós\b", r"\bbye\b", r"\bhasta luego\b"
]
RESISTANCE = [
    r"\bno tengo\b", r"\bno puedo\b", r"\bdespu[eé]s\b", r"\bllama\b.*\bdespu[eé]s\b",
    r"\bno quiero pagar\b", r"\bno pienso pagar\b"
]


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def compute_min_parcial(monto) -> str:
    # 10% con 2 decimales, y mínimo 100 MXN para que tenga fuerza comercial
    m = _to_float(monto)
    base = max(m * 0.10, 100.0)
    return f"{base:.2f}"


def compute_nivel_local(dias: str, score: str) -> int:
    try:
        d = int(dias or 0)
        s = int(score or 0)
    except Exception:
        d, s = 0, 0
    if d >= 16 or s < 60:
        return 3
    if d >= 6:
        return 2
    if d >= 1:
        return 1
    return 1


def should_close(text: str) -> bool:
    t = (text or "").lower()
    import re as _re
    return any(_re.search(p, t) for p in CLOSERS)


def count_resistance(text: str) -> int:
    t = (text or "").lower()
    import re as _re
    return sum(1 for p in RESISTANCE if _re.search(p, t))

_AFFIRM_ID = [
    r"\bs[ií]\b", r"\bas[ií]\s+es\b", r"\bsoy\b", r"\bhabla\b",
    r"\bcorrecto\b", r"\bas[ií]\b.*\bhabla\b"
]
_DENY_ID = [
    r"\bno soy\b", r"\bno habla\b", r"\bno.*titular\b", r"\bse equivoca\b",
    r"\bno.*(luis|yo)\b"  # opcional
]

def _detect_identity_confirmation(text: str) -> int:
    t = (text or "").lower()
    if any(_re.search(p, t) for p in _DENY_ID):
        return -1   # niega ser el titular
    if any(_re.search(p, t) for p in _AFFIRM_ID):
        return 1    # confirma ser el titular
    return 0        # no hay señal

def _update_identity_flags(call_sid: str, user_text: str):
    try:
        res = _detect_identity_confirmation(user_text)
        if res == 1:
            SESSIONS[call_sid]["identity_confirmed"] = True
        elif res == -1:
            SESSIONS[call_sid]["identity_confirmed"] = False
        # no tocamos asked_identity aquí; ya quedó True desde la apertura
    except Exception:
        pass

def _split_name_es(nombre: str):
    parts = (nombre or "").strip().split()
    if not parts:
        return {"full": "Cliente", "first": "Cliente", "last": ""}
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    return {"full": " ".join(parts), "first": first, "last": last}

def _honorific(last: str):
    # En demo, usa trato masculino genérico. (Podemos pedir preferencia más adelante)
    return f"señor {last}".strip() if last else "señor"

def next_address_variant(call_sid: str) -> str:
    sess = SESSIONS.get(call_sid, {})
    variants = sess.get("addr_variants") or []
    if not variants:
        return "Cliente"
    # Si la intensidad es alta (p. ej. nivel 3), forzamos trato formal cuando esté disponible:
    if sess.get("intensity", 1) >= 3 and sess.get("addr_formal"):
        return sess["addr_formal"]
    # Rotación simple: full → first → formal → (repite…)
    i = sess.get("addr_idx", 0) % len(variants)
    sess["addr_idx"] = i + 1
    return variants[i]

def _ssml_escape(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def to_ssml(text: str, intensity: int = 1) -> str:
    """
    Envuelve la respuesta en SSML y ajusta voz según intensidad (1 cordial, 2 firme, 3 muy firme).
    - rate: reduce un poco la velocidad (más firme = más lento).
    - pitch: baja un poquito el tono conforme sube la firmeza.
    """
    rate_map  = {1: "95%", 2: "92%", 3: "90%"}   # 100% = normal. Menos = más despacio
    pitch_map = {1: "+0%", 2: "-2%", 3: "-4%"}   # tono ligeramente más grave en nivel alto

    safe = _ssml_escape(text)
    return (
        f'<speak>'
        f'  <prosody rate="{rate_map.get(intensity, "95%")}" pitch="{pitch_map.get(intensity, "+0%")}">'
        f'    {safe}'
        f'  </prosody>'
        f'</speak>'
    )

# ensure_session() — acepta overrides
def ensure_session(call_sid: str, nombre: str, dias: str, monto: str, score: str, override_level=None, override_min=None):
    if call_sid not in SESSIONS:
        # nivel por decisión si viene; si no, calcula local
        if override_level is not None:
            try:
                nivel = int(override_level)
            except Exception:
                nivel = compute_nivel_local(dias, score)
        else:
            nivel = compute_nivel_local(dias, score)

        # mínimo por decisión si viene; si no, calcula 10% local
        if override_min is not None:
            min_parcial = override_min
        else:
            min_parcial = compute_min_parcial(monto)

        SESSIONS[call_sid] = {
            "system": SYSTEM_TEMPLATE.format(
                nombre=nombre, dias=dias, monto=monto, score=score,
                nivel=nivel, min_parcial=min_parcial
            ),
            "history": [],
            # Si es nivel 3 arrancamos alto
            "intensity": 3 if nivel == 3 else 1,
            "resists": 0,
            "target_nivel": nivel,
            "min_parcial": min_parcial,
            "asked_identity": False,
            "identity_confirmed": False,
        }
        # === variantes de trato guardadas en sesión ===
    name_parts = _split_name_es(nombre)
    formal = _honorific(name_parts["last"])
    SESSIONS[call_sid]["addr_variants"] = [name_parts["full"], name_parts["first"], formal]
    SESSIONS[call_sid]["addr_formal"]   = formal
    SESSIONS[call_sid]["addr_idx"]      = 0   # tras el primer uso, rotamos a la 2ª variante
    SESSIONS[call_sid]["name_parts"]    = name_parts


def build_messages(call_sid: str, user_text: str, force_intro=False):
    sess = SESSIONS.get(call_sid) or {}
    system = sess.get("system", "")
    intensity = sess.get("intensity", 1)
    target = sess.get("target_nivel", 1)

    msgs = [SystemMessage(content=system)]
    msgs.append(SystemMessage(content=f"Nivel de cobro objetivo (1-3): {target}."))
    msgs.append(SystemMessage(content=f"Nivel de intensidad sugerido por resistencia: {intensity}."))

    # Política de identidad (solo 1 vez, sin repetir)
    if sess.get("asked_identity", False):
        if sess.get("identity_confirmed", False):
            msgs.append(SystemMessage(content=(
                "La identidad ya fue confirmada en la apertura. "
                "NO repitas '¿Eres [[NOMBRE]]?'. Dirígete directo al motivo y opciones."
            )))
        else:
            msgs.append(SystemMessage(content=(
                "Ya preguntaste identidad en la apertura. NO repitas la pregunta. "
                "Si la persona indica que no es el titular, solicita teléfono/horario del titular "
                "o un medio de contacto, pero no vuelvas a pedir confirmación de identidad."
            )))

    # Contexto corto de los últimos turnos
    for role, content in sess.get("history", [])[-6:]:
        if role == "human":
            msgs.append(HumanMessage(content=content))
        else:
            msgs.append(SystemMessage(content=f"(Tu respuesta anterior): {content}"))

    # Mensaje del usuario o instrucción de inicio
    if force_intro:
        msgs.append(HumanMessage(content="Inicia la conversación con el cliente, sigue la guía por turnos."))
    else:
        msgs.append(HumanMessage(content=user_text or ""))

    return msgs

def _should_inject_name(call_sid: str) -> bool:
    sess = SESSIONS.setdefault(call_sid, {})
    # cuántas respuestas del bot van en esta llamada
    turns = sum(1 for r in sess.get("history", []) if r[0] == "ai") + 1
    # usa nombre en el turno 1 y luego en 4, 7, 10...
    return turns == 1 or (turns % 3 == 1)


def llm_reply(call_sid: str, user_text: str, force_intro=False) -> str:
    msgs = build_messages(call_sid, user_text, force_intro=force_intro)
    reply = llm(msgs).content.strip()

    # Reemplazo controlado de [[NOMBRE]] con "cooldown"
    if "[[NOMBRE]]" in reply:
        if _should_inject_name(call_sid):
            try:
                addr = next_address_variant(call_sid)
            except Exception:
                addr = SESSIONS.get(call_sid, {}).get("name_parts", {}).get("first", "Cliente")
            # Reemplaza SOLO la primera aparición…
            reply = reply.replace("[[NOMBRE]]", addr, 1)
            # …y elimina cualquier sobrante con espacios y coma opcional
            reply = re.sub(r"\s*\[\[NOMBRE\]\]\s*,?\s*", "", reply)
        else:
            # No toca vocativo este turno: quita marcador + espacios + coma
            reply = re.sub(r"\s*\[\[NOMBRE\]\]\s*,?\s*", "", reply)

    # Registro de historial (aunque no existiera la sesión)
    sess = SESSIONS.setdefault(call_sid, {"history": []})
    if user_text:
        sess["history"].append(("human", user_text))
    sess["history"].append(("ai", reply))
    return reply


# --- Helper: convierte due_date → días de atraso (DPD) ---
def _calc_dpd_from_due(due_date_str: str) -> int:
    """
    Acepta 'YYYY-MM-DD' o ISO completo 'YYYY-MM-DDTHH:MM:SS'.
    Devuelve días de atraso (>=0) respecto a hoy (UTC).
    """
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



# =========================================================
# RUTAS DE VOZ
# =========================================================
from fastapi import Request, Response
from urllib.parse import quote_plus

@app.post("/voice")
@app.get("/voice")
async def voice(
    request: Request,  # ← Parámetro obligatorio
    nombre: str = "Cliente",
    dias: str = "0",
    monto: str = "0",
    score: str = "0",
    nivel: str = None,
    min_parcial: str = None,
):
    """Endpoint inicial de llamada Twilio"""
    try:
        if not twilio_client or not llm:
            return Response(
                content="Servicio de voz no disponible", 
                media_type="text/plain",
                status_code=503
            )

        call_sid = request.query_params.get("CallSid", "no_sid")
        
        ensure_session(
            call_sid, nombre, dias, monto, score,
            override_level=nivel,
            override_min=min_parcial
        )
        
        SESSIONS[call_sid]["asked_identity"] = True
        
        intro = llm_reply(call_sid, user_text="", force_intro=True)
        intensity = SESSIONS[call_sid].get("intensity", 1)
        intro_ssml = to_ssml(intro, intensity)
        
        vr = VoiceResponse()
        vr.say(intro_ssml, voice=VOICE, language="es-MX")
        
        # Construye URL con parámetros
        params_str = "&".join([
            f"nombre={quote_plus(nombre)}",
            f"dias={quote_plus(dias)}",
            f"monto={quote_plus(monto)}",
            f"score={quote_plus(score)}",
            f"call_sid={quote_plus(call_sid)}"
        ])
        
        vr.gather(
            input="speech",
            speech_timeout="auto",
            language="es-MX",
            action=f"{PUBLIC_BASE_URL}/process_speech?{params_str}",
            method="POST",
        )
        
        return Response(content=str(vr), media_type="application/xml")
    
    except Exception as e:
        print(f"Error en /voice: {e}")
        vr = VoiceResponse()
        vr.say("Lo sentimos, hay un problema técnico.", voice=VOICE, language="es-MX")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")


from fastapi import Request, Response
from urllib.parse import quote_plus

@app.post("/process_speech")
async def process_speech(request: Request):
    """Procesa respuesta del usuario y genera siguiente mensaje"""
    try:
        # Leer datos del formulario (POST de Twilio)
        form_data = await request.form()
        user_text = (form_data.get("SpeechResult") or "").strip()
        
        # Leer parámetros de la URL
        call_sid = request.query_params.get("call_sid") or form_data.get("CallSid") or "no_sid"
        nombre = request.query_params.get("nombre", "Cliente")
        dias = request.query_params.get("dias", "0")
        monto = request.query_params.get("monto", "0")
        score = request.query_params.get("score", "0")
        nivel = request.query_params.get("nivel")
        min_parcial = request.query_params.get("min_parcial")

        # Si no hay sesión, terminar llamada
        if call_sid not in SESSIONS:
            vr = VoiceResponse()
            vr.say("Sesión no encontrada. Adiós.", voice=VOICE, language="es-MX")
            vr.hangup()
            return Response(content=str(vr), media_type="application/xml")

        # Respeta overrides desde /voice
        ensure_session(
            call_sid, nombre, dias, monto, score,
            override_level=nivel, override_min=min_parcial
        )
        
        if user_text:
            _update_identity_flags(call_sid, user_text)

        confidence = form_data.get("Confidence", "N/A")
        print(f"[Twilio STT] CallSid={call_sid} | User='{user_text}' | Confidence={confidence}")

        sess = SESSIONS.get(call_sid, {})
        vr = VoiceResponse()

        # Cierre explícito por parte del cliente
        if user_text and should_close(user_text):
            closing_ssml = to_ssml(
                "Gracias por tu tiempo. Cierro la llamada. Que tengas buen día.",
                intensity=sess.get("intensity", 1)
            )
            vr.say(closing_ssml, voice=VOICE, language="es-MX")
            vr.hangup()
            return Response(content=str(vr), media_type="application/xml")

        # Escalado de intensidad por resistencia
        if user_text:
            SESSIONS[call_sid]["resists"] = sess.get("resists", 0) + count_resistance(user_text)
            target_nivel = sess.get("target_nivel", 1)
            
            if target_nivel == 3:
                SESSIONS[call_sid]["intensity"] = 3
            else:
                if SESSIONS[call_sid]["resists"] >= 4:
                    SESSIONS[call_sid]["intensity"] = 3
                elif SESSIONS[call_sid]["resists"] >= 2:
                    SESSIONS[call_sid]["intensity"] = 2

        # Construir parámetros para la URL
        params_str = "&".join([
            f"nombre={quote_plus(nombre)}",
            f"dias={quote_plus(dias)}",
            f"monto={quote_plus(monto)}",
            f"score={quote_plus(score)}",
            f"nivel={quote_plus(nivel or '')}",
            f"min_parcial={quote_plus(min_parcial or '')}",
            f"call_sid={quote_plus(call_sid)}"
        ])

        # Si hubo silencio, reprompt breve
        if not user_text:
            reprompt = "¿Confirmas pago hoy, o fijamos una fecha exacta?"
            reprompt_ssml = to_ssml(reprompt, intensity=sess.get("intensity", 1))
            vr.say(reprompt_ssml, voice=VOICE, language="es-MX")
            vr.gather(
                input="speech",
                speech_timeout="auto",
                language="es-MX",
                action=f"{PUBLIC_BASE_URL}/process_speech?{params_str}",
                method="POST",
            )
            return Response(content=str(vr), media_type="application/xml")

        # Respuesta del LLM y siguiente turno
        reply = llm_reply(call_sid, user_text=user_text, force_intro=False)
        reply_ssml = to_ssml(reply, intensity=sess.get("intensity", 1))
        vr.say(reply_ssml, voice=VOICE, language="es-MX")
        
        vr.gather(
            input="speech",
            speech_timeout="auto",
            language="es-MX",
            action=f"{PUBLIC_BASE_URL}/process_speech?{params_str}",
            method="POST",
        )
        
        return Response(content=str(vr), media_type="application/xml")
    
    except Exception as e:
        print(f"Error en /process_speech: {e}")
        vr = VoiceResponse()
        vr.say("Disculpa, no pude procesar tu respuesta.", voice=VOICE, language="es-MX")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

@app.post("/twilio/amd_status")
async def twilio_amd_status(request: Request):
    """Callback de detección de contestadora (AMD)"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        answered_by = (form_data.get("AnsweredBy") or "").lower()  # human | machine_start | machine_end_beep | machine_end_silence | fax | unknown
        
        print(f"[AMD] CallSid={call_sid} | AnsweredBy={answered_by}")

        # Registrar en base de datos
        if SessionLocal and call_sid:
            try:
                with SessionLocal() as db:
                    log = db.query(ActionLog).filter_by(provider_sid=call_sid).first()
                    if log:
                        # Actualizar answered_by
                        log.answered_by = answered_by
                        
                        # Si es humano, marcar como contestada
                        if answered_by.startswith("human"):
                            log.answered = 1
                        # Si es máquina, marcar como no contestada
                        elif answered_by.startswith("machine"):
                            log.answered = 0
                            log.status = "machine"
                        
                        db.commit()
            except Exception as e:
                print(f"[AMD][WARN] persist failed: {e}")

        return Response(content="", status_code=204)
    
    except Exception as e:
        print(f"Error en /twilio/amd_status: {e}")
        return Response(content="", status_code=204)

# =========================================================
# WEBHOOK STATUS
# =========================================================
@app.post("/twilio/status")
async def twilio_status(request: Request):
    """Callback de estado de llamada Twilio"""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_stat = (form_data.get("CallStatus") or "").lower()  # initiated|ringing|in-progress|completed|busy|no-answer|failed|canceled
        event = (form_data.get("StatusCallbackEvent") or "").lower()  # initiated|ringing|answered|completed
        answered_by = (form_data.get("AnsweredBy") or "").lower()  # human|machine_*|unknown
        duration = int(form_data.get("CallDuration") or 0)  # solo en completed

        print(f"[STATUS] CallSid={call_sid} | Status={call_stat} | Event={event} | AnsweredBy={answered_by} | Duration={duration}")

        # Normaliza para tus KPIs/UI
        if call_stat in {"busy", "no-answer", "failed", "canceled"}:
            norm = "failed"
        elif call_stat in {"queued", "ringing", "initiated"}:
            norm = "queued"
        elif call_stat in {"in-progress", "answered"}:
            norm = "sent"
        elif call_stat == "completed":
            norm = "completed"
        else:
            norm = call_stat or event

        # ¿Se contestó?
        answered_flag = 1 if (event == "answered" or duration > 0 or (answered_by or "").startswith("human")) else 0

        # Terminales por CallStatus
        terminal = {"completed", "no-answer", "busy", "failed", "canceled"}
        end_status = call_stat if call_stat in terminal else None

        # Registrar en base de datos
        if SessionLocal and call_sid:
            try:
                with SessionLocal() as db:
                    log = db.query(ActionLog).filter_by(provider_sid=call_sid).first()

                    # Si no existe (raro), crea un registro mínimo
                    if not log:
                        log = ActionLog(
                            canal="call",
                            to="",
                            status=norm,
                            provider_sid=call_sid,
                            payload=f"[late webhook] event={event} status={call_stat}"
                        )
                        db.add(log)
                        db.flush()  # Para que tenga ID antes de actualizar

                    # Actualiza campos
                    log.status = norm or log.status
                    if end_status is not None:
                        log.end_status = end_status
                    log.answered = answered_flag
                    log.duration_sec = duration or 0
                    if answered_by:
                        log.answered_by = answered_by

                    db.commit()
            except Exception as e:
                print(f"[STATUS][WARN] DB persist failed: {e}")

        # Limpia la sesión si terminó/falló
        if (event == "completed") or (call_stat in {"no-answer", "busy", "failed", "canceled"}):
            SESSIONS.pop(call_sid, None)
            print(f"[STATUS] Sesión limpiada: {call_sid}")

        return Response(content="", status_code=204)

    except Exception as e:
        print(f"Error en /twilio/status: {e}")
        return Response(content="", status_code=204)


@app.post("/twilio/reconcile")
def twilio_reconcile():
    """
    Cierra llamadas en queued/sent consultando a Twilio.
    Usa ?minutes=60 (default) o ?call_sid=CAxxx para una específica.
    """
    minutes = int(request.args.get("minutes", "60"))
    call_sid_arg = request.args.get("call_sid")

    updated, errors = [], []

    terminal_map = {
        "completed": ("completed", "completed"),
        "busy": ("failed", "busy"),
        "no-answer": ("failed", "no-answer"),
        "failed": ("failed", "failed"),
        "canceled": ("failed", "canceled"),
    }

    with SessionLocal() as db:
        q = db.query(ActionLog).filter(ActionLog.canal=="call", ActionLog.status.in_(("queued","sent")))
        if not call_sid_arg:
            since = datetime.utcnow() - timedelta(minutes=minutes)
            q = q.filter(ActionLog.created_at >= since)
        else:
            q = q.filter(ActionLog.provider_sid == call_sid_arg)

        rows = q.all()

        for r in rows:
            try:
                tw_call = twilio_client.calls(r.provider_sid).fetch()
                cs = (tw_call.status or "").lower()              # queued|ringing|in-progress|completed|busy|no-answer|failed|canceled
                ab = (getattr(tw_call, "answered_by", "") or "").lower()
                dur = int(getattr(tw_call, "duration", 0) or 0)

                if cs in {"queued","ringing","in-progress"}:
                    continue  # sigue viva

                norm, end = terminal_map.get(cs, ("failed", cs or "failed"))
                r.status = norm
                r.end_status = end
                r.answered = 1 if (dur > 0 or ab.startswith("human")) else 0
                r.duration_sec = dur
                if ab:
                    r.answered_by = ab

                db.commit()
                updated.append(r.provider_sid)
            except TwilioRestException as te:
                errors.append({"sid": r.provider_sid, "err": f"{te.code} {te.msg}"})
            except Exception as e:
                errors.append({"sid": r.provider_sid, "err": str(e)})

    return jsonify(ok=True, updated=updated, errors=errors)



# ──────────────────────────────────────────────────────────────────────────────
# HEALTH CHECKS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    """Health check principal"""
    return {"status": "ok", "service": "Motor de Cobranza"}

@app.get("/health")
async def health_detailed():
    """Health check detallado"""
    return {
        "status": "ok",
        "dotenv_loaded": DOTENV_LOADED,
        "openai_configured": bool(OPENAI_API_KEY),
        "twilio_configured": twilio_client is not None,
        "db_configured": SessionLocal is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/ping")
async def api_ping():
    """Ping simple"""
    return {"ok": True, "now": datetime.utcnow().isoformat()}

# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD / MÉTRICAS (para Lovable)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/summary")
async def dashboard_summary(days: int = 30):
    """KPIs principales para el dashboard"""
    try:
        if not SessionLocal:
            # Datos mock si no hay DB
            return {
                "evaluaciones_hoy": 1,
                "evaluaciones_totales": 18,
                "porcentaje_alta": 50,
                "mensajes_enviados": 0,
                "promedio_dias_atraso": 19,
                "total_evaluaciones_periodo": 8,
                "cambio_evaluaciones": -20.0,
                "cambio_alta": 0.0,
                "cambio_mensajes": 0.0,
                "cambio_dias_atraso": 0.0
            }
        
        # Tu lógica real aquí con la DB
        return {
            "evaluaciones_hoy": 1,
            "evaluaciones_totales": 18,
            "porcentaje_alta": 50,
            "mensajes_enviados": 0,
            "promedio_dias_atraso": 19,
        }
    except Exception as e:
        print(f"Error en dashboard_summary: {e}")
        return {"error": str(e)}

@app.get("/api/metrics")
async def api_metrics(days: int = 30):
    """Métricas detalladas para gráficos"""
    try:
        days = max(1, min(days, 365))
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days)

        if not SessionLocal or not build_kpis:
            return {
                "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
                "kpis": {},
                "timeseries": []
            }

        with SessionLocal() as db:
            kpis = build_kpis(db, start_dt, end_dt)
            ts = build_timeseries(db, start_dt, end_dt)

        return {
            "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "kpis": kpis,
            "timeseries": ts,
        }
    except Exception as e:
        print(f"Error en api_metrics: {e}")
        return {"ok": False, "error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# EVALUACIONES / DECISIÓN
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/decision")
async def api_decision(request: Request):
    """Evalúa cliente y retorna estrategia"""
    try:
        data = await request.json()
        
        nombre = str(data.get("nombre", "Cliente")).strip()
        dpd = int(data.get("dias_atraso") or data.get("dpd") or 0)
        score = int(data.get("score") or 0)
        monto = float(data.get("monto") or 0.0)

        if not compute_decision:
            return {"error": "Módulo de decisión no disponible"}

        decision = compute_decision(nombre, dpd, score, monto)

        # Guardar en DB si está disponible
        if SessionLocal:
            with SessionLocal() as db:
                db.add(Evaluation(
                    nombre=nombre,
                    score=score,
                    dias_atraso=dpd,
                    monto=monto,
                    canal_sugerido=decision.get("canal_sugerido"),
                    mensaje=decision.get("mensaje"),
                ))
                db.commit()

        return {"ok": True, "decision": decision}
    
    except Exception as e:
        print(f"Error en api_decision: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/api/evaluations")
async def api_evaluations(limit: int = 20):
    """Lista de evaluaciones recientes"""
    try:
        if not SessionLocal:
            return {"ok": True, "items": []}

        with SessionLocal() as db:
            rows = (
                db.query(Evaluation)
                .order_by(Evaluation.created_at.desc())
                .limit(limit)
                .all()
            )
            
            items = []
            for r in rows:
                canal = (r.canal_sugerido or "").lower()
                accion_map = {
                    "call": "Llamar",
                    "whatsapp": "Enviar WhatsApp",
                    "sms": "Enviar SMS",
                    "email": "Enviar correo",
                }
                accion = accion_map.get(canal, "Sin acción")
                prioridad = "Alta" if (r.dias_atraso or 0) >= 15 else "Baja"

                items.append({
                    "id": r.id,
                    "fecha": r.created_at.isoformat(),
                    "cliente": r.nombre,
                    "score": r.score,
                    "dias": r.dias_atraso,
                    "monto": r.monto,
                    "accion": accion,
                    "prioridad": prioridad,
                    "canal": r.canal_sugerido,
                    "mensaje": r.mensaje,
                })
            
            return {"ok": True, "items": items}
    
    except Exception as e:
        print(f"Error en api_evaluations: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/api/execute_all")
async def api_execute_all(request: Request):
    """Ejecuta decisión de cobranza y dispara todos los canales"""
    try:
        data = await request.json()
        
        nombre   = (data.get("nombre") or "Cliente").strip()
        telefono = (data.get("telefono") or "").strip()
        email    = (data.get("email") or "").strip()
        score    = int(data.get("score") or 0)
        dpd      = int(data.get("dias_atraso") or data.get("dpd") or 0)
        monto    = float(data.get("monto") or 0.0)

        if not compute_decision:
            return {"ok": False, "error": "Módulo de decisión no disponible"}

        decision = compute_decision(nombre, dpd, score, monto)
        tpls     = decision.get("templates", {})
        nivel    = decision.get("nivel")
        min_parc = decision.get("min_parcial") if "min_parcial" in decision else None

        # --- 1) DISPARAR LLAMADA ---
        call_sid = None
        if telefono and twilio_client and PUBLIC_BASE_URL:
            params = {
                "nombre": nombre, "dias": dpd, "monto": monto, "score": score
            }
            if nivel:     params["nivel"] = nivel
            if min_parc:  params["min_parcial"] = min_parc

            twiml_url = f"{PUBLIC_BASE_URL}/voice?" + "&".join(
                [f"{k}={quote_plus(str(v))}" for k, v in params.items()]
            )

            try:
                amd_timeout = int(os.getenv("TWILIO_AMD_TIMEOUT", "8") or 8)
                base_kwargs = dict(
                    to=telefono,
                    from_=TWILIO_FROM_NUMBER,
                    url=twiml_url,
                    method="GET",
                    status_callback=f"{PUBLIC_BASE_URL}/twilio/status",
                    status_callback_method="POST",
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                )
                amd_kwargs_full = dict(
                    machine_detection="Enable",
                    machine_detection_timeout=amd_timeout,
                    async_amd=True,
                    amd_status_callback=f"{PUBLIC_BASE_URL}/twilio/amd_status",
                    amd_status_callback_method="POST",
                )
                import inspect
                allowed = set(inspect.signature(twilio_client.calls.create).parameters.keys())
                kwargs1 = {**base_kwargs, **{k: v for k, v in amd_kwargs_full.items() if k in allowed}}
                
                try:
                    call = twilio_client.calls.create(**kwargs1)
                except TypeError:
                    call = twilio_client.calls.create(**base_kwargs)

                call_sid = call.sid
                
                # Log en DB
                if SessionLocal:
                    with SessionLocal() as db:
                        db.add(ActionLog(
                            canal="call",
                            to=telefono,
                            status="queued",
                            provider_sid=call_sid,
                            payload=json.dumps({"decision": decision, "twiml_url": twiml_url}, ensure_ascii=False),
                            related_name=nombre
                        ))
                        db.commit()
            except Exception as e:
                print(f"Error al disparar llamada: {e}")
                if SessionLocal:
                    with SessionLocal() as db:
                        db.add(ActionLog(
                            canal="call",
                            to=telefono,
                            status="failed",
                            error=str(e),
                            related_name=nombre
                        ))
                        db.commit()

        # --- 2) DISPARAR CANALES DIGITALES a n8n ---
        n8n_req_id = f"req_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        n8n_payload = {
            "request_id": n8n_req_id,
            "nombre": nombre,
            "telefono": telefono,
            "email": email,
            "dpd": dpd,
            "score": score,
            "monto": monto,
            "nivel": nivel,
            "templates": {
                "whatsapp": tpls.get("whatsapp"),
                "sms":      tpls.get("sms"),
                "email": {
                    "subject": tpls.get("email_subject"),
                    "body":    tpls.get("email_body")
                }
            }
        }

        # Pre-log para KPIs
        if SessionLocal:
            with SessionLocal() as db:
                if tpls.get("whatsapp"):
                    db.add(ActionLog(
                        canal="whatsapp",
                        to=telefono,
                        status="queued",
                        provider_sid=f"{n8n_req_id}:wa",
                        related_name=nombre,
                        payload=json.dumps(n8n_payload, ensure_ascii=False)
                    ))
                if tpls.get("sms"):
                    db.add(ActionLog(
                        canal="sms",
                        to=telefono,
                        status="queued",
                        provider_sid=f"{n8n_req_id}:sms",
                        related_name=nombre,
                        payload=json.dumps(n8n_payload, ensure_ascii=False)
                    ))
                if tpls.get("email") and email:
                    db.add(ActionLog(
                        canal="email",
                        to=email,
                        status="queued",
                        provider_sid=f"{n8n_req_id}:mail",
                        related_name=nombre,
                        payload=json.dumps(n8n_payload, ensure_ascii=False)
                    ))
                db.commit()

        # Enviar a n8n si está configurado
        n8n_resp = {}
        if N8N_WEBHOOK_NOTIFY:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.post(N8N_WEBHOOK_NOTIFY, json=n8n_payload, timeout=10.0)
                    n8n_resp = resp.json() if resp.status_code == 200 else {"error": resp.text}
            except Exception as e:
                print(f"Error enviando a n8n: {e}")
                n8n_resp = {"error": str(e)}

        return {
            "ok": True,
            "decision": decision,
            "call_sid": call_sid,
            "n8n": n8n_resp
        }
    
    except Exception as e:
        print(f"Error en api_execute_all: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/api/history")
async def api_history(limit: int = 200):
    """Historial de acciones"""
    try:
        if not SessionLocal:
            return []

        with SessionLocal() as db:
            rows = (
                db.query(ActionLog)
                .order_by(ActionLog.created_at.desc())
                .limit(limit)
                .all()
            )
            
            return [{
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "canal": r.canal,
                "to": r.to,
                "status": r.status,
                "provider_sid": r.provider_sid,
                "error": r.error,
                "related_name": r.related_name,
                "answered": bool(r.answered) if hasattr(r, 'answered') else False,
                "end_status": r.end_status if hasattr(r, 'end_status') else None,
                "duration_sec": r.duration_sec if hasattr(r, 'duration_sec') else None,
            } for r in rows]
    
    except Exception as e:
        print(f"Error en api_history: {e}")
        return []

# ──────────────────────────────────────────────────────────────────────────────
# ERP ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/erp/invoices/unpaid")
async def erp_invoices_unpaid(
    limit: int = 25,
    offset: int = 0,
    q: str = None,
    order_by: str = "due_date asc",
    include_draft: bool = False
):
    """Lista facturas impagas desde ERP"""
    try:
        if not list_unpaid_invoices:
            return {"ok": False, "error": "ERP client no disponible"}

        rows = list_unpaid_invoices(
            limit=limit,
            offset=offset,
            q=q,
            order_by=order_by,
            include_draft=include_draft
        )

        items = [{
            "invoice_id": inv.get("name"),
            "customer_id": inv.get("customer"),
            "due_date": inv.get("due_date"),
            "dias_atraso": calc_dias_atraso(inv.get("due_date")) if calc_dias_atraso else 0,
            "amount": inv.get("outstanding_amount"),
            "grand_total": inv.get("grand_total"),
            "status": inv.get("status"),
            "company": inv.get("company"),
            "currency": inv.get("currency"),
        } for inv in rows]

        return {"ok": True, "count": len(items), "items": items}
    
    except Exception as e:
        print(f"Error en erp_invoices_unpaid: {e}")
        return {"ok": False, "error": str(e)}

@app.post("/erp/trigger-cobranza")
async def erp_trigger_cobranza(request: Request):
    """Dispara proceso de cobranza para una factura"""
    try:
        data = await request.json()
        invoice_name = data.get("invoice")
        
        if not invoice_name:
            return {"ok": False, "error": "Falta parámetro 'invoice'"}

        if not get_invoice:
            return {"ok": False, "error": "ERP client no disponible"}

        inv = get_invoice(invoice_name)
        if not inv:
            return {"ok": False, "error": f"Factura '{invoice_name}' no encontrada"}

        dias = calc_dias_atraso(inv.get("due_date")) if calc_dias_atraso else 0
        monto = float(inv.get("outstanding_amount") or 0.0)
        nombre = inv.get("customer") or "Cliente"

        # Decisión
        dec_payload = {
            "nombre": nombre,
            "score": 60,
            "dias_atraso": dias,
            "monto": monto,
        }
        
        decision = compute_decision(dec_payload) if compute_decision else {}

        return {
            "ok": True,
            "invoice": inv["name"],
            "cliente": nombre,
            "status": inv.get("status"),
            "due_date": inv.get("due_date"),
            "dias_atraso": dias,
            "monto": monto,
            "decision": decision,
        }
    
    except Exception as e:
        print(f"Error en erp_trigger_cobranza: {e}")
        return {"ok": False, "error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# VOZ (Twilio) - Solo si Twilio está configurado
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/voice")
@app.get("/voice")
async def voice(
    request: Request,
    nombre: str = "Cliente",
    dias: str = "0",
    monto: str = "0",
    score: str = "0",
    nivel: str = None,
    min_parcial: str = None,
):
    """Endpoint inicial de llamada Twilio"""
    try:
        if not twilio_client or not llm:
            return PlainTextResponse("Servicio de voz no disponible", status_code=503)

        # Tu lógica de voz aquí (igual que antes)
        call_sid = request.query_params.get("CallSid", "no_sid")
        
        # Respuesta TwiML básica
        vr = VoiceResponse()
        vr.say(f"Hola {nombre}, tenemos un saldo pendiente de {monto} pesos.", 
               voice=VOICE, language="es-MX")
        
        return Response(content=str(vr), media_type="application/xml")
    
    except Exception as e:
        print(f"Error en /voice: {e}")
        return PlainTextResponse(f"Error: {str(e)}", status_code=500)

# ──────────────────────────────────────────────────────────────────────────────
# INICIAR SERVIDOR
# ──────────────────────────────────────────────────────────────────────────────
# Montar Flask en FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
app.mount("/", WSGIMiddleware(flask_app))  # ← Nota: cambié /llm a /
print("✅ Flask montado en FastAPI")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "5050"))
    print("\n" + "="*60)
    print("🚀 MOTOR DE COBRANZA - INICIANDO")
    print("="*60)
    print(f"📍 API: http://localhost:{port}")
    print(f"📍 Docs: http://localhost:{port}/docs")
    print(f"📍 LLM: {LLM_MODEL}")
    print(f"📍 Twilio: {'✅' if twilio_client else '❌'}")
    print(f"📍 DB: {'✅' if SessionLocal else '❌'}")
    print("="*60 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )