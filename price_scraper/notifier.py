# price_scraper/notifier.py
import os
import requests

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def send_price_alert(product_name: str, url: str, old_price: float, new_price: float, currency: str = "EUR"):
    if not SLACK_WEBHOOK:
        print("[WARN] SLACK_WEBHOOK_URL non defini, alerte ignoree")
        return

    change = new_price - old_price
    pct = (change / old_price * 100) if old_price else 0
    direction = "BAISSE" if change < 0 else "HAUSSE"
    color = "#22c55e" if change < 0 else "#ef4444"
    sign = "" if change > 0 else ""

    # Format simple et fiable — pas d'attachments imbriques
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{direction} DE PRIX DETECTEE*\n"
                        f"*Produit :* {product_name}\n"
                        f"*Ancien prix :* {old_price:.2f} {currency}\n"
                        f"*Nouveau prix :* *{new_price:.2f} {currency}*\n"
                        f"*Variation :* {sign}{pct:.1f}%\n"
                        f"*Lien :* {url}"
                    )
                }
            },
            {"type": "divider"}
        ]
    }

    try:
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        print(f"[Slack] status={resp.status_code} reponse='{resp.text}' pour {product_name}")
        resp.raise_for_status()
        print(f"[OK] Alerte Slack envoyee pour {product_name}")
    except requests.RequestException as e:
        print(f"[ERREUR] Slack : {e}")


def send_scrape_summary(total: int, drops: int, rises: int, errors: int):
    if not SLACK_WEBHOOK:
        return

    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Rapport de scraping quotidien*\n"
                        f"- {total} produits analyses\n"
                        f"- {drops} baisses de prix\n"
                        f"- {rises} hausses de prix\n"
                        f"- {errors} erreurs"
                    )
                }
            }
        ]
    }
    try:
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        print(f"[Slack] Resume envoye : status={resp.status_code}")
    except requests.RequestException as e:
        print(f"[ERREUR] Slack resume : {e}")