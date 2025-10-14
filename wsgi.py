# wsgi.py
from flask import Flask
from dotenv import load_dotenv
load_dotenv()  # OPENAI_API_KEY, DB_URL, etc.

from app.stalled_flask import bp as stalled_bp

def create_app():
    app = Flask(__name__)
    # registra blueprints
    app.register_blueprint(stalled_bp)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    return app

# WSGI entrypoint
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
