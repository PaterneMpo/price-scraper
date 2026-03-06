# price_scraper/spiders/settings.py
import os

BOT_NAME = "price_scraper"
SPIDER_MODULES = ["price_scraper.spiders"]
NEWSPIDER_MODULE = "price_scraper.spiders"

ROBOTSTXT_OBEY = False
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 4
COOKIES_ENABLED = True

# Retry
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# Timeout
DOWNLOAD_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Ne pas demander brotli — évite le warning si brotli n'est pas installé
# Scrapy décode gzip et deflate nativement, c'est suffisant
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",   # ← 'br' retiré volontairement
}

DOWNLOADER_MIDDLEWARES = {
    "price_scraper.spiders.middlewares.BrightDataMiddleware": 350,
}

LOG_LEVEL = "WARNING"
TELNETCONSOLE_ENABLED = False
FEEDS = {}