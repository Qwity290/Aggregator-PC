import json
import time
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

API_KEY = os.environ.get("SCRAPER_API_KEY", "").strip()

def fetch_via_scraperapi(target_url, render_js=False, encoding="utf-8"):
    if not API_KEY:
        return ""
    params = {"api_key": API_KEY, "url": target_url, "country_code": "ru"}
    if render_js:
        params["render"] = "true"
    api_url = "https://scraperapi.com?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(api_url)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode(encoding, errors="ignore")

def clean_int(text):
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else 0

MIN_MARKET_FLOOR = {
    "5090": 180000, "5080": 110000, "5070": 55000, "4090": 160000,
    "4080": 95000, "4070": 48000, "4060": 26000, "3060": 22000,
    "7900": 65000, "7800": 42000, "7700": 35000, "7600": 23000,
    "9800x3d": 42000, "7800x3d": 25000, "7500f": 10500, "5700x3d": 16000,
    "5600": 7500, "ddr5": 6500, "ssd": 3500
}
STOP_WORDS = ("кабель", "переходник", "райзер", "подставка", "коробка", "водоблок", "крепление")

def get_min_floor(search_word, ref_price):
    w = search_word.lower()
    for key, floor in MIN_MARKET_FLOOR.items():
        if key in w:
            return floor
    return max(int(ref_price * 0.7), 3000) if ref_price > 3000 else 3000

def title_matches(title, search_word):
    t = title.lower()
    if any(bad in t for bad in STOP_WORDS):
        return False
    tokens = [tok.lower() for tok in search_word.split() if len(tok) >= 3]
    hits = sum(1 for tok in tokens if tok in t)
    return hits >= max(1, len(tokens) - 1)

def extract_shop_prices(shop, html, search_word, floor):
    soup = BeautifulSoup(html, "html.parser")
    prices = []

    if shop == "Онлайн Трейд":
        for card in soup.select(".indexGoods__item")[:8]:
            t = card.select_one(".indexGoods__item__name")
            p = card.select_one(".price.regular, .price")
            if t and p and title_matches(t.text, search_word):
                val = clean_int(p.text)
                if floor <= val <= 450000:
                    prices.append(val)

    elif shop == "DNS":
        for card in soup.select(".catalog-product")[:8]:
            t = card.select_one(".catalog-product__name")
            p = card.select_one(".product-buy__price")
            if t and p and title_matches(t.text, search_word):
                val = clean_int(p.text.split("₽"))
                if floor <= val <= 450000:
                    prices.append(val)

    elif shop == "Яндекс Маркет":
        for card in soup.select("article[data-autotest-id='product-snippet'], [data-zone-name='productSnippet']")[:10]:
            t = card.select_one("[data-auto='snippet-title'], h3")
            p = card.select_one("[data-auto='snippet-price-current']")
            if t and p and "×" not in p.text and "мес" not in p.text.lower():
                if title_matches(t.text, search_word):
                    val = clean_int(p.text)
                    if floor <= val <= 450000:
                        prices.append(val)

    elif shop == "Ozon":
        root = soup.select_one("[data-widget='searchResultsV2']") or soup
        for card in root.select("div[data-index]")[:10]:
            lines = [s.strip() for s in card.stripped_strings]
            title = next((x for x in lines if len(x) > 18 and "₽" not in x), "")
            if not title_matches(title, search_word):
                continue
            for line in lines:
                if "₽" in line and not line.startswith("+") and "мес" not in line.lower():
                    val = clean_int(line)
                    if floor <= val <= 450000:
                        prices.append(val)
                    break
    return prices

def check_shop_price(shop, search_word, ref_price=0):
    enc = urllib.parse.quote(search_word)
    urls = {
        "DNS": (f"https://dns-shop.ru{enc}", True, "utf-8"),
        "Ozon": (f"https://ozon.ru{enc}&from_global=true", True, "utf-8"),
        "Яндекс Маркет": (f"https://yandex.ru{enc}", True, "utf-8"),
        "Онлайн Трейд": (f"https://onlinetrade.ru{enc}", False, "windows-1251"),
    }
    if shop not in urls:
        return None, None
    url, need_js, enc_type = urls[shop]
    try:
        html = fetch_via_scraperapi(url, render_js=need_js, encoding=enc_type)
        if not html or len(html) < 1500 or "smartcaptcha" in html.lower():
            return None, None
        if "ничего не найдено" in html.lower() or "товаров не найдено" in html.lower():
            return 0, False
        floor = get_min_floor(search_word, ref_price)
        prices = extract_shop_prices(shop, html, search_word, floor)
        if prices:
            return min(prices), True
    except Exception as e:
        print(f"Ошибка {shop} ({search_word}): {e}")
    return None, None

def process_task(task):
    shop, word, ref_price = task
    print(f"Проверяю {shop}: {word}...")
    new_price, in_stock = check_shop_price(shop, word, ref_price)
    time.sleep(1.5)
    return (shop, word, new_price, in_stock)

def main():
    with open("prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    ref_map = {(i["shop"], i["searchWord"]): i["price"] for i in data["products"] if i["price"] > 0}
    tasks = [(s, w, ref_map.get((s, w), 0)) for (s, w) in set((i["shop"], i["searchWord"]) for i in data["products"])]
    cache = {}
    with ThreadPoolExecutor(max_workers=1) as ex:
        for shop, word, p, stock in ex.map(process_task, tasks):
            cache[f"{shop}_{word}"] = (p, stock)
            if p is not None:
                print(f" -> Успех {shop} ({word}): {p} ₽")
    for item in data["products"]:
        p, stock = cache.get(f"{item['shop']}_{item['searchWord']}", (None, None))
        if p is not None:
            item["price"], item["inStock"] = p, stock
    data["updated_at"] = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M МСК")
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
