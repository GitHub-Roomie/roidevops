# seed_realistic.py
"""
Script para poblar la base de datos con datos realistas para la demo.
Crea casos ESTANCADOS y NO ESTANCADOS basados en clientes reales de ERPNext.
"""

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from app.services.db import SessionLocal, Evaluation, ActionLog
import random

def seed_realistic():
    now = datetime.utcnow()
    
    # Definir casos realistas
    casos = [
        # ========== CASOS ESTANCADOS (aparecerán en la lista) ==========
        {
            "nombre": "Palmer Productions Ltd.",
            "score": 65,
            "dias_atraso": 35,
            "monto": 18700.00,
            "telefono": "+522721301401",
            "email": "contacto@palmer.com",
            "intentos": [
                {"dias_atras": 25, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 22, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 18, "canal": "call", "status": "busy", "answered": 0},
                {"dias_atras": 15, "canal": "sms", "status": "sent", "answered": 0},
                {"dias_atras": 10, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 5, "canal": "email", "status": "sent", "answered": 0},
            ],
            "es_estancado": True
        },
        {
            "nombre": "West View Software Ltd.",
            "score": 45,
            "dias_atraso": 62,
            "monto": 229900.00,
            "telefono": "+522721301402",
            "email": "admin@westview.com",
            "intentos": [
                {"dias_atras": 28, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 26, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 24, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 20, "canal": "email", "status": "sent", "answered": 0},
                {"dias_atras": 15, "canal": "call", "status": "failed", "answered": 0},
                {"dias_atras": 10, "canal": "sms", "status": "sent", "answered": 0},
                {"dias_atras": 5, "canal": "call", "status": "no-answer", "answered": 0},
            ],
            "es_estancado": True
        },
        {
            "nombre": "Grant Plastics Ltd.",
            "score": 58,
            "dias_atraso": 48,
            "monto": 5000.00,
            "telefono": "+522721301403",
            "email": "billing@grantplastics.com",
            "intentos": [
                {"dias_atras": 27, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 23, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 19, "canal": "call", "status": "busy", "answered": 0},
                {"dias_atras": 12, "canal": "sms", "status": "sent", "answered": 0},
            ],
            "es_estancado": True
        },
        {
            "nombre": "Construcciones del Norte SA",
            "score": 52,
            "dias_atraso": 41,
            "monto": 45000.00,
            "telefono": "+522721301404",
            "email": "pagos@construcciones.mx",
            "intentos": [
                {"dias_atras": 29, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 25, "canal": "email", "status": "sent", "answered": 0},
                {"dias_atras": 20, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 15, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 8, "canal": "sms", "status": "sent", "answered": 0},
            ],
            "es_estancado": True
        },
        {
            "nombre": "Distribuidora López y Asociados",
            "score": 38,
            "dias_atraso": 55,
            "monto": 12800.00,
            "telefono": "+522721301405",
            "email": "cobranza@distlopez.com",
            "intentos": [
                {"dias_atras": 28, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 24, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 21, "canal": "call", "status": "failed", "answered": 0},
                {"dias_atras": 17, "canal": "email", "status": "sent", "answered": 0},
                {"dias_atras": 10, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 5, "canal": "sms", "status": "sent", "answered": 0},
            ],
            "es_estancado": True
        },
        {
            "nombre": "Servicios Integrales MX",
            "score": 42,
            "dias_atraso": 67,
            "monto": 38500.00,
            "telefono": "+522721301406",
            "email": "administracion@serviciosmx.com",
            "intentos": [
                {"dias_atras": 29, "canal": "email", "status": "sent", "answered": 0},
                {"dias_atras": 26, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 22, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 18, "canal": "call", "status": "busy", "answered": 0},
                {"dias_atras": 12, "canal": "sms", "status": "sent", "answered": 0},
                {"dias_atras": 7, "canal": "call", "status": "no-answer", "answered": 0},
            ],
            "es_estancado": True
        },
        
        # ========== CASOS NO ESTANCADOS (NO aparecerán) ==========
        {
            "nombre": "Comercializadora Azteca",
            "score": 72,
            "dias_atraso": 38,
            "monto": 8500.00,
            "telefono": "+522721301407",
            "email": "pagos@azteca.mx",
            "intentos": [
                {"dias_atras": 20, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 15, "canal": "whatsapp", "status": "sent", "answered": 0},
                {"dias_atras": 10, "canal": "call", "status": "completed", "answered": 1},  # ← RESPONDIÓ
            ],
            "es_estancado": False
        },
        {
            "nombre": "Importaciones del Pacífico",
            "score": 68,
            "dias_atraso": 33,
            "monto": 15200.00,
            "telefono": "+522721301408",
            "email": "tesoreria@pacifico.com",
            "intentos": [
                {"dias_atras": 18, "canal": "email", "status": "sent", "answered": 0},
                {"dias_atras": 14, "canal": "whatsapp", "status": "replied", "answered": 1},  # ← RESPONDIÓ
                {"dias_atras": 8, "canal": "call", "status": "completed", "answered": 1},     # ← RESPONDIÓ
            ],
            "es_estancado": False
        },
        {
            "nombre": "Grupo Industrial del Bajío",
            "score": 75,
            "dias_atraso": 31,
            "monto": 22000.00,
            "telefono": "+522721301409",
            "email": "cuentas@grupobajio.mx",
            "intentos": [
                {"dias_atras": 25, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 20, "canal": "email", "status": "replied", "answered": 1},    # ← RESPONDIÓ
                {"dias_atras": 12, "canal": "whatsapp", "status": "sent", "answered": 0},
            ],
            "es_estancado": False
        },
        {
            "nombre": "Tecnología Avanzada SA",
            "score": 80,
            "dias_atraso": 35,
            "monto": 9800.00,
            "telefono": "+522721301410",
            "email": "facturacion@tecavanzada.com",
            "intentos": [
                {"dias_atras": 22, "canal": "call", "status": "completed", "answered": 1},   # ← RESPONDIÓ
                {"dias_atras": 15, "canal": "whatsapp", "status": "sent", "answered": 0},
            ],
            "es_estancado": False
        },
        
        # Caso con pocos intentos (< 3) - NO aparecerá aunque no tenga respuestas
        {
            "nombre": "Nuevos Clientes SA",
            "score": 60,
            "dias_atraso": 32,
            "monto": 3500.00,
            "telefono": "+522721301411",
            "email": "info@nuevosclientes.com",
            "intentos": [
                {"dias_atras": 10, "canal": "call", "status": "no-answer", "answered": 0},
                {"dias_atras": 5, "canal": "email", "status": "sent", "answered": 0},
            ],
            "es_estancado": False  # Solo 2 intentos, no cumple el mínimo de 3
        },
    ]
    
    with SessionLocal() as db:
        print("\n🗑️  Limpiando datos anteriores...")
        db.query(ActionLog).delete()
        db.query(Evaluation).delete()
        db.commit()
        
        print("\n📊 Creando casos realistas...")
        
        estancados_creados = 0
        no_estancados_creados = 0
        
        for caso in casos:
            # Crear evaluación
            eva = Evaluation(
                nombre=caso["nombre"],
                score=caso["score"],
                dias_atraso=caso["dias_atraso"],
                monto=caso["monto"],
                canal_sugerido="call" if caso["dias_atraso"] >= 45 else "whatsapp",
                mensaje=f"Cliente con {caso['dias_atraso']} días de atraso, score {caso['score']}"
            )
            db.add(eva)
            db.commit()
            db.refresh(eva)
            
            # Crear action logs
            for intento in caso["intentos"]:
                log = ActionLog(
                    created_at=now - timedelta(days=intento["dias_atras"]),
                    canal=intento["canal"],
                    to=caso["telefono"] if intento["canal"] in ["call", "sms", "whatsapp"] else caso["email"],
                    status=intento["status"],
                    provider_sid=f"DEMO{random.randint(1000,9999)}",
                    related_name=f"eval:{eva.id}",
                    answered=intento["answered"],
                    end_status=intento["status"],
                    duration_sec=random.randint(0, 180) if intento["answered"] == 1 else 0,
                )
                db.add(log)
            
            db.commit()
            
            if caso["es_estancado"]:
                estancados_creados += 1
                print(f"  ✅ ESTANCADO: {caso['nombre'][:30]:30} | {caso['dias_atraso']}d | ${caso['monto']:,.0f} | {len(caso['intentos'])} intentos")
            else:
                no_estancados_creados += 1
                razon = "Tuvo respuesta" if any(i["answered"] == 1 for i in caso["intentos"]) else "Pocos intentos"
                print(f"  ⚪ No estancado: {caso['nombre'][:30]:30} | {caso['dias_atraso']}d | ${caso['monto']:,.0f} | {razon}")
        
        print("\n" + "="*80)
        print(f"✅ SEED COMPLETADO")
        print(f"   Casos ESTANCADOS creados: {estancados_creados}")
        print(f"   Casos NO estancados creados: {no_estancados_creados}")
        print(f"   Total de casos: {len(casos)}")
        print("="*80)
        print("\n📋 PRUEBAS SUGERIDAS:")
        print("   1. Ve a Lovable → Casos Estancados")
        print(f"   2. Deberías ver {estancados_creados} casos en la lista")
        print("   3. Click en 'Ver estrategia' para cualquiera")
        print("   4. Verifica que la IA genera estrategias personalizadas")
        print("\n💡 NOTA: Los casos NO estancados NO aparecerán en la lista porque:")
        print("   - Tuvieron respuestas (answered=1)")
        print("   - O no cumplen el mínimo de 3 intentos")
        print()

if __name__ == "__main__":
    seed_realistic()