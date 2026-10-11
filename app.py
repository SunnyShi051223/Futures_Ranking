"""Futures Ranking application entry point.

Run with: python app.py
"""
from flask import Flask, send_from_directory

from config import settings
from backend.routes import register_routes


def create_app() -> Flask:
    app = Flask(__name__, static_folder="front", static_url_path="/front")
    app.config["JSON_AS_ASCII"] = False
    app.config["SECRET_KEY"] = settings.jwt_secret_key
    register_routes(app)

    @app.get("/")
    def index():
        return send_from_directory(settings.front_dir, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
