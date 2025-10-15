import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline

# Columnas (numéricas y categóricas) — fáciles de extender
NUM_COLS = ["score", "dias_atraso", "monto", "recordatorios_enviados", "pagos_previos", "moras_previas"]
CAT_COLS = ["sector", "pais"]

def build_pipeline(estimator):
    """
    Crea un pipeline con preprocesamiento (escalado numérico + one-hot categórico)
    y el estimador que definas (logístico baseline).
    """
    numeric_transformer = StandardScaler(with_mean=True, with_std=True)
    categorical_transformer = OneHotEncoder(handle_unknown="ignore")

    pre = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUM_COLS),
            ("cat", categorical_transformer, CAT_COLS),
        ],
        remainder="drop",
    )

    pipe = Pipeline(steps=[
        ("pre", pre),
        ("clf", estimator)
    ])
    return pipe

def input_to_df(x: dict) -> pd.DataFrame:
    """
    Convierte el input Pydantic a DataFrame con columnas esperadas.
    Aplica defaults seguros (0 para numéricos, 'MX' para país, etc.).
    """
    row = {
        "score": x.get("score", 50),
        "dias_atraso": x.get("dias_atraso", 0),
        "monto": float(x.get("monto") or 0.0),
        "recordatorios_enviados": int(x.get("recordatorios_enviados") or 0),
        "pagos_previos": int(x.get("pagos_previos") or 0),
        "moras_previas": int(x.get("moras_previas") or 0),
        "sector": x.get("sector") or "desconocido",
        "pais": x.get("pais") or "MX",
    }
    return pd.DataFrame([row])
