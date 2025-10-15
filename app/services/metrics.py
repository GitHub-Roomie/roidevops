# app/services/metrics.py
from datetime import timedelta
from sqlalchemy import func
from app.services.db import ActionLog

def build_kpis(db, start_dt, end_dt):
    q = db.query(ActionLog).filter(
        ActionLog.created_at >= start_dt,
        ActionLog.created_at < end_dt
    )
    total = q.count()
    failed = q.filter(ActionLog.status == "failed").count()
    ok = q.filter(ActionLog.status.in_(("sent", "completed", "queued"))).count()
    success_rate = round((ok / total * 100) if total else 0.0, 2)

    return {
        "total_actions": total,
        "ok": ok,
        "failed": failed,
        "success_rate": success_rate,
    }

def build_timeseries(db, start_dt, end_dt):
    # Agrupa por día (func.date funciona en SQLite y Postgres)
    rows = (
        db.query(func.date(ActionLog.created_at), func.count(1))
          .filter(ActionLog.created_at >= start_dt, ActionLog.created_at < end_dt)
          .group_by(func.date(ActionLog.created_at))
          .order_by(func.date(ActionLog.created_at))
          .all()
    )
    # Normaliza a dict "YYYY-MM-DD" -> count
    counts = {}
    for d, c in rows:
        key = d if isinstance(d, str) else d.strftime("%Y-%m-%d")
        counts[key] = int(c)

    # Rellena días faltantes
    out = []
    cur = start_dt.date()
    while cur <= end_dt.date():
        k = cur.isoformat()
        out.append({"date": k, "count": counts.get(k, 0)})
        cur += timedelta(days=1)
    return out
