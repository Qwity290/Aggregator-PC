import json, time, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

API_KEY = os.environ.get("SCRAPER_API_KEY", "").strip()
FLOORS = {
    "5090": 190000, "5080": 115000, "5070": 62000, "4090": 165000,
    "4080": 98000, "4070": 55000, "4060 ti": 36000, "4060": 29000,
    "3060": 24000, "7900": 75000, "7800": 46000, "7600": 26000,
    "9700x": 28000, "7800x3d": 25000, "7500f": 11000, "5700x3d": 18000,
    "5600": 8500, "ddr5": 8500, "nvme": 6500, "ssd": 6500, "nv3": 6500
}

def get_floor(word, ref):
    w = word.lower()
    for k, v in FLOORS.items():
        if k in w:
            return v
    return max(int(ref * 0.7), 4000) if ref > 4000 else 4000

def fetch_html(target_url, enc="utf-8", tout=12):
    if not API_KEY:
        return ""
    s, q = chr(47), chr(63)
    api = "https:" + s + s + "api." + "scraperapi.com" + s + q
    qs = urllib.parse.urlencode({"api_key": API_KEY, "url": target_url})
    with urllib.request.urlopen(urllib.request.Request(api + qs), timeout=tout) as r:
        return r.read().decode(enc, errors="ignore")

def parse_by_shop(shop, html, floor):
    if shop == "Онлайн Трейд":
        raw = re.findall(r'indexGoods__item__price[^>]*>.*?([\d\s\u00a0]{4,9})', html, re.S)[:6]
        if not raw:
            raw = re.findall(r'([\d]{2,3}[\s\u00a0][\d]{3})\s*(?:₽|&#8381;)', html)[:6]
    elif shop == "Яндекс Маркет":
        raw = re.findall(r'(?:snippet-price-current|"value"|"price")\s*[:=>"\s]+(\d{4,6})', html)[:5]
    elif shop in ("DNS", "Ozon"):
        raw = re.findall(r'(\d{2,3}[\s\u00a0]\d{3})\s*(?:₽|руб)', html)[:8]
    else:
        return []
    nums = [int(re.sub(r"\D", "", x)) for x in raw if re.sub(r"\D", "", x)]
    return [n for n in nums if floor <= n <= 350000]

def check_shop_price(shop, word, ref=0):
    s, q = chr(47), chr(63)
    enc = urllib.parse.quote(word)
    oz_q = urllib.parse.quote(f"site:ozon.ru {word} цена")
    dns_q = urllib.parse.quote(f"site:dns-shop.ru {word} цена")
    routes = {
        "Онлайн Трейд": ("https:" + s + s + "www.onlinetrade.ru" + s + "sitesearch.html" + q + "query=" + enc, "windows-1251"),
        "Яндекс Маркет": ("https:" + s + s + "market.yandex.ru" + s + "search" + q + "text=" + enc, "utf-8"),
        "Ozon": ("https:" + s + s + "yandex.ru" + s + "search" + s + q + "text=" + oz_q, "utf-8"),
        "DNS": ("https:" + s + s + "yandex.ru" + s + "search" + s + q + "text=" + dns_q, "utf-8"),
    }
    if shop not in routes:
        return None, None
    url, charset = routes[shop]
    try:
        html = fetch_html(url, charset, 12)
        low = html.lower()
        if len(html) < 1500 or "smartcaptcha" in low:
            return None, None
        if "ничего не найдено" in low or "товаров не найдено" in low:
            return 0, False
        prices = parse_by_shop(shop, html, get_floor(word, ref))
        if prices:
            return min(prices), True
    except Exception:
        pass
    return None, None

def process_task(task):
    shop, word, ref = task
    p, stock = check_shop_price(shop, word, ref)
    time.sleep(0.5)
    return (shop, word, p, stock)

def main():
    with open("prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    refs = {(i["shop"], i["searchWord"]): i["price"] for i in data["products"] if i["price"] > 0}
    tasks = [(s, w, refs.get((s, w), 0)) for (s, w) in set((i["shop"], i["searchWord"]) for i in data["products"])]
    cache = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        for shop, word, p, stock in ex.map(process_task, tasks):
            cache[f"{shop}_{word}"] = (p, stock)
            if p is not None:
                print(f" -> Успех {shop} ({word}): {p} ₽", flush=True)
    for item in data["products"]:
        p, stock = cache.get(f"{item['shop']}_{item['searchWord']}", (None, None))
        if p is not None:
            item["price"], item["inStock"] = p, stock
    data["updated_at"] = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M МСК")
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
