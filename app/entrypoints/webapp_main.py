from aiohttp import web

from app.config.settings import read_int, read_str
from database import init_db
from webapp_api import create_app


def main() -> None:
    init_db()
    host = read_str("WEBAPP_HOST", "127.0.0.1")
    port = read_int("WEBAPP_PORT", 8080)
    web.run_app(create_app(), host=host, port=port)

