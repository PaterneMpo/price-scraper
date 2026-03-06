# price_scraper/sheets.py
import os
import json
from datetime import datetime


def _get_client():
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            creds_dict = json.loads(creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        elif os.path.exists("credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scopes)
        else:
            return None

        return gspread.authorize(creds)
    except Exception as e:
        print(f"[ERREUR] credentials Google : {e}")
        return None


def update_sheet(results: list):
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("[WARN] GOOGLE_SHEET_ID non defini, export ignore")
        return

    client = _get_client()
    if not client:
        print("[WARN] Impossible de s'authentifier a Google Sheets")
        return

    try:
        spreadsheet = client.open_by_key(sheet_id)

        # ── Feuille 1 : Derniers prix ────────────────────────────────
        sheet1 = spreadsheet.sheet1
        # Initialiser les headers si vide
        if not sheet1.row_values(1):
            sheet1.append_row(
                ["Date", "Produit", "Prix", "Devise", "Variation (€)", "Variation (%)", "URL"],
                value_input_option="USER_ENTERED",
            )
            # Formater le header en gras
            sheet1.format("A1:G1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.37}})

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        rows_to_add = []
        for item in results:
            old = item.get("old_price")
            new = item.get("price", 0)
            change_val = round(new - old, 2) if old else ""
            change_pct = round((new - old) / old * 100, 2) if old else ""
            rows_to_add.append([
                now,
                item.get("product_name", "N/A"),
                new,
                item.get("currency", "EUR"),
                change_val,
                change_pct,
                item.get("url", ""),
            ])

        if rows_to_add:
            sheet1.append_rows(rows_to_add, value_input_option="USER_ENTERED")

        # ── Feuille 2 : Résumé produits ─────────────────────────────
        try:
            summary = spreadsheet.worksheet("Résumé")
        except Exception:
            summary = spreadsheet.add_worksheet("Résumé", rows=200, cols=10)
            summary.append_row(
                ["Produit", "Prix actuel", "Devise", "Dernière mise à jour", "URL"],
                value_input_option="USER_ENTERED",
            )
            summary.format("A1:E1", {"textFormat": {"bold": True}})

        # Vider et réécrire le résumé
        summary.clear()
        summary.append_row(["Produit", "Prix actuel", "Devise", "Dernière MàJ", "URL"])
        for item in results:
            summary.append_row([
                item.get("product_name", "N/A"),
                item.get("price", 0),
                item.get("currency", "EUR"),
                now,
                item.get("url", ""),
            ])

        print(f"[OK] Google Sheet mis a jour : {len(results)} produits")

    except Exception as e:
        print(f"[ERREUR] Google Sheets : {e}")
