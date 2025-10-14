from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class PaymentPredictionInput(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None

    score: int = Field(ge=0, le=100)
    dias_atraso: int = Field(ge=0)
    monto: Optional[float] = None

    # Hooks para escalar en el futuro (puedes mandarlos cuando existan)
    sector: Optional[str] = None        # e.g., "retail", "saas"
    pais: Optional[str] = "MX"          # MX/AR/CO, etc.
    recordatorios_enviados: Optional[int] = 0  # voz/sms/wa/email enviados
    pagos_previos: Optional[int] = 0    # # pagos históricos exitosos
    moras_previas: Optional[int] = 0    # # veces con mora en el pasado

class PaymentPredictionOutput(BaseModel):
    modelo_version: str
    prob_pago_15d: float      # 0..1
    dias_estimados_pago: int  # baseline derivado
    recomendacion: str        # texto breve
