# FastAPI + Twilio Media Streams + OpenAI Realtime (Cobranza)

## Pasos
1) pip install -r requirements.txt
2) Copia .env.example a .env y coloca tu OPENAI_API_KEY.
3) uvicorn main:app --host 0.0.0.0 --port 5050
4) ngrok http 5050
5) En Twilio Console -> Phone Numbers -> Voice -> A Call Comes In (Webhook): POST a
   https://TU-NGROK/incoming-call?nombre=Luis&dias=15&monto=1000

La llamada se conectara por <Connect><Stream> al WS /media-stream. Audio en mu-law 8k.

## Tips
- Cambia la voz del modelo en voice: "alloy" si tu cuenta lo permite.
- Si usas HTTPS en produccion, asegúrate de que scheme sea wss://.
