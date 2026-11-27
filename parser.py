import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

API_KEY = os.environ.get("SCRAPER_API_KEY", "").strip()

def fetch_via_scraperapi(target_url):
    """Загружает страницу магазина через бесплатный тариф ScraperAPI."""
    if not API_KEY:
        return ""
    s = chr(47)
    q = chr(63)
    params = {
        "api_key": API_KEY,
        "url": target_url
    }
    api_url = f"https:{s}{s}://scraperapi.com{s}{q}" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api_url)
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8", errors="ignore")

def check_shop_price(shop, search_word):
    """Ищет минимальную цену и наличие товара в указанном магазине."""
    encoded = urllib.parse.quote(search_word)
    s = chr(47)
    q = chr(63)
    
    if shop == "DNS":
        url = f"https:{s}{s}www.dns-shop.ru{s}search{s}{q}q={encoded}"
    elif shop == "Ozon":
        url = f"https:{s}{s}www.ozon.ru{s}search{s}{q}text={encoded}"
    elif shop == "Яндекс Маркет":
        url = f"https:{s}{s}market.yandex.ru{s}search{q}text={encoded}"
    elif shop == "Онлайн Трейд":
        url = f"https:{s}{s}www.onlinetrade.ru{s}sitesearch.html{q}query={encoded}"
    else:
        return None, None

    try:
        html = fetch_via_scraperapi(url)
        if not html or len(html) < 1000:
            return None, None

        lower_html = html.lower()
        if "ничего не найдено" in lower_html or "товаров не найдено" in lower_html:
            return 0, False

        raw_prices = re.findall(r'(\d[\d\s\u00a0]{2,8})\s*₽', html)
        valid_prices = []
        for p in raw_prices:
            clean_num = int(re.sub(r'\D', '', p))
            if 3000 <= clean_num <= 450000:
                valid_prices.append(clean_num)

        if valid_prices:
            return min(valid_prices), True

    except Exception as e:
        print(f"Ошибка при проверке {shop} ({search_word}): {e}")

    return None, None

def main():
    with open("prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    cache = {}

    for item in data["products"]:
        shop = item["shop"]
        word = item["searchWord"]
        cache_key = f"{shop}_{word}"

        if cache_key in cache:
            new_price, in_stock = cache[cache_key]
        else:
            print(f"Проверяю {shop}: {word}...")
            new_price, in_stock = check_shop_price(shop, word)
            cache[cache_key] = (new_price, in_stock)

        if new_price is not None:
            item["price"] = new_price
            item["inStock"] = in_stock
            print(f" -> Успех: {new_price} ₽ (в наличии: {in_stock})")
        else:
            print(f" -> Оставлена резервная цена: {item['price']} ₽")

    msk_tz = timezone(timedelta(hours=3))
    data["updated_at"] = datetime.now(msk_tz).strftime("%d.%m.%Y %H:%M МСК")

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
