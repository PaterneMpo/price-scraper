# price_scraper/app.py
import os
import sys
import subprocess
import threading
from datetime import datetime

from flask import Flask, render_template, jsonify, request, abort
from dotenv import load_dotenv

load_dotenv()

# ── Scrape state (partagé en mémoire) ────────────────────────────────────────
_scrape_lock = threading.Lock()
_scrape_state = {
    "status": "idle",       # idle | running | success | error
    "started_at": None,
    "finished_at": None,
    "products_updated": 0,
    "error": None,
}


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates")
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    from price_scraper.database import initialize_db
    initialize_db()

    _start_scheduler(app)

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route("/")
    def dashboard():
        from price_scraper.database import get_all_products, get_stats, get_last_scrape_log, get_recent_alerts
        products = [dict(p) for p in get_all_products()]
        stats = get_stats()
        last_log = get_last_scrape_log()
        recent_alerts = [dict(a) for a in get_recent_alerts(limit=3)]

        return render_template(
            "dashboard.html",
            products=products,
            stats=stats,
            last_log=dict(last_log) if last_log else None,
            scrape_state=_scrape_state,
            sheet_url=os.getenv("GOOGLE_SHEET_PUBLIC_URL", ""),
            slack_configured=bool(os.getenv("SLACK_WEBHOOK_URL")),
            slack_channel=os.getenv("SLACK_CHANNEL_NAME", "#prices"),
            scrape_hour=os.getenv("SCRAPE_HOUR", "8"),
            recent_alerts=recent_alerts,
            alert_threshold=os.getenv("ALERT_THRESHOLD_PCT", "1.0"),
        )

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "ts": datetime.utcnow().isoformat()})

    @app.route("/api/products")
    def api_products():
        from price_scraper.database import get_all_products
        return jsonify([dict(p) for p in get_all_products()])

    @app.route("/api/prices/<int:product_id>")
    def api_prices(product_id: int):
        from price_scraper.database import get_price_history
        rows = get_price_history(product_id, limit=60)
        return jsonify([dict(r) for r in rows])

    @app.route("/api/stats")
    def api_stats():
        from price_scraper.database import get_stats
        return jsonify(get_stats())

    @app.route("/api/scrape", methods=["POST"])
    def api_scrape():
        # request.get_json(silent=True) ne lève jamais d'exception (contrairement à request.json)
        data = request.get_json(silent=True) or {}
        token = request.headers.get("X-Scrape-Token") or data.get("token", "")
        expected = os.getenv("SCRAPE_SECRET_TOKEN", "changeme")

        if not token or token != expected:
            return jsonify({"error": "Token invalide"}), 401

        if _scrape_state["status"] == "running":
            return jsonify({"status": "already_running"})

        t = threading.Thread(target=_run_scraper_bg, daemon=True)
        t.start()
        return jsonify({"status": "started"})

    @app.route("/api/scrape/status")
    def api_scrape_status():
        return jsonify(_scrape_state)

    return app


# ── Background scraper ────────────────────────────────────────────────────────

def _run_scraper_bg():
    with _scrape_lock:
        _scrape_state.update({"status": "running", "started_at": datetime.utcnow().isoformat(), "error": None})

    # Racine du projet = dossier parent de price_scraper/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        result = subprocess.run(
            [sys.executable, "-m", "price_scraper.spider_runner"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=project_root,
            env={**os.environ, "PYTHONPATH": project_root, "PYTHONIOENCODING": "utf-8"},
        )
        # Affiche stdout/stderr dans le terminal Flask pour debug
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[-2000:])

        if result.returncode == 0:
            _scrape_state.update({"status": "success", "error": None})
        else:
            error_msg = result.stderr[-1000:] if result.stderr else f"Exit code {result.returncode}"
            _scrape_state.update({"status": "error", "error": error_msg})
    except subprocess.TimeoutExpired:
        _scrape_state.update({"status": "error", "error": "Timeout (10 min)"})
    except Exception as e:
        _scrape_state.update({"status": "error", "error": str(e)})
    finally:
        _scrape_state["finished_at"] = datetime.utcnow().isoformat()


# ── Scheduler ────────────────────────────────────────────────────────────────

def _start_scheduler(app: Flask):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(timezone="UTC")
        hour = int(os.getenv("SCRAPE_HOUR", "8"))
        scheduler.add_job(_run_scraper_bg, "cron", hour=hour, minute=0, id="daily_scrape")
        scheduler.start()

        import atexit
        atexit.register(lambda: scheduler.shutdown(wait=False))
        print(f"✅ Scheduler démarré — scraping quotidien à {hour:02d}:00 UTC")
    except Exception as e:
        print(f"⚠️  Scheduler non démarré : {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = create_app()
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Dashboard disponible sur http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()