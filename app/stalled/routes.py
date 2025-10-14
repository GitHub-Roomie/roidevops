import os
from typing import Any, Dict
from fastapi import HTTPException
from datetime import datetime, timedelta

# OpenAI SDK
from openai import OpenAI

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, case
# 🔴 Antes (mal): from ..db ... / from ..models ...
# ✅ Ahora (bien): todo sale de services/db.py
from ..services.db import SessionLocal, Evaluation, ActionLog
router = APIRouter()

# dentro de routes.py (añade esto debajo del encabezado anterior)

class StalledItem(BaseModel):
    evaluation_id: int
    nombre: Optional[str]
    dias_atraso: int
    monto: float
    score: int
    intentos_30d: Dict[str, int]
    respuestas_30d: Dict[str, int]
    ultima_interaccion: Optional[str] = None

@router.get("/api/invoices/stalled", response_model=List[StalledItem])
def list_stalled_invoices(
    days_min: int = Query(30, ge=1),
    lookback_days: int = Query(30, ge=7, le=90),
    min_attempts: int = Query(3, ge=1, le=20),
):
    """
    Evaluaciones con dias_atraso >= days_min y SIN respuesta
    en los últimos 'lookback_days', pese a intentos >= min_attempts.
    Identificamos por Evaluation.id y (si aplica) ActionLog.related_name.
    """
    now = datetime.utcnow()
    since = now - timedelta(days=lookback_days)

    with SessionLocal() as db:
        evals = db.execute(
            select(Evaluation).where(Evaluation.dias_atraso >= days_min)
        ).scalars().all()
        if not evals:
            return []

        # Agregamos por related_name (si guardas "eval:<id>" o "<id>" allí)
        q_act = (
            select(
                ActionLog.related_name.label("rel"),
                func.max(ActionLog.created_at).label("last_at"),
                func.sum(case((ActionLog.canal=="call"),     1, else_=0)).label("try_call"),
                func.sum(case((ActionLog.canal=="whatsapp"), 1, else_=0)).label("try_wa"),
                func.sum(case((ActionLog.canal=="sms"),      1, else_=0)).label("try_sms"),
                func.sum(case((ActionLog.canal=="email"),    1, else_=0)).label("try_email"),
                # qué cuenta como "respuesta" (ajústalo a tus reglas)
                func.sum(case((ActionLog.canal=="call")     & (ActionLog.status.in_(["completed"])), 1, else_=0)).label("resp_call"),
                func.sum(case((ActionLog.canal=="whatsapp") & (ActionLog.status.in_(["read"])),      1, else_=0)).label("resp_wa"),
                func.sum(case((ActionLog.canal=="sms")      & (ActionLog.status.in_(["inbound"])),   1, else_=0)).label("resp_sms"),
                func.sum(case((ActionLog.canal=="email")    & (ActionLog.status.in_(["replied"])),   1, else_=0)).label("resp_email"),
            )
            .where(ActionLog.created_at >= since)
            .group_by(ActionLog.related_name)
        )
        act = { (r.rel or ""): dict(r._mapping) for r in db.execute(q_act).all() }

        items: List[StalledItem] = []
        for e in evals:
            # intenta resolver el "rel" tal como lo guardes en action_logs
            keys = [str(e.id), f"eval:{e.id}", e.nombre or ""]
            a = {}
            for k in keys:
                if k and k in act:
                    a = act[k]; break

            total_attempts = sum(int(a.get(k,0) or 0) for k in ["try_call","try_wa","try_sms","try_email"])
            total_responses = sum(int(a.get(k,0) or 0) for k in ["resp_call","resp_wa","resp_sms","resp_email"])

            if total_attempts >= min_attempts and total_responses == 0:
                items.append(StalledItem(
                    evaluation_id=e.id,
                    nombre=e.nombre,
                    dias_atraso=int(e.dias_atraso or 0),
                    monto=float(e.monto or 0),
                    score=int(e.score or 0),
                    intentos_30d={
                        "call": int(a.get("try_call",0) or 0),
                        "whatsapp": int(a.get("try_wa",0) or 0),
                        "sms": int(a.get("try_sms",0) or 0),
                        "email": int(a.get("try_email",0) or 0),
                    },
                    respuestas_30d={
                        "call": int(a.get("resp_call",0) or 0),
                        "whatsapp": int(a.get("resp_wa",0) or 0),
                        "sms": int(a.get("resp_sms",0) or 0),
                        "email": int(a.get("resp_email",0) or 0),
                    },
                    ultima_interaccion=(a.get("last_at").isoformat()+"Z") if a.get("last_at") else None,
                ))

        items.sort(key=lambda x: (x.dias_atraso, x.monto), reverse=True)
        return items


# ---------- Modelos de respuesta ----------
class StalledItem(BaseModel):
    invoice_id: str
    org_id: Optional[str]
    customer_id: Optional[str]
    cliente: Optional[str]
    telefono: Optional[str]
    dias_atraso: int
    monto: float
    score: int
    intentos_30d: Dict[str, int]
    respuestas_30d: Dict[str, int]
    ultima_interaccion: Optional[str] = None

class StrategyIn(BaseModel):
    genero: Optional[Literal["M","F"]] = None
    edad: Optional[int] = None
    canal_respuesta: Literal["whatsapp","sms","voice","email"]
    monto_deuda: float
    dias_atraso: int
    score: int

class StrategyOut(BaseModel):
    canal: str
    monto_estimado_recuperacion: float
    horario_recomendado: str
    mensaje_sugerido: str
    acciones: List[str]

# ---------- Heurísticas de estrategia (rule-based) ----------


def _franja_horaria(edad: Optional[int], canal: str) -> str:
    if canal in ("whatsapp","sms"):
        return "10:30–13:00 y 17:30–20:30 (hora local)"
    if canal == "voice":
        return "09:00–12:00 y 16:00–19:30 (hora local)"
    return "12:00–16:00 (hora local)"

def _recuperacion_estimada(monto: float, dias: int, score: int) -> float:
    base = 0.55 if score>=80 else (0.40 if score>=65 else 0.25)
    pen  = 0.10 if dias>=30 else (0.05 if dias>=20 else 0.0)
    return round(monto * max(0.05, base - pen), 2)

def _mensaje(genero: Optional[str], canal: str, monto: float, dias: int, score: int, tono: str) -> str:
    saludo = "Hola" + (", estimado" if genero=="M" else (", estimada" if genero=="F" else ""))
    cuerpo = (
        f"{saludo}. Soy Sofía de cobranza. "
        f"{dias} días de atraso y saldo ${monto:,.2f}. "
        f"{'Necesitamos regularizar hoy para evitar escalamiento. ' if tono=='firme' else ''}"
        f"Propongo un abono inicial inmediato y programar el resto en fechas específicas."
    )
    cierre = "Puedo enviarte la ficha y confirmar por este medio." if canal in ("whatsapp","sms") else "¿Te viene bien hacerlo ahora? Puedo dictarte los datos."
    return f"{cuerpo} {cierre}"


def suggest_strategy(body: StrategyIn) -> StrategyOut:
    canal = body.canal_respuesta
    tono = "firme" if (body.dias_atraso>=20 or body.score<70 or body.monto_deuda>=10000) else "amable"
    horario = _franja_horaria(body.edad, canal)
    recuperacion = _recuperacion_estimada(body.monto_deuda, body.dias_atraso, body.score)
    msg = _mensaje(body.genero, body.edad, canal, body.monto_deuda, body.dias_atraso, body.score, tono)
    acciones = [
        f"Contactar por {canal} en {horario}.",
        "Pedir abono inicial hoy (mínimo 5–10% si el saldo lo permite).",
        "Si duda: ofrecer plan en 2–4 parcialidades con fechas exactas.",
        "Registrar compromiso y solicitar evidencia (comprobante o SPEI programado).",
        "Si incumple nuevamente: escalar a supervisor y ofrecer reestructura o liquidación condicionada."
    ]
    return StrategyOut(
        canal=canal,
        monto_estimado_recuperacion=recuperacion,
        horario_recomendado=horario,
        mensaje_sugerido=msg,
        acciones=acciones
    )

# ---------- Endpoint 1: listar facturas estancadas ----------
@router.get("/api/invoices/stalled", response_model=List[StalledItem])
def list_stalled_invoices(
    days_min: int = Query(30, ge=1),
    lookback_days: int = Query(30, ge=7, le=90),
    min_attempts: int = Query(3, ge=1, le=20),
):
    """
    Facturas con dias_atraso >= days_min y SIN respuesta reciente,
    pese a intentos ≥ min_attempts en los últimos lookback_days.
    """
    now = datetime.utcnow()
    since = now - timedelta(days=lookback_days)

    with SessionLocal() as db:
        evals = db.execute(
            select(Evaluation).where(Evaluation.dias_atraso >= days_min)
        ).scalars().all()
        if not evals:
            return []

        q_act = (
            select(
                ActionLog.to.label("to"),
                func.max(ActionLog.created_at).label("last_at"),
                # intentos
                func.sum(case((ActionLog.canal=="voice"), 1, else_=0)).label("try_voice"),
                func.sum(case((ActionLog.canal=="whatsapp"), 1, else_=0)).label("try_wa"),
                func.sum(case((ActionLog.canal=="sms"), 1, else_=0)).label("try_sms"),
                func.sum(case((ActionLog.canal=="email"), 1, else_=0)).label("try_email"),
                # "respuestas" (ajusta a tus criterios)
                func.sum(case((ActionLog.canal=="voice") & (ActionLog.status.in_(["answered","in-progress","completed"])),1, else_=0)).label("resp_voice"),
                func.sum(case((ActionLog.canal=="whatsapp") & (ActionLog.status.in_(["read"])),1, else_=0)).label("resp_wa"),
                func.sum(case((ActionLog.canal=="sms") & (ActionLog.status.in_(["inbound"])),1, else_=0)).label("resp_sms"),
                func.sum(case((ActionLog.canal=="email") & (ActionLog.status.in_(["opened","clicked","replied"])),1, else_=0)).label("resp_email"),
            )
            .where(ActionLog.created_at >= since)
            .group_by(ActionLog.to)
        )
        act = {r.to: dict(r._mapping) for r in db.execute(q_act).all()}

        items: List[StalledItem] = []
        for e in evals:
            tel = e.telefono
            a = act.get(tel, {})
            total_attempts = sum(int(a.get(k,0) or 0) for k in ["try_voice","try_wa","try_sms","try_email"])
            total_responses = sum(int(a.get(k,0) or 0) for k in ["resp_voice","resp_wa","resp_sms","resp_email"])

            if total_attempts >= min_attempts and total_responses == 0:
                items.append(StalledItem(
                    invoice_id=e.invoice_id,
                    org_id=e.org_id,
                    customer_id=e.customer_id,
                    cliente=(e.meta_json or {}).get("cliente"),
                    telefono=tel,
                    dias_atraso=int(e.dias_atraso or 0),
                    monto=float(e.monto or 0),
                    score=int(e.score or 0),
                    intentos_30d={
                        "voice": int(a.get("try_voice",0) or 0),
                        "whatsapp": int(a.get("try_wa",0) or 0),
                        "sms": int(a.get("try_sms",0) or 0),
                        "email": int(a.get("try_email",0) or 0),
                    },
                    respuestas_30d={
                        "voice": int(a.get("resp_voice",0) or 0),
                        "whatsapp": int(a.get("resp_wa",0) or 0),
                        "sms": int(a.get("resp_sms",0) or 0),
                        "email": int(a.get("resp_email",0) or 0),
                    },
                    ultima_interaccion=(a.get("last_at").isoformat() + "Z") if a.get("last_at") else None,
                ))

        items.sort(key=lambda x: (x.dias_atraso, x.monto), reverse=True)
        return items

# ---------- Endpoint 2: estrategia por factura ----------
@router.get("/api/invoices/{invoice_id}/strategy", response_model=StrategyOut)
def strategy_for_invoice(invoice_id: str):
    with SessionLocal() as db:
        e = db.query(Evaluation).filter(Evaluation.invoice_id == invoice_id).first()
        if not e:
            raise HTTPException(status_code=404, detail="Factura no encontrada")
        meta = e.meta_json or {}
        genero = (meta.get("genero") or meta.get("gender") or None)
        edad = meta.get("edad") or meta.get("age")
        canal_pref = (meta.get("canal_preferido") or "whatsapp")  # fallback

        body = StrategyIn(
            genero=genero,
            edad=edad,
            canal_respuesta=canal_pref,
            monto_deuda=float(e.monto or 0),
            dias_atraso=int(e.dias_atraso or 0),
            score=int(e.score or 0),
        )
    return suggest_strategy(body)



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Utilidad para canal con más respuesta en últimos 30 días ---
def _canal_preferido_por_logs(db, evaluation_id: int) -> str:
    since = datetime.utcnow() - timedelta(days=30)
    # Asumimos que guardas el vínculo en related_name="eval:<id>"
    rel = f"eval:{evaluation_id}"
    rows = db.execute(
        select(
            ActionLog.canal,
            func.sum(case((ActionLog.status.in_(["completed","replied","inbound","read","opened","clicked"])), 1, else_=0)).label("score")
        ).where(ActionLog.created_at >= since, ActionLog.related_name == rel)
         .group_by(ActionLog.canal)
    ).all()
    if not rows:
        return "whatsapp"  # fallback razonable
    rows = sorted(rows, key=lambda r: r.score or 0, reverse=True)
    best = rows[0].canal or "whatsapp"
    # normaliza a tus 4 valores
    return {"call": "voice"}.get(best, best)

# --- JSON Schema para salida estricta ---
NEGOTIATION_SCHEMA: Dict[str, Any] = {
    "name": "NegotiationPlan",
    "schema": {
        "type": "object",
        "properties": {
            "canal_recomendado": {"type": "string", "enum": ["whatsapp","sms","voice","email"]},
            "monto_estimado_recuperacion": {"type": "number"},
            "ventana_horaria": {"type": "string"},
            "mensaje_sugerido": {"type": "string"},
            "acciones_siguientes": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1
            },
            "riesgos_o_barreras": {
                "type": "array",
                "items": {"type": "string"}
            },
            "racional": {"type": "string"}
        },
        "required": [
            "canal_recomendado",
            "monto_estimado_recuperacion",
            "ventana_horaria",
            "mensaje_sugerido",
            "acciones_siguientes",
            "racional"
        ],
        "additionalProperties": False
    },
    "strict": True
}

# --- Helpers de elegibilidad ---
from datetime import datetime, timedelta

def _stalled_stats(db, evaluation_id: int, days_min: int = 30, lookback_days: int = 30, min_attempts: int = 3):
    """Devuelve (eligible:bool, reason:str, stats:dict) para un caso."""
    e = db.get(Evaluation, evaluation_id)
    if not e:
        return False, "Evaluación no encontrada", {}

    if (e.dias_atraso or 0) < days_min:
        return False, f"Días de atraso < {days_min}", {"dias_atraso": e.dias_atraso}

    since = datetime.utcnow() - timedelta(days=lookback_days)
    rel = f"eval:{evaluation_id}"

    row = db.execute(
        select(
            func.sum(case((ActionLog.canal=="call"),     1, else_=0)).label("try_call"),
            func.sum(case((ActionLog.canal=="whatsapp"), 1, else_=0)).label("try_wa"),
            func.sum(case((ActionLog.canal=="sms"),      1, else_=0)).label("try_sms"),
            func.sum(case((ActionLog.canal=="email"),    1, else_=0)).label("try_email"),
            # responde/”acercamiento” (ajusta a tu criterio):
            func.sum(case((ActionLog.canal=="call")     & (ActionLog.status.in_(["completed"])), 1, else_=0)).label("resp_call"),
            func.sum(case((ActionLog.canal=="whatsapp") & (ActionLog.status.in_(["replied","inbound"])), 1, else_=0)).label("resp_wa"),
            func.sum(case((ActionLog.canal=="sms")      & (ActionLog.status.in_(["inbound"])), 1, else_=0)).label("resp_sms"),
            func.sum(case((ActionLog.canal=="email")    & (ActionLog.status.in_(["replied"])), 1, else_=0)).label("resp_email"),
        ).where(ActionLog.created_at >= since, ActionLog.related_name == rel)
    ).first()

    tries = sum(int(getattr(row, k) or 0) for k in ["try_call","try_wa","try_sms","try_email"]) if row else 0
    resps = sum(int(getattr(row, k) or 0) for k in ["resp_call","resp_wa","resp_sms","resp_email"]) if row else 0

    if tries < min_attempts:
        return False, f"Intentos en {lookback_days}d < {min_attempts} (={tries})", {"tries": tries, "responses": resps}
    if resps > 0:
        return False, f"Ya hubo respuesta reciente (={resps})", {"tries": tries, "responses": resps}

    return True, "Elegible para estrategia LLM (estancado)", {"tries": tries, "responses": resps, "dias_atraso": e.dias_atraso}


@router.get("/api/evaluations/{evaluation_id}/strategy_llm")
def strategy_llm_for_evaluation(evaluation_id: int):
    with SessionLocal() as db:
        e = db.get(Evaluation, evaluation_id)
        if not e:
            raise HTTPException(status_code=404, detail="Evaluación no encontrada")
        
        eligible, reason, stats = _stalled_stats(db, evaluation_id, days_min=30, lookback_days=30, min_attempts=3)
        if not eligible:
            # Rechaza la generación si no cumple los criterios de “estancado”
            raise HTTPException(status_code=409, detail={"reason": reason, "stats": stats})

        canal_pref = _canal_preferido_por_logs(db, e.id)

        # --- Mensajes para el modelo (System + User) ---
        system_msg = (
            "Actúa como un experto negociador para recuperación de deudas en México. "
            "Objetivo: maximizar recuperación sin prácticas agresivas ni ilegales. "
            "Respeta horarios razonables, evita amenazas y ofrece opciones claras. "
            "Responde SOLO en español y SOLO con el JSON del esquema."
        )

        user_msg = (
            f"Contexto del deudor:\n"
            f"- Género: desconocido\n"  # si luego lo tienes, pásalo aquí
            f"- Edad: desconocida\n"
            f"- Canal con más respuesta: {canal_pref}\n"
            f"- Monto de la deuda: {float(e.monto or 0):.2f}\n"
            f"- Días de atraso: {int(e.dias_atraso or 0)}\n"
            f"- Score crediticio: {int(e.score or 0)}\n\n"
            f"Devuelve una estrategia detallada indicando: canal recomendado, monto estimado de recuperación, "
            f"ventana horaria sugerida, mensaje sugerido (breve y directo), acciones siguientes, riesgos/barreras y la lógica (racional)."
        )

        try:
            # --- Responses API con Structured Outputs ---
            result = client.responses.create(
                model="gpt-4o-mini",  # rápido y económico; puedes cambiar por un modelo reasoning si prefieres
                input=[
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                response_format={"type": "json_schema", "json_schema": NEGOTIATION_SCHEMA},
                temperature=0.3,
            )
            data = result.output_parsed  # ya es dict validado contra el schema
            return {"ok": True, "evaluation_id": e.id, "strategy": data}
        except Exception as ex:
            # Fallback: usa tu regla heurística existente
            tono = "firme" if (e.dias_atraso>=20 or (e.score or 0)<70 or (e.monto or 0)>=10000) else "amable"
            ventana = "10:30–13:00 y 17:30–20:30 (hora local)" if canal_pref in ("whatsapp","sms") else "09:00–12:00 y 16:00–19:30 (hora local)"
            prob_base = 0.55 if (e.score or 0)>=80 else (0.40 if (e.score or 0)>=65 else 0.25)
            pen = 0.10 if (e.dias_atraso or 0)>=30 else (0.05 if (e.dias_atraso or 0)>=20 else 0.0)
            monto_est = round(float(e.monto or 0) * max(0.05, prob_base - pen), 2)
            msg = (
                f"Hola. Soy Sofía de cobranza. {int(e.dias_atraso or 0)} días de atraso y saldo ${float(e.monto or 0):,.2f}. "
                f"{'Necesitamos regularizar hoy para evitar escalamiento. ' if tono=='firme' else ''}"
                f"Propongo un abono inicial inmediato y programar el resto en fechas específicas."
            )
            return {
                "ok": True, "evaluation_id": e.id,
                "strategy": {
                    "canal_recomendado": canal_pref,
                    "monto_estimado_recuperacion": monto_est,
                    "ventana_horaria": ventana,
                    "mensaje_sugerido": msg,
                    "acciones_siguientes": [
                        f"Contactar por {canal_pref} en {ventana}.",
                        "Pedir abono inicial hoy (mínimo 5–10%).",
                        "Si duda: ofrecer plan en 2–4 parcialidades.",
                        "Registrar compromiso y evidencia (comprobante o SPEI programado).",
                        "Si incumple: escalar y ofrecer reestructura o liquidación condicionada."
                    ],
                    "riesgos_o_barreras": ["Promesas incumplidas", "Liquidez limitada", "Contacto fuera de horario"],
                    "racional": "Fallback heurístico por error de API."
                }
            }
