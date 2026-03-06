# price_scraper/spiders/price_spider.py
import re
import json
import scrapy
from datetime import datetime


class PriceSpider(scrapy.Spider):
    name = "prices"
    start_urls = []

    def __init__(self, urls=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if urls:
            self.start_urls = json.loads(urls)

    # ── Sélecteurs par domaine ──────────────────────────────────────────────
    # Ajoute ici les sélecteurs pour chaque site que tu surveilles.
    # Clé = fragment du domaine, valeur = sélecteur CSS du prix.
    SITE_SELECTORS = {
        "books.toscrape.com": "p.price_color::text",
        "amazon.fr":          "span.a-price-whole::text",
        "amazon.com":         "span.a-price-whole::text",
        "fnac.com":           "span.userPrice::text",
        "cdiscount.com":      "div.priceFnc::text",
        "ldlc.com":           "div.price::text",
        "darty.com":          "span.price-block__our-price::text",
        "ebay.fr":            "span.x-price-primary span::text",
    }

    # Sélecteurs génériques testés en fallback si le domaine n'est pas listé
    FALLBACK_SELECTORS = [
        "p.price_color::text",                          # books.toscrape style
        '[itemprop="price"]::attr(content)',            # Schema.org (très répandu)
        '[itemprop="price"]::text',
        'meta[property="product:price:amount"]::attr(content)',
        '[class="price"]::text',                        # classe exacte "price"
        '[class*="price_color"]::text',
    ]

    def parse(self, response):
        product_name = (
            response.css("h1::text").get("")
            or response.css("title::text").get("")
        ).strip()[:200]

        # Cherche d'abord un sélecteur spécifique au domaine
        domain = response.url.split("/")[2]  # ex: "books.toscrape.com"
        site_sel = next(
            (sel for key, sel in self.SITE_SELECTORS.items() if key in domain),
            None
        )

        price_text = ""
        if site_sel:
            price_text = (response.css(site_sel).get("") or "").strip()

        # Fallback sur les sélecteurs génériques
        if not price_text:
            for sel in self.FALLBACK_SELECTORS:
                val = response.css(sel).get("")
                if val and val.strip():
                    price_text = val.strip()
                    break

        price = self._clean_price(price_text)

        # Détection de la devise depuis le texte du prix ou les métadonnées
        currency = "EUR"
        currency_text = price_text + response.css('[itemprop="priceCurrency"]::attr(content)').get("")
        if "£" in currency_text:
            currency = "GBP"
        elif "$" in currency_text:
            currency = "USD"
        elif "CHF" in currency_text:
            currency = "CHF"

        if price is not None:
            self.logger.info(f"[OK] {product_name} => {price} {currency} (via '{site_sel or 'fallback'}')")
            yield {
                "url": response.url,
                "product_name": product_name,
                "price": price,
                "currency": currency,
                "scraped_at": datetime.utcnow().isoformat(),
            }
        else:
            self.logger.warning(
                f"[WARN] Prix introuvable sur {response.url}\n"
                f"  domaine={domain}, selecteur tente='{site_sel or 'fallback'}'\n"
                f"  Ajoute ce domaine dans SITE_SELECTORS avec le bon selecteur CSS."
            )

    @staticmethod
    def _clean_price(price_str: str) -> float | None:
        if not price_str:
            return None
        # Supprimer tout sauf chiffres, virgule et point
        cleaned = re.sub(r"[^\d,.]", "", price_str.strip())
        if not cleaned:
            return None
        # Convertir la virgule française en point
        cleaned = cleaned.replace(",", ".")
        # Si plusieurs points : garder le dernier comme décimale
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return None