# price_scraper/spider_runner.py
"""
Script autonome — lancé en subprocess par Flask pour isoler Twisted de asyncio.

Architecture anti-namespace-bug :
  Le pipeline écrit chaque item dans un fichier JSONL temporaire.
  Après process.start(), run() lit ce fichier.
  => Zéro variable partagée entre __main__ et price_scraper.spider_runner.
"""
import os
import json
import sys
import tempfile
import atexit
from dotenv import load_dotenv

load_dotenv()

from price_scraper.database import (
    initialize_db,
    upsert_product,
    insert_price,
    get_last_price,
    log_scrape_start,
    log_scrape_finish,
)
from price_scraper.notifier import send_price_alert, send_scrape_summary
from price_scraper.sheets import update_sheet

URLS_TO_SCRAPE: list[str] = json.loads(os.getenv("URLS_TO_SCRAPE", "[]"))
ALERT_THRESHOLD_PCT: float = float(os.getenv("ALERT_THRESHOLD_PCT", "1.0"))

# Fichier temporaire partagé via variable d'environnement — visible par tous
# les namespaces du même processus
_TMPFILE_ENV_KEY = "_SCRAPER_TMPFILE"


class PricePipeline:
    """
    Écrit chaque item scraped dans un fichier JSONL temporaire.
    Contourne totalement le problème __main__ vs module namespace.
    """

    def open_spider(self, spider=None):
        path = os.environ.get(_TMPFILE_ENV_KEY, "")
        if not path:
            # Ne devrait pas arriver, mais sécurité
            fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="scraper_")
            os.close(fd)
            os.environ[_TMPFILE_ENV_KEY] = path
        self._path = path
        self._f = open(path, "a", encoding="utf-8")
        print(f"[DEBUG] Pipeline ouvert -> {path}")

    def close_spider(self, spider=None):
        if hasattr(self, "_f"):
            self._f.flush()
            self._f.close()
        print("[DEBUG] Pipeline ferme")

    def process_item(self, item, spider=None):
        row = dict(item)
        url = row["url"]
        name = row.get("product_name", "Produit inconnu")
        price = row["price"]
        currency = row.get("currency", "EUR")

        try:
            product_id = upsert_product(url, name)
            last_price = get_last_price(product_id)
            insert_price(product_id, price, currency)

            price_change = 0.0
            if last_price is not None:
                price_change = price - last_price
                pct = abs(price_change / last_price * 100)
                if pct >= ALERT_THRESHOLD_PCT:
                    print(f"[ALERTE] {name}: {last_price:.2f} -> {price:.2f} {currency} ({pct:+.1f}%)")
                    send_price_alert(name, url, last_price, price, currency)
            else:
                print(f"[NOUVEAU] {name} a {price:.2f} {currency}")

            row["price_change"] = price_change
            row["old_price"] = last_price

            # Écriture atomique dans le fichier JSONL
            self._f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._f.flush()

        except Exception as e:
            print(f"[ERREUR] Pipeline pour {url}: {e}", file=sys.stderr)

        return item


def _read_results(path: str) -> list[dict]:
    """Lit le fichier JSONL et retourne la liste des résultats."""
    results = []
    if not path or not os.path.exists(path):
        return results
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return results


def run():
    if not URLS_TO_SCRAPE:
        print("[WARN] Aucune URL dans URLS_TO_SCRAPE -- configure la variable d'environnement")
        sys.exit(0)

    initialize_db()
    log_id = log_scrape_start()

    # Créer le fichier temporaire et l'enregistrer dans l'env du processus
    fd, tmp_path = tempfile.mkstemp(suffix=".jsonl", prefix="scraper_results_")
    os.close(fd)
    os.environ[_TMPFILE_ENV_KEY] = tmp_path
    atexit.register(lambda: os.path.exists(tmp_path) and os.remove(tmp_path))

    print(f"[DEBUG] Fichier temporaire : {tmp_path}")
    print(f"[DEBUG] URLs a scraper : {URLS_TO_SCRAPE}")

    errors = []
    try:
        os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "price_scraper.spiders.settings")

        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings

        settings = get_project_settings()
        # Référencer PricePipeline par son chemin complet dans le module importé
        settings.set("ITEM_PIPELINES", {
            "price_scraper.spider_runner.PricePipeline": 300
        })

        process = CrawlerProcess(settings)
        process.crawl("prices", urls=json.dumps(URLS_TO_SCRAPE))
        process.start()  # Bloquant — reprend ici une fois le crawl terminé

        # Lire les résultats depuis le fichier — aucun problème de namespace
        results = _read_results(tmp_path)
        print(f"[DEBUG] Items lus depuis le fichier : {len(results)}")

        if results:
            update_sheet(results)

        drops = sum(1 for r in results if (r.get("price_change") or 0) < 0)
        rises = sum(1 for r in results if (r.get("price_change") or 0) > 0)
        send_scrape_summary(len(results), drops, rises, len(errors))

        status = "success" if results else ("error" if errors else "success")
        log_scrape_finish(log_id, status, len(results), "; ".join(errors) or None)

        print(f"[OK] Scraping termine : {len(results)} produits, {len(errors)} erreurs")
        sys.exit(0)

    except Exception as e:
        import traceback
        traceback.print_exc()
        log_scrape_finish(log_id, "error", 0, str(e))
        print(f"[ERREUR FATALE] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()