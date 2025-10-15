# app/services/db.py
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text, Index, Boolean
)
from sqlalchemy.orm import sessionmaker, declarative_base

# === Conexión/ORM ===
DB_URL = os.getenv("DB_URL", "sqlite:///cobranza.db")
engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# === Modelos ===
class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    nombre = Column(String(120))
    score = Column(Integer)
    dias_atraso = Column(Integer)
    monto = Column(Float)
    canal_sugerido = Column(String(30))
    mensaje = Column(Text)

class ActionLog(Base):
    __tablename__ = "action_logs"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    canal = Column(String(30))        # call | sms | whatsapp | email | none
    to = Column(String(80))
    status = Column(String(30))       # queued | sent | failed | completed | skipped
    provider_sid = Column(String(80)) # CA..., SM..., WA..., SG...
    error = Column(Text)
    payload = Column(Text)            # JSON con lo enviado
    related_name = Column(String(120))
    # métricas de voz
    answered = Column(Integer, default=0)   # 0/1
    end_status = Column(String(30))         # completed|no-answer|busy|failed|canceled
    duration_sec = Column(Integer, default=0)
    answered_by = Column(String(30))        # human|machine_*|unknown

class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=False)

    # frecuencia
    frequency     = Column(String(16), default="daily")  # daily|weekly|monthly
    days_of_week  = Column(String(64), nullable=True)    # CSV "0,2,4" (lunes=0)
    day_of_month  = Column(Integer, nullable=True)       # 1..28

    # hora/tz
    time_of_day = Column(String(5), default="09:00")     # "HH:MM"
    timezone   = Column(String(64), default="America/Mexico_City")

    # opciones de reporte
    period_days   = Column(Integer, default=30)          # 7/30/90
    include_draft = Column(Boolean, default=True)
    categories    = Column(String(64), default="verde,amarillo,naranja,rojo")  # CSV
    min_dpd       = Column(Integer, default=0)
    formats       = Column(String(32), default="pdf,xlsx")  # CSV
    attach_files  = Column(Boolean, default=False)

    # destinatarios
    groups = Column(String(128), default="Direccion,Operaciones,Cobranza,Finanzas")
    emails = Column(Text, default="")  # CSV

    # mensajes
    subject_tpl = Column(Text, default="Reporte ejecutivo CxC ({{rango}} días)")
    body_tpl    = Column(Text, default="Adjunto enlaces al reporte de {{rango}} días. Generado: {{fecha}}. Total: {{total}}")

    # auditoría
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)

# === Crear tablas/índices ===
Base.metadata.create_all(bind=engine)

ix_eval_created = Index('ix_evaluations_created_at', Evaluation.created_at)
ix_eval_score   = Index('ix_evaluations_score',      Evaluation.score)
ix_al_created   = Index('ix_action_logs_created_at', ActionLog.created_at)
ix_al_canal     = Index('ix_action_logs_canal',      ActionLog.canal)
ix_al_status    = Index('ix_action_logs_status',     ActionLog.status)
ix_al_to        = Index('ix_action_logs_to',         ActionLog.to)

for idx in [ix_eval_created, ix_eval_score, ix_al_created, ix_al_canal, ix_al_status, ix_al_to]:
    try:
        idx.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"[DB][WARN] No se pudo crear índice {idx.name}: {e}")
