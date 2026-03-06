# price_scraper/database.py
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "prices.db"))


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT UNIQUE NOT NULL,
                name       TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price      REAL NOT NULL,
                currency   TEXT DEFAULT 'EUR',
                scraped_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS scrape_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                status     TEXT NOT NULL,
                products_updated INTEGER DEFAULT 0,
                errors     TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_ph_product
                ON price_history(product_id, scraped_at DESC);
        """)
    print("[OK] DB initialisee")


def upsert_product(url: str, name: str) -> int:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO products (url, name) VALUES (?, ?)", (url, name)
        )
        conn.execute(
            "UPDATE products SET name = ? WHERE url = ? AND name != ?", (name, url, name)
        )
        row = conn.execute(
            "SELECT id FROM products WHERE url = ?", (url,)
        ).fetchone()
        return row["id"]


def insert_price(product_id: int, price: float, currency: str = "EUR"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_history (product_id, price, currency, scraped_at) VALUES (?, ?, ?, ?)",
            (product_id, price, currency, datetime.utcnow().isoformat()),
        )


def get_last_price(product_id: int) -> float | None:
    """Retourne le dernier prix enregistré, pour comparer avec le prix fraîchement scrapé."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT price FROM price_history
            WHERE product_id = ?
            ORDER BY scraped_at DESC LIMIT 1
            """,
            (product_id,),
        ).fetchone()
        return row["price"] if row else None


def get_all_products():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                p.id, p.url, p.name,
                ph.price      AS current_price,
                ph2.price     AS previous_price,
                ph.currency,
                ph.scraped_at AS last_scraped
            FROM products p
            LEFT JOIN price_history ph ON ph.id = (
                SELECT id FROM price_history
                WHERE product_id = p.id
                ORDER BY scraped_at DESC LIMIT 1
            )
            LEFT JOIN price_history ph2 ON ph2.id = (
                SELECT id FROM price_history
                WHERE product_id = p.id
                ORDER BY scraped_at DESC LIMIT 1 OFFSET 1
            )
            ORDER BY p.name
            """
        ).fetchall()


def get_price_history(product_id: int, limit: int = 30):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT price, currency, scraped_at
            FROM price_history
            WHERE product_id = ?
            ORDER BY scraped_at ASC
            LIMIT ?
            """,
            (product_id, limit),
        ).fetchall()


def log_scrape_start() -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_logs (status, started_at) VALUES ('running', ?)",
            (datetime.utcnow().isoformat(),),
        )
        return cur.lastrowid


def log_scrape_finish(log_id: int, status: str, products_updated: int, errors: str = None):
    with get_connection() as conn:
        conn.execute(
            "UPDATE scrape_logs SET status=?, products_updated=?, errors=?, finished_at=? WHERE id=?",
            (status, products_updated, errors, datetime.utcnow().isoformat(), log_id),
        )


def get_last_scrape_log():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM scrape_logs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()


def get_stats():
    """Stats pour les cards du dashboard."""
    with get_connection() as conn:
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Produits scrapés aujourd'hui
        scraped_today = conn.execute(
            "SELECT COUNT(DISTINCT product_id) FROM price_history WHERE scraped_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]

        # Changements de prix détectés (produits avec 2+ entrées aujourd'hui)
        # Compte les produits où le prix a changé entre les 2 dernières entrées
        rows = conn.execute(
            """
            SELECT ph1.product_id,
                   ph1.price as new_price,
                   ph2.price as old_price
            FROM price_history ph1
            JOIN price_history ph2 ON ph2.id = (
                SELECT id FROM price_history
                WHERE product_id = ph1.product_id
                AND id < ph1.id
                ORDER BY id DESC LIMIT 1
            )
            WHERE ph1.id IN (
                SELECT MAX(id) FROM price_history GROUP BY product_id
            )
            """
        ).fetchall()

        drops = sum(1 for r in rows if r["new_price"] < r["old_price"])
        rises = sum(1 for r in rows if r["new_price"] > r["old_price"])

        return {
            "total_products": total_products,
            "scraped_today": scraped_today,
            "price_drops": drops,
            "price_rises": rises,
        }


def get_recent_alerts(limit: int = 5):
    """Retourne les dernières alertes de changement de prix."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                p.name        AS product_name,
                p.url,
                ph1.price     AS new_price,
                ph2.price     AS old_price,
                ph1.currency,
                ph1.scraped_at,
                ROUND((ph1.price - ph2.price) / ph2.price * 100, 1) AS pct_change
            FROM price_history ph1
            JOIN products p ON p.id = ph1.product_id
            JOIN price_history ph2 ON ph2.id = (
                SELECT id FROM price_history
                WHERE product_id = ph1.product_id AND id < ph1.id
                ORDER BY id DESC LIMIT 1
            )
            WHERE ph1.price != ph2.price
            ORDER BY ph1.scraped_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()