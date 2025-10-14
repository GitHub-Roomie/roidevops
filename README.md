# 🤖 Motor de Cobranza Inteligente con IA

Sistema automatizado de cobranza que utiliza Inteligencia Artificial para gestionar comunicaciones multicanal (llamadas, WhatsApp, SMS, email) con clientes morosos. Integra OpenAI GPT-4, Twilio, FastAPI y un dashboard de gestión en tiempo real.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)
![Twilio](https://img.shields.io/badge/Twilio-Voice%20%26%20SMS-red.svg)

---

## 🎯 Características Principales

### ✨ Agente de Voz Inteligente
- **Conversaciones naturales** con clientes usando GPT-4
- **Detección automática de contestadoras** (AMD - Answering Machine Detection)
- **Escalado dinámico de intensidad** según resistencia del cliente
- **3 niveles de firmeza** adaptados a días de atraso
- **Voz Neural de Amazon Polly** (Mia - México)

### 📊 Dashboard de Gestión
- **Vista de casos estancados** con filtros avanzados
- **Métricas en tiempo real** (llamadas, respuestas, efectividad)
- **Historial completo** de interacciones multicanal
- **Sistema de evaluación** con scoring crediticio

### 🔗 Integración Multicanal
- ✅ **Llamadas de voz** (Twilio Voice + OpenAI)
- ✅ **WhatsApp Business** (vía n8n)
- ✅ **SMS** (Twilio Messaging)
- ✅ **Email** (automatizado)

### 🧠 Inteligencia de Decisión
- **Motor de reglas** para selección de canal óptimo
- **Predicción de pago** con ML
- **Estrategias dinámicas** según perfil del cliente
- **Logs detallados** para análisis y auditoría

---

## 🏗️ Arquitectura

┌─────────────────┐
│  Frontend       │
│  (Lovable)      │  ← Dashboard React
└────────┬────────┘
│
▼
┌─────────────────┐
│  FastAPI        │
│  Backend        │  ← Motor principal
└────────┬────────┘
│
┌────┼────────────────┐
│    │                │
▼    ▼                ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ Twilio │  │  OpenAI  │  │   n8n    │
│ Voice  │  │  GPT-4   │  │ Workflows│
└────────┘  └──────────┘  └──────────┘
│            │              │
└────────────┼──────────────┘
▼
┌──────────────┐
│  PostgreSQL  │  ← Base de datos
│  / SQLite    │
└──────────────┘

---

## 📋 Requisitos Previos

- **Python 3.9+**
- **Cuenta de OpenAI** con API Key
- **Cuenta de Twilio** (con número de teléfono activo)
- **ngrok** (para desarrollo local) o servidor con HTTPS
- **(Opcional) n8n** para canales digitales

---

## 🚀 Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/motor-cobranza-ia.git
cd motor-cobranza-ia

2. Crear entorno virtual
bashpython -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

3. Instalar dependencias
bashpip install -r requirements.txt

4. Configurar variables de entorno
Copia .env.example a .env y configura:
# ========== OpenAI ==========
OPENAI_API_KEY=sk-proj-...
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.5

# ========== Twilio ==========
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxx
TWILIO_FROM_NUMBER=+12025551234
TWILIO_AMD_TIMEOUT=8

# ========== Servidor ==========
PORT=5050
PUBLIC_BASE_URL=https://tu-dominio.ngrok-free.app

# ========== Base de Datos ==========
DB_URL=sqlite:///cobranza.db
# O PostgreSQL: postgresql://user:pass@localhost/cobranza

# ========== Voz (TTS) ==========
TTS_VOICE=Polly.Mia-Neural
TTS_LANG=es-MX

# ========== n8n (Opcional) ==========
N8N_WEBHOOK_URL=https://tu-n8n.com/webhook/cobranza
N8N_INGEST_URL=https://tu-n8n.com/webhook/ingest

5. Iniciar el servidor
bash# Opción 1: Desarrollo
uvicorn main:app --host 0.0.0.0 --port 5050 --reload

# Opción 2: Producción
python main.py

6. Exponer con ngrok (desarrollo)
bashngrok http 5050


 Configuración de Twilio
1. Permisos Geográficos

Ve a: https://console.twilio.com/us1/develop/voice/settings/geo-permissions
Habilita México (y otros países según necesites)

2. Configurar Webhook de Voz

Ve a: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
Selecciona tu número
En "A call comes in":

Método: GET o POST
URL: https://tu-ngrok-url/voice


Guarda

3. Configurar Status Callbacks
En Advanced Configuration:

Status Callback URL: https://tu-ngrok-url/twilio/status
Método: POST

Uso
Evaluar un cliente (desde el frontend)
javascriptPOST /api/execute_all
{
  "nombre": "Luis Alfonso",
  "telefono": "+522721234567",
  "email": "cliente@ejemplo.com",
  "score": 65,
  "dias_atraso": 30,
  "monto": 15000.00
}
Respuesta:
json{
  "ok": true,
  "decision": {
    "nivel": 3,
    "canal_sugerido": "call",
    "mensaje": "Luis Alfonso, saldo $15,000 con 30 días...",
    "min_parcial": "1500.00"
  },
  "call_sid": "CAxxxxxxxxxxxx",
  "n8n": {...}
}
Principales Endpoints
EndpointMétodoDescripción/api/execute_allPOSTEjecuta estrategia completa de cobranza/api/evaluationsGETLista evaluaciones recientes/api/historyGETHistorial de acciones (llamadas, SMS, etc.)/api/metricsGETKPIs y métricas (?days=30)/voiceGET/POSTWebhook de inicio de llamada (Twilio)/process_speechPOSTProcesa respuestas del cliente/twilio/statusPOSTCallback de estado de llamadas/twilio/amd_statusPOSTCallback de detección de máquinas

📁 Estructura del Proyecto
motor-cobranza-ia/
├── main.py                 # Aplicación principal FastAPI
├── decision.py             # Motor de reglas de decisión
├── erp_client.py          # Cliente para integración ERP
├── requirements.txt       # Dependencias Python
├── .env                   # Variables de entorno (no subir a git)
├── .env.example          # Plantilla de configuración
│
├── app/
│   ├── services/
│   │   ├── db.py         # Modelos de base de datos
│   │   └── metrics.py    # Cálculo de KPIs
│   ├── reports.py        # Generación de reportes
│   └── stalled_flask.py  # Endpoint de casos estancados
│
├── prediction/
│   └── serve.py          # Modelo de predicción de pago
│
└── data/
    └── cobranza.db       # Base de datos SQLite (generada)

🧪 Testing
Probar una llamada manualmente
bashcurl -X POST "https://tu-ngrok-url/api/execute_all" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Juan Pérez",
    "telefono": "+522721234567",
    "score": 70,
    "dias_atraso": 20,
    "monto": 10000
  }'
Verificar estado de llamadas
bash# Reconciliar llamadas de las últimas 2 horas
curl -X POST "http://localhost:5050/twilio/reconcile?minutes=120"

🛠️ Tecnologías Utilizadas
Backend

FastAPI - Framework web moderno y rápido
Flask - Endpoints de reportes y legacy
SQLAlchemy - ORM para base de datos
LangChain - Integración con LLMs

IA / ML

OpenAI GPT-4 - Generación de conversaciones
scikit-learn - Predicción de pagos

Comunicaciones

Twilio Voice - Llamadas telefónicas
Twilio Messaging - SMS
Amazon Polly - Text-to-Speech Neural

Frontend

React (Lovable) - Dashboard interactivo
Tailwind CSS - Estilos
shadcn/ui - Componentes UI


🐛 Troubleshooting
Error: "Account not authorized to call +52..."
Solución: Habilita permisos geo en Twilio Console → Voice → Geo Permissions
Error: "The model gpt-4-mini does not exist"
Solución: Cambia en .env a LLM_MODEL=gpt-4o-mini (con la letra "o")
Las llamadas no inician
Verificar:

✅ ngrok está corriendo
✅ PUBLIC_BASE_URL en .env apunta a tu URL de ngrok
✅ Twilio webhook configurado correctamente
✅ Tienes crédito en OpenAI

Bot no habla / voz robótica
Solución: Usa TTS_VOICE=Polly.Mia-Neural con TTS_LANG=es-MX
Error 404 en /api/evaluations
Causa: Flask montado antes de FastAPI endpoints
Solución: Mueve app.mount("/", WSGIMiddleware(flask_app)) al FINAL del archivo

📊 Métricas y KPIs
El sistema registra automáticamente:

✅ Total de llamadas realizadas
✅ Tasa de contestación (humano vs máquina)
✅ Duración promedio de llamadas
✅ Respuestas por canal (call, WhatsApp, SMS, email)
✅ Tasa de conversión (acuerdos de pago)
✅ Efectividad por nivel de cobranza

Accede al dashboard: http://localhost:5173 (frontend)

🔒 Seguridad

✅ Nunca subas el archivo .env a git
✅ Usa variables de entorno para credenciales
✅ En producción, usa HTTPS (no HTTP)
✅ Valida y sanitiza inputs del usuario
✅ Limita rate de APIs externas


🚧 Roadmap

 Integración con ERPNext completa
 Webhook para respuestas de WhatsApp
 Panel de administración de voces
 Reportes avanzados en PDF/Excel
 Multi-idioma (EN, PT)
 Análisis de sentimientos en conversaciones


📝 Licencia
Este proyecto es privado y de uso interno. Todos los derechos reservados.

👥 Contribuidores

Luis Alfonso - Desarrollo principal


📞 Soporte
Para dudas o issues:

Email: tu-email@ejemplo.com
Slack: #motor-cobranza


🙏 Agradecimientos

OpenAI por GPT-4
Twilio por la infraestructura de comunicaciones
Lovable por el frontend


¿Preguntas? Consulta la Wiki o abre un Issue.

Hecho con ❤️ para mejorar la gestión de cobranza

---

## 📝 **También crea un `.env.example`:**
```env
# ========== OpenAI ==========
OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.5

# ========== Twilio ==========
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+12025551234
TWILIO_AMD_TIMEOUT=8

# ========== Servidor ==========
PORT=5050
BACKEND_BASE=http://127.0.0.1:5050
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.app

# ========== Base de Datos ==========
DB_URL=sqlite:///cobranza.db

# ========== Voz (TTS) ==========
TTS_VOICE=Polly.Mia-Neural
TTS_LANG=es-MX

# ========== n8n (Opcional) ==========
N8N_WEBHOOK_URL=
N8N_INGEST_URL=

# ========== Frontend (Lovable) ==========
VITE_API_BASE_URL=http://localhost:5050
