from flask import Flask

from .api import api_bp


def register_routes(app: Flask) -> None:
    app.register_blueprint(api_bp, url_prefix="/api")
