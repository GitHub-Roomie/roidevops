# prediction/serve.py
import joblib
from pathlib import Path
from .schema import PaymentPredictionInput, PaymentPredictionOutput
from .features import input_to_df

MODEL_PATH = Path(__file__).parent / "model_store" / "model_v1.joblib"
MODEL = None

def _load_model():
    global MODEL
    if MODEL is None:
        if not MODEL_PATH.exists():
            raise RuntimeError("Modelo no encontrado. Entrena con prediction/train.py")
        MODEL = joblib.load(MODEL_PATH)
    return MODEL

def model_health():
    try:
        m = _load_model()
        return {"ok": True, "version": m.get("version"), "auc": m.get("auc")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def predict_pago_dict(payload: dict) -> dict:
    """
    Recibe un dict con los campos de PaymentPredictionInput
    y devuelve un dict PaymentPredictionOutput.
    """
    m = _load_model()
    pipe = m["pipeline"]
    version = m["version"]

    x = PaymentPredictionInput(**payload)
    df = input_to_df(x.dict())
    prob = float(pipe.predict_proba(df)[:, 1][0])

    # Heurística simple para días estimados + recomendación
    if prob >= 0.8:
        dias_est = 5
        rec = "Probable pago inmediato: mantén recordatorios suaves."
    elif prob >= 0.6:
        dias_est = 10
        rec = "Buena probabilidad: combina email + WhatsApp."
    elif prob >= 0.4:
        dias_est = 15
        rec = "Riesgo moderado: voz + WhatsApp y seguimiento a 72h."
    else:
        dias_est = 25
        rec = "Baja probabilidad: escalar a voz prioritaria y oferta de plan."

    out = PaymentPredictionOutput(
        modelo_version=version,
        prob_pago_15d=round(prob, 4),
        dias_estimados_pago=dias_est,
        recomendacion=rec
    )
    return out.dict()
