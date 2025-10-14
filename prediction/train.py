import os
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from .features import build_pipeline, NUM_COLS, CAT_COLS

MODEL_DIR = Path(__file__).parent / "model_store"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "model_v1.joblib"

def _synthetic_data(n=3000, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    paises = np.array(["MX", "AR", "CO"])
    sectores = np.array(["retail", "saas", "manufactura", "fintech", "otros"])

    score = rng.integers(0, 101, size=n)
    dias_atraso = rng.integers(0, 91, size=n)  # 0-90 días
    monto = np.round(rng.lognormal(mean=7.5, sigma=0.6, size=n), 2)  # ~ montos realistas
    recordatorios = rng.integers(0, 6, size=n)
    pagos_previos = rng.integers(0, 12, size=n)
    moras_previas = rng.integers(0, 6, size=n)
    pais = rng.choice(paises, size=n, replace=True)
    sector = rng.choice(sectores, size=n, replace=True)

    # Generamos prob de pago en 15 días como función "realista"
    # Alta con score alto, baja con muchos días de atraso, etc.
    z = (
        0.05 * (score - 50)  # score ayuda
        - 0.06 * (dias_atraso)  # más atraso, peor
        - 0.15 * (moras_previas)  # moras previas, peor
        + 0.03 * (pagos_previos)  # historial positivo ayuda
        - 0.000004 * (monto)      # montos muy altos dificultan
        + 0.04 * (recordatorios)  # más recordatorios ayudan un poco
    )
    # tweaks por país/sector
    z += np.where(pais == "MX", 0.03, 0.0)
    z += np.where(sector == "saas", 0.05, 0.0)

    # Sigmoide → probabilidad
    prob = 1 / (1 + np.exp(-z))
    y = (rng.random(n) < prob).astype(int)

    df = pd.DataFrame({
        "score": score,
        "dias_atraso": dias_atraso,
        "monto": monto,
        "recordatorios_enviados": recordatorios,
        "pagos_previos": pagos_previos,
        "moras_previas": moras_previas,
        "pais": pais,
        "sector": sector,
        "pago_en_15d": y,
    })
    return df

def train_and_save():
    df = _synthetic_data()
    X = df[NUM_COLS + CAT_COLS]
    y = df["pago_en_15d"]

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=123, stratify=y)

    clf = LogisticRegression(max_iter=200)
    pipe = build_pipeline(clf)
    pipe.fit(Xtr, ytr)

    # Métrica primaria (AUC)
    yhat = pipe.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, yhat)
    print(f"[model_v1] AUC={auc:.3f}")

    joblib.dump({"pipeline": pipe, "version": "v1", "auc": float(auc)}, MODEL_PATH)
    print(f"Modelo guardado en: {MODEL_PATH.resolve()}")

if __name__ == "__main__":
    train_and_save()
