# price_scraper/spiders/middlewares.py
import base64
import os


class BrightDataMiddleware:
    """Injecte les proxies résidentiels Bright Data sur chaque requête."""

    def process_request(self, request, spider=None):
        user = os.getenv("BRIGHT_DATA_USER")
        password = os.getenv("BRIGHT_DATA_PASS")
        host = os.getenv("BRIGHT_DATA_HOST")
        port = os.getenv("BRIGHT_DATA_PORT", "22225")

        if not all([user, password, host]):
            return  # Mode sans proxy (dev local)

        credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.meta["proxy"] = f"http://{host}:{port}"
        request.headers["Proxy-Authorization"] = f"Basic {credentials}"

    @classmethod
    def from_crawler(cls, crawler):
        return cls()