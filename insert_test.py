import sys
import os
sys.path.insert(0, '.')

# Charger le .env pour avoir le bon DB_PATH
from dotenv import load_dotenv
load_dotenv()

from price_scraper.database import initialize_db
import sqlite3
from pathlib import Path

initialize_db()

db_path = Path(os.getenv("DB_PATH", "prices.db"))
print(f"DB utilisee : {db_path.resolve()}")

conn = sqlite3.connect(db_path)

# Lister tous les produits disponibles
rows = conn.execute("SELECT id, name FROM products").fetchall()
if not rows:
    print("Aucun produit en base — lance d'abord un scraping depuis le dashboard !")
    conn.close()
    sys.exit(1)

print("Produits disponibles :")
for r in rows:
    print(f"  id={r[0]} | {r[1]}")

# Prendre le premier produit
product_id = rows[0][0]
product_name = rows[0][1]

# Récupérer son dernier prix
last = conn.execute(
    "SELECT price, currency FROM price_history WHERE product_id = ? ORDER BY scraped_at DESC LIMIT 1",
    (product_id,)
).fetchone()

if last:
    print(f"\nDernier prix connu : {last[0]} {last[1]}")
    fake_price = round(last[0] * 0.80, 2)  # -20% pour forcer une alerte
    print(f"Insertion d'un faux prix : {fake_price} {last[1]} (-20%)")
    conn.execute(
        "INSERT INTO price_history (product_id, price, currency, scraped_at) VALUES (?, ?, ?, datetime('now'))",
        (product_id, fake_price, last[1])
    )
    conn.commit()
    print(f"OK - Relance maintenant le scraper depuis le dashboard !")
else:
    print("Aucun prix en base pour ce produit.")

conn.close()
