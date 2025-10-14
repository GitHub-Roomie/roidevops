# seed_stalled.py
from dotenv import load_dotenv
load_dotenv()  # asegura que DB_URL/OPENAI_API_KEY se carguen antes de importar la DB

from datetime import datetime, timedelta
from app.services.db import SessionLocal, Evaluation, ActionLog

def seed():
    now = datetime.utcnow()
    with SessionLocal() as db:
        # 1) Caso ESTANCADO (debe salir en /api/invoices/stalled)
        eva = Evaluation(
            nombre="Cliente Prueba Estancado",
            score=65,
            dias_atraso=35,        # >= 30
            monto=120000.0,
        )
        db.add(eva); db.commit(); db.refresh(eva)

        db.add_all([
            # 3-4 intentos SIN respuesta en los últimos 30 días
            ActionLog(created_at=now - timedelta(days=3), canal="call",     status="queued",  to="5551112222", related_name=f"eval:{eva.id}"),
            ActionLog(created_at=now - timedelta(days=2), canal="whatsapp", status="sent",    to="5551112222", related_name=f"eval:{eva.id}"),
            ActionLog(created_at=now - timedelta(days=1), canal="sms",      status="sent",    to="5551112222", related_name=f"eval:{eva.id}"),
            ActionLog(created_at=now - timedelta(days=1), canal="email",    status="sent",    to="cliente@demo.com", related_name=f"eval:{eva.id}"),
        ])
        db.commit()

        # 2) Caso NO estancado (tiene una "respuesta" → no debe salir)
        eva_ok = Evaluation(
            nombre="Cliente Con Respuesta",
            score=72,
            dias_atraso=42,        # >= 30
            monto=50000.0,
        )
        db.add(eva_ok); db.commit(); db.refresh(eva_ok)

        db.add_all([
            ActionLog(created_at=now - timedelta(days=2), canal="call", status="queued",    to="5553334444", related_name=f"eval:{eva_ok.id}"),
            ActionLog(created_at=now - timedelta(days=1), canal="call", status="completed", to="5553334444", related_name=f"eval:{eva_ok.id}"),  # cuenta como respuesta
        ])
        db.commit()

    print("[SEED] Listo.")
    print("  - Estancado      -> evaluation_id =", eva.id)
    print("  - Con respuesta  -> evaluation_id =", eva_ok.id)
    print("Usa estos IDs para probar /api/evaluations/{id}/strategy_llm")

if __name__ == "__main__":
    seed()
