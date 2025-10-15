# app/stalled_flask.py
# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import select, func, case
from typing import Dict, Any
import os

from app.services.db import SessionLocal, Evaluation, ActionLog

bp = Blueprint("stalled", __name__, url_prefix="/api")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _canal_preferido_por_logs(db, evaluation_id: int) -> str:
    since = datetime.utcnow() - timedelta(days=30)
    rel = f"eval:{evaluation_id}"

    rows = db.execute(
        select(
            ActionLog.canal,
            func.sum(
                case(((ActionLog.status.in_(["completed","replied","inbound","read","opened","clicked"])), 1), else_=0)
            ).label("score")
        )
        .where(ActionLog.created_at >= since, ActionLog.related_name == rel)
        .group_by(ActionLog.canal)
    ).all()

    if not rows:
        return "whatsapp"  # sin señales: preferir WA

    rows = sorted(rows, key=lambda r: (r.score or 0), reverse=True)
    top = rows[0]
    if (top.score or 0) <= 0:
        return "whatsapp"  # señales nulas: preferir WA

    best = top.canal or "whatsapp"
    return {"call": "voice"}.get(best, best)



def _stalled_stats(db, evaluation_id: int, days_min=30, lookback_days=30, min_attempts=3):
    """
    Devuelve (eligible:bool, reason:str, stats:dict) para un caso “estancado”.
    Regla: dias_atraso >= days_min AND intentos >= min_attempts AND respuestas == 0.
    """
    e = db.get(Evaluation, evaluation_id)
    if not e:
        return False, "Evaluación no encontrada", {}

    if (e.dias_atraso or 0) < days_min:
        return False, f"Días de atraso < {days_min}", {"dias_atraso": e.dias_atraso}

    since = datetime.utcnow() - timedelta(days=lookback_days)
    rel = f"eval:{evaluation_id}"

    row = db.execute(
        select(
            # intentos por canal
            func.sum(case(((ActionLog.canal == "call"),     1), else_=0)).label("try_call"),
            func.sum(case(((ActionLog.canal == "whatsapp"), 1), else_=0)).label("try_wa"),
            func.sum(case(((ActionLog.canal == "sms"),      1), else_=0)).label("try_sms"),
            func.sum(case(((ActionLog.canal == "email"),    1), else_=0)).label("try_email"),
            # respuestas por canal (ajusta a tu definición)
            func.sum(case((((ActionLog.canal == "call")     & (ActionLog.status.in_(["completed"]))), 1), else_=0)).label("resp_call"),
            func.sum(case((((ActionLog.canal == "whatsapp") & (ActionLog.status.in_(["replied", "inbound"]))), 1), else_=0)).label("resp_wa"),
            func.sum(case((((ActionLog.canal == "sms")      & (ActionLog.status.in_(["inbound"]))), 1), else_=0)).label("resp_sms"),
            func.sum(case((((ActionLog.canal == "email")    & (ActionLog.status.in_(["replied"]))), 1), else_=0)).label("resp_email"),
        )
        .where(ActionLog.created_at >= since, ActionLog.related_name == rel)
    ).first()

    tries = 0
    resps = 0
    if row:
        tries = sum(int(getattr(row, k) or 0) for k in ["try_call", "try_wa", "try_sms", "try_email"])
        resps = sum(int(getattr(row, k) or 0) for k in ["resp_call", "resp_wa", "resp_sms", "resp_email"])

    if tries < min_attempts:
        return False, f"Intentos en {lookback_days}d < {min_attempts} (={tries})", {"tries": tries, "responses": resps}
    if resps > 0:
        return False, f"Ya hubo respuesta reciente (={resps})", {"tries": tries, "responses": resps}

    return True, "Elegible para estrategia LLM (estancado)", {
        "tries": tries, "responses": resps, "dias_atraso": e.dias_atraso
    }

def _get_openai_client():
    # import perezoso para no romper el arranque si falta la lib/clave
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


import json  # ← MOVER AQUÍ ARRIBA (fuera de la función)

def _llm_negotiation_strategy(client, model, system_msg, user_msg, json_schema):
    """
    Llama a OpenAI con Structured Outputs.
    Devuelve (strategy_dict, source_str).
    """
    try:
        # Usar Chat Completions con JSON Schema
        result = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": json_schema
            },
            temperature=0.3,
        )
        
        # Parsear la respuesta
        content = result.choices[0].message.content
        data = json.loads(content)
        return data, "llm"
        
    except Exception as e:
        print(f"❌ Error llamando a OpenAI: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: sin JSON Schema
        prompt_user = (
            user_msg
            + "\n\nIMPORTANTE: Devuelve SOLO un JSON válido. "
            + "Propiedades requeridas: canal_recomendado, monto_estimado_recuperacion, "
            + "probabilidad_recuperacion, primer_abono_sugerido, ventana_horaria, "
            + "mensaje_sugerido, acciones_siguientes, racional."
        )

        try:
            cc = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg + " Responde únicamente con JSON válido."},
                    {"role": "user", "content": prompt_user},
                ],
                temperature=0.3,
            )
            
            text = cc.choices[0].message.content or "{}"
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("El modelo no devolvió JSON válido.")
            data = json.loads(text[start:end+1])
            return data, "llm-chat"
        except Exception as e2:
            print(f"❌ Fallback también falló: {e2}")
            raise
# -------------------------------------------------------------------
# 1) Listado de “estancadas”
# -------------------------------------------------------------------
@bp.get("/invoices/stalled")
def list_stalled():
    days_min      = int(request.args.get("days_min", 30))
    lookback_days = int(request.args.get("lookback_days", 30))
    min_attempts  = int(request.args.get("min_attempts", 3))

    with SessionLocal() as db:
        evals = db.execute(
            select(Evaluation).where(Evaluation.dias_atraso >= days_min)
        ).scalars().all()

        since = datetime.utcnow() - timedelta(days=lookback_days)

        # Agregados por related_name en la ventana
        rows = db.execute(
            select(
                ActionLog.related_name.label("rel"),
                func.max(ActionLog.created_at).label("last_at"),

                func.sum(case(((ActionLog.canal == "call"),     1), else_=0)).label("try_call"),
                func.sum(case(((ActionLog.canal == "whatsapp"), 1), else_=0)).label("try_wa"),
                func.sum(case(((ActionLog.canal == "sms"),      1), else_=0)).label("try_sms"),
                func.sum(case(((ActionLog.canal == "email"),    1), else_=0)).label("try_email"),

                func.sum(case((((ActionLog.canal == "call")     & (ActionLog.status.in_(["completed"]))), 1), else_=0)).label("resp_call"),
                func.sum(case((((ActionLog.canal == "whatsapp") & (ActionLog.status.in_(["replied", "inbound"]))), 1), else_=0)).label("resp_wa"),
                func.sum(case((((ActionLog.canal == "sms")      & (ActionLog.status.in_(["inbound"]))), 1), else_=0)).label("resp_sms"),
                func.sum(case((((ActionLog.canal == "email")    & (ActionLog.status.in_(["replied"]))), 1), else_=0)).label("resp_email"),
            )
            .where(ActionLog.created_at >= since)
            .group_by(ActionLog.related_name)
        ).all()

        act_map: Dict[str, Dict[str, Any]] = { (r.rel or ""): dict(r._mapping) for r in rows }

        items = []
        for e in evals:
            rel = f"eval:{e.id}"
            a = act_map.get(rel, {})
            total_attempts = sum(int(a.get(k, 0) or 0) for k in ["try_call", "try_wa", "try_sms", "try_email"])
            total_responses = sum(int(a.get(k, 0) or 0) for k in ["resp_call", "resp_wa", "resp_sms", "resp_email"])
            if total_attempts >= min_attempts and total_responses == 0:
                items.append({
                    "evaluation_id": e.id,
                    "nombre": e.nombre,
                    "dias_atraso": int(e.dias_atraso or 0),
                    "monto": float(e.monto or 0),
                    "score": int(e.score or 0),
                    "intentos_30d": {
                        "call": int(a.get("try_call",0) or 0),
                        "whatsapp": int(a.get("try_wa",0) or 0),
                        "sms": int(a.get("try_sms",0) or 0),
                        "email": int(a.get("try_email",0) or 0),
                    },
                    "respuestas_30d": {
                        "call": int(a.get("resp_call",0) or 0),
                        "whatsapp": int(a.get("resp_wa",0) or 0),
                        "sms": int(a.get("resp_sms",0) or 0),
                        "email": int(a.get("resp_email",0) or 0),
                    },
                    "ultima_interaccion": (a.get("last_at").isoformat()+"Z") if a.get("last_at") else None,
                })

        items.sort(key=lambda x: (x["dias_atraso"], x["monto"]), reverse=True)
        return jsonify(items), 200


# -------------------------------------------------------------------
# 2) Estrategia LLM (con guard de elegibilidad)
# -------------------------------------------------------------------

NEGOTIATION_SCHEMA = {
    "name": "NegotiationPlan",
    "schema": {
        "type": "object",
        "properties": {
            "canal_recomendado": {"type": "string", "enum": ["whatsapp","sms","voice","email"]},
            "monto_estimado_recuperacion": {"type": "number"},
            "probabilidad_recuperacion": {"type": "number"},
            "primer_abono_sugerido": {"type": "number"},
            "ventana_horaria": {"type": "string"},
            "mensaje_sugerido": {"type": "string"},
            "acciones_siguientes": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "riesgos_o_barreras": {"type": "array", "items": {"type": "string"}},
            "racional": {"type": "string"}
        },
        "required": [
            "canal_recomendado",
            "monto_estimado_recuperacion",
            "probabilidad_recuperacion",
            "primer_abono_sugerido",
            "ventana_horaria",
            "mensaje_sugerido",
            "acciones_siguientes",
            "riesgos_o_barreras",  # ← AGREGAR ESTA
            "racional"
        ],
        "additionalProperties": False
    },
    "strict": True
}

@bp.get("/evaluations/<int:evaluation_id>/strategy_llm")
def strategy_llm(evaluation_id: int):
    with SessionLocal() as db:
        e = db.get(Evaluation, evaluation_id)
        if not e:
            return jsonify({"detail": "Evaluación no encontrada"}), 404

        # solo generar estrategia si es “estancado”
        eligible, reason, stats = _stalled_stats(db, evaluation_id, days_min=30, lookback_days=30, min_attempts=3)
        if not eligible:
            return jsonify({"detail": {"reason": reason, "stats": stats}}), 409

        canal_pref = _canal_preferido_por_logs(db, e.id)

        # reglas fijas de franja por canal
        FRANJA_VOICE = "09:00–12:00 y 16:00–19:30 (hora local)"
        FRANJA_MSG   = "10:30–13:00 y 17:30–20:30 (hora local)"

        def _franja_por_canal(canal: str) -> str:
            return FRANJA_MSG if canal in ("whatsapp", "sms", "email") else FRANJA_VOICE

        def _normaliza_canal(c: str) -> str:
            c = (c or "").lower().strip()
            if c in ("whatsapp", "sms", "voice", "email"):
                return c
            # si el modelo no manda un valor válido, usa preferencia histórica o whatsapp
            return (canal_pref or "whatsapp")

        def _normaliza_ventana(canal: str, _ventana: str) -> str:
            # independientemente de lo que diga el LLM, imponemos nuestra franja válida
            return _franja_por_canal(canal)

        # prompt más estricto (franjas y rango de recuperación)
        system_msg = (
            "Actúa como un experto negociador para recuperación de deudas en México. "
            "Objetivo: maximizar recuperación sin prácticas agresivas ni ilegales. "
            "No uses amenazas. Respeta privacidad y horarios razonables. "
            "Responde SOLO en español y SOLO con el JSON del esquema."
        )
        user_msg = (
            f"Datos del caso:\n"
            f"- Canal con más respuesta (histórico): {canal_pref}\n"
            f"- Monto de la deuda: {float(e.monto or 0):.2f}\n"
            f"- Días de atraso: {int(e.dias_atraso or 0)}\n"
            f"- Score crediticio: {int(e.score or 0)}\n\n"
            f"Requisitos estrictos para la salida:\n"
            f"1) canal_recomendado ∈ {{'whatsapp','sms','voice','email'}}.\n"
            f"2) monto_estimado_recuperacion en el rango 0.25–0.55 del saldo; "
            f"   si 30–45 DPD y score<70, tope 0.45.\n"
            f"3) ventana_horaria obligatoria: si canal es 'voice' usa '{FRANJA_VOICE}'; "
            f"   si canal es 'whatsapp' o 'sms' o 'email' usa '{FRANJA_MSG}'.\n"
            f"4) mensaje_sugerido: breve, respetuoso, con CTA claro "
            f"   (confirmar abono hoy o enviar comprobante/SPEI programado).\n"
            f"5) acciones_siguientes: pasos operativos concretos (contacto, confirmación, evidencia, escalamiento si incumple).\n"
            f"6) Responde SOLO con JSON válido del esquema proporcionado."
        )

        try:
            client = _get_openai_client()
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            data, source = _llm_negotiation_strategy(client, model, system_msg, user_msg, NEGOTIATION_SCHEMA)

            # --- post-procesado: normalizar canal/ventana y acotar monto + agregar prob/primer abono ---
            canal_out = _normaliza_canal(data.get("canal_recomendado"))
            data["canal_recomendado"] = canal_out
            data["ventana_horaria"]   = _normaliza_ventana(canal_out, data.get("ventana_horaria", ""))

            saldo = float(e.monto or 0)
            dpd   = int(e.dias_atraso or 0)
            score = int(e.score or 0)

            # clamp del monto por DPD/score
            low_ratio, high_ratio = 0.25, 0.55
            if 30 <= dpd <= 45 and score < 70:
                high_ratio = 0.45

            rec = float(data.get("monto_estimado_recuperacion") or 0.0)
            if saldo > 0:
                if rec <= 0:
                    rec = ((low_ratio + high_ratio) / 2.0) * saldo  # punto medio del rango
                rec = max(low_ratio * saldo, min(rec, high_ratio * saldo))
                data["monto_estimado_recuperacion"] = round(rec, 2)

            # probabilidad de recuperación (heurística)
            if score >= 80: base = 0.60
            elif score >= 70: base = 0.50
            elif score >= 60: base = 0.40
            else: base = 0.30

            if dpd >= 60: pen = 0.20
            elif dpd >= 45: pen = 0.12
            elif dpd >= 30: pen = 0.08
            else: pen = 0.0

            prob = max(0.05, min(0.95, base - pen))
            # si el modelo lo mandó fuera de 0..1, corrígelo; si no lo mandó, añádelo
            model_prob = data.get("probabilidad_recuperacion")
            if isinstance(model_prob, (int, float)):
                data["probabilidad_recuperacion"] = round(max(0.0, min(1.0, float(model_prob))), 2)
            else:
                data["probabilidad_recuperacion"] = round(prob, 2)

            # primer abono sugerido (10–20% del saldo, cap al monto estimado)
            target_ratio = 0.15
            target = max(0.10 * saldo, min(0.20 * saldo, target_ratio * saldo))
            primer_abono = round(min(data["monto_estimado_recuperacion"], target), 2) if saldo > 0 else 0.0
            data["primer_abono_sugerido"] = primer_abono

            # CTA mínimo si faltó
            msg = (data.get("mensaje_sugerido") or "").strip()
            if msg and ("¿" not in msg and "confirm" not in msg.lower()):
                msg += " ¿Puedes confirmar un abono inicial hoy y programar el resto en parcialidades?"
            data["mensaje_sugerido"] = msg

            return jsonify({"ok": True, "evaluation_id": e.id, "source": source, "strategy": data}), 200

        except Exception as ex:
            import traceback
            print("[LLM][ERROR]", repr(ex)); traceback.print_exc()

            # Fallback heurístico con mismas reglas
            saldo = float(e.monto or 0)
            dpd   = int(e.dias_atraso or 0)
            score = int(e.score or 0)

            ventana = _franja_por_canal(canal_pref or "whatsapp")

            low_ratio, high_ratio = 0.25, 0.55
            if 30 <= dpd <= 45 and score < 70:
                high_ratio = 0.45

            if score >= 80: base = 0.60
            elif score >= 70: base = 0.50
            elif score >= 60: base = 0.40
            else: base = 0.30

            if dpd >= 60: pen = 0.20
            elif dpd >= 45: pen = 0.12
            elif dpd >= 30: pen = 0.08
            else: pen = 0.0

            prob = max(0.05, min(0.95, base - pen))
            rec  = max(low_ratio * saldo, min((base - pen) * saldo, high_ratio * saldo))
            monto_est = round(rec, 2)
            target_ratio = 0.15
            target = max(0.10 * saldo, min(0.20 * saldo, target_ratio * saldo))
            primer_abono = round(min(monto_est, target), 2) if saldo > 0 else 0.0

            msg = (
                f"Hola. Soy Sofía de cobranza. {dpd} días de atraso y saldo ${saldo:,.2f}. "
                f"Para ayudarte a regularizar, hoy podemos registrar un abono inicial y programar el resto en 2–4 parcialidades. "
                f"¿Puedes confirmarlo hoy? Puedo enviarte las ligas de pago ahora mismo."
            )

            return jsonify({
                "ok": True, "evaluation_id": e.id, "source": "heuristic",
                "strategy": {
                    "canal_recomendado": (canal_pref or "whatsapp"),
                    "monto_estimado_recuperacion": monto_est,
                    "probabilidad_recuperacion": round(prob, 2),
                    "primer_abono_sugerido": primer_abono,
                    "ventana_horaria": ventana,
                    "mensaje_sugerido": msg,
                    "acciones_siguientes": [
                        f"Contactar por {(canal_pref or 'whatsapp')} en {ventana}.",
                        "Pedir abono inicial hoy (10–20%).",
                        "Ofrecer plan en 2–4 parcialidades con fechas exactas.",
                        "Registrar compromiso y evidencia (comprobante o SPEI programado).",
                        "Si incumple: escalar; considerar reestructura o liquidación condicionada según política."
                    ],
                    "riesgos_o_barreras": ["Promesas incumplidas", "Liquidez limitada"],
                    "racional": "Fallback heurístico por error de API."
                }
            }), 200


@bp.get("/_llm_ping")
def llm_ping():
    try:
        client = _get_openai_client()
        result = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[{"role": "user", "content": "Responde SOLO con: OK"}],
            temperature=0.0,
        )
        return {"ok": True, "text": result.output_text}
    except Exception as ex:
        import traceback
        print("[LLM][ERROR]", repr(ex)); traceback.print_exc()
        return {"ok": False, "error": str(ex)}, 500
