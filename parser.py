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

def fetch_html(target_url, enc="utf-8"):
    if not API_KEY:
        return ""
    s, q = chr(47), chr(63)
    api = "https:" + s + s + "api." + "scraperapi.com" + s + q
    qs = urllib.parse.urlencode({"api_key": API_KEY, "url": target_url, "country_code": "ru"})
    with urllib.request.urlopen(urllib.request.Request(api + qs), timeout=35) as r:
        return r.read().decode(enc, errors="ignore")

def parse_by_shop(shop, html, floor):
    if shop == "DNS":
        raw = re.findall(r'(?:product-buy__price|data-product-price)[^>]*>([\d\s\u00a0]+)', html)
    elif shop == "Онлайн Трейд":
        raw = re.findall(r'class="price(?:\s+regular)?"[^>]*>([\d\s\u00a0]+)\s*₽', html)
    elif shop == "Яндекс Маркет":
        raw = re.findall(r'(?:snippet-price-current|"value"|"price")\s*[:=>"\s]+(\d{4,6})', html)
    elif shop == "Ozon":
        raw = re.findall(r'(?:"finalPrice"|"price"|tsHeadline500Medium)[^>":]*[:>"]\s*([\d\s\u00a0]{4,8})', html)
    else:
        return []
    nums = [int(re.sub(r"\D", "", x)) for x in raw if re.sub(r"\D", "", x)]
    return [n for n in nums if floor <= n <= 450000]
    
def check_shop_price(shop, word, ref=0):
    s, q = chr(47), chr(63)
    enc = urllib.parse.quote(word)
    routes = {
        "DNS": ("https:" + s + s + "www.dns-shop.ru" + s + "search" + s + q + "q=" + enc, "utf-8"),
        "Ozon": ("https:" + s + s + "www.ozon.ru" + s + "search" + s + q + "text=" + enc, "utf-8"),
        "Яндекс Маркет": ("https:" + s + s + "market.yandex.ru" + s + "search" + q + "text=" + enc, "utf-8"),
        "Онлайн Трейд": ("https:" + s + s + "www.onlinetrade.ru" + s + "sitesearch.html" + q + "query=" + enc, "windows-1251"),
    }
    if shop not in routes:
        return None, None
    url, charset = routes[shop]
    try:
        html = fetch_html(url, charset)
        low = html.lower()
        if len(html) < 1500 or "smartcaptcha" in low:
            return None, None
        if "ничего не найдено" in low or "товаров не найдено" in low:
            return 0, False
        prices = parse_by_shop(shop, html, get_floor(word, ref))
        if prices:
            return min(prices), True
    except Exception as e:
        print(f"Ошибка {shop} ({word}): {e}")
    return None, None

def process_task(task):
    shop, word, ref = task
    print(f"Проверяю {shop}: {word}...")
    res = check_shop_price(shop, word, ref)
    time.sleep(1.2)
    return (shop, word, res[0], res[1])

def main():
    with open("prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    refs = {(i["shop"], i["searchWord"]): i["price"] for i in data["products"] if i["price"] > 0}
    tasks = [(s, w, refs.get((s, w), 0)) for (s, w) in set((i["shop"], i["searchWord"]) for i in data["products"])]
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
