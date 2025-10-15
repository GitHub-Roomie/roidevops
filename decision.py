# decision.py

def _to_850_scale(raw_score):
    try:
        s = float(raw_score)
    except Exception:
        s = 0.0
    # permitir 0..1 como porcentaje
    if 0.0 <= s <= 1.0:
        s *= 100.0
    if s <= 100.0:
        s = max(0.0, min(100.0, s))
        return 300.0 + s * 5.5
    return s  # ya viene en ~300..850


def _classify_level(dpd: int, score: float) -> int:
    """
    Nivel base por DPD:
      1 = 1–5 días
      2 = 6–15 días
      3 = 16+ días
    Ajuste por score (escala 850):
      - score < 650 => +1 (máx 3)
      - score >= 700 => -1 (mín 1)
    """
    s850 = _to_850_scale(score)
    if dpd >= 16:
        level = 3
    elif dpd >= 6:
        level = 2
    elif dpd >= 1:
        level = 1
    else:
        level = 1  # recordatorio

    if s850 < 650:
        level = min(3, level + 1)
    elif s850 >= 700:
        level = max(1, level - 1)
    return level


def _format_mxn(monto: float) -> str:
    # Formato simple estilo es-MX sin dependencias
    s = f"{float(monto):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def compute_min_parcial(monto: float) -> float:
    # 10% o mínimo $100
    try:
        m = float(monto)
    except Exception:
        m = 0.0
    return round(max(m * 0.10, 100.0), 2)


def _templates(nombre: str, dpd: int, monto: float, level: int, min_parcial: float):
    monto_txt = f"${_format_mxn(monto)}"
    min_txt   = f"${_format_mxn(min_parcial)}"

    base = {
        1: {  # Bajo (invitación cordial)
            "sms":      f"{nombre}, tienes {dpd} día(s) de atraso por {monto_txt}. ¿Puedes regularizar hoy? Te apoyamos por este medio.",
            "whatsapp": f"Hola {nombre}, recordatorio amable: saldo {monto_txt}, {dpd} día(s) de atraso. ¿Pagas hoy o agendamos fecha?",
            "email_subject": f"Recordatorio de pago — {monto_txt}",
            "email_body": (
                f"Hola {nombre},\n\n"
                f"Detectamos {dpd} día(s) de atraso por {monto_txt}. "
                f"Para evitar contratiempos, te invitamos a ponerte al corriente hoy. "
                f"Si requieres apoyo, responde este correo.\n\n"
                f"Saludos."
            ),
            "call_opening": (
                f"{nombre}, soy Sofía. Tu saldo es {monto_txt} con {dpd} día(s) de atraso. "
                f"¿Eres {nombre}? (Queremos ayudarte a regularizar hoy)."
            ),
        },
        2: {  # Medio (firme, 72h, intereses/suspensión)
            "sms":      f"{nombre}, {dpd} días de atraso por {monto_txt}. Hay intereses activos. Define pago hoy o fecha ≤72h.",
            "whatsapp": f"{nombre}, saldo {monto_txt}, {dpd} días de atraso. Intereses y riesgo de suspensión. ¿Pagas hoy o fecha ≤72h?",
            "email_subject": f"Regulariza tu saldo en 72 horas — {monto_txt}",
            "email_body": (
                f"Hola {nombre},\n\n"
                f"Tu cuenta presenta {dpd} días de atraso por {monto_txt}. "
                f"Se generan intereses y podrías tener suspensión de beneficios/servicios. "
                f"Define pago hoy o una fecha dentro de 72 horas.\n\n"
                f"Quedamos atentos."
            ),
            "call_opening": (
                f"{nombre}, soy Sofía. Saldo {monto_txt}, {dpd} días de atraso. "
                f"Intereses activos y posible suspensión. ¿Pagas hoy o defines fecha ≤72h? ¿Cuál confirmas?"
            ),
        },
        3: {  # Alto (muy firme, posible jurídico, abono mínimo hoy)
            "sms":      f"{nombre}, {dpd} días de atraso por {monto_txt}. Exigimos regularización hoy. Abono mínimo {min_txt} o acuerdo inmediato.",
            "whatsapp": f"{nombre}, saldo {monto_txt} con {dpd} días de atraso. Exigimos abono hoy de {min_txt} o fecha inamovible. Sin acuerdo, escalaremos conforme contrato.",
            "email_subject": f"Acción requerida hoy — {monto_txt}",
            "email_body": (
                f"Hola {nombre},\n\n"
                f"Tu saldo ({monto_txt}) suma {dpd} días de atraso. "
                f"Se requiere regularización inmediata. Exigimos un abono hoy de {min_txt} o acuerdo firme. "
                f"De no recibir confirmación, el caso podría escalarse conforme contrato y normatividad.\n"
            ),
            "call_opening": (
                f"{nombre}, soy Sofía. Saldo {monto_txt}, {dpd} días de atraso. "
                f"Exigimos regularización hoy. Mínimo {min_txt} ahora o fecha inamovible. ¿Cómo procedemos?"
            ),
        },
    }
    return base.get(level, base[1])


def compute_decision(nombre: str, dpd: int, score: float, monto: float):
    # Normaliza
    try:
        dpd = int(dpd or 0)
    except Exception:
        dpd = 0
    try:
        monto = float(monto or 0.0)
    except Exception:
        monto = 0.0

    s_850 = _to_850_scale(score)
    nivel = _classify_level(dpd, score)
    min_parcial = compute_min_parcial(monto)
    tpls = _templates(nombre, dpd, monto, nivel, min_parcial)

    canal_sugerido = "call"  # compatibilidad con tu backend
    mensaje = (
        f"Sugerido principal: {canal_sugerido}. "
        f"Nivel={nivel} (1 bajo, 2 medio, 3 alto). "
        f"Score(entrada)={score} → Score(850)={int(s_850)}; "
        f"DPD={dpd}; Monto={monto:.2f}; MinParcial={min_parcial:.2f}"
    )

    return {
        "canal_sugerido": canal_sugerido,
        "channels": ["call", "whatsapp", "sms", "email"],
        "nivel": nivel,
        "min_parcial": min_parcial,
        "templates": tpls,
        "score_entrada": score,
        "score_850": int(s_850),
        "dpd": dpd,
        "monto": monto,
        "mensaje": mensaje,
    }
