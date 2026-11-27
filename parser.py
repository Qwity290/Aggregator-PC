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

def fetch_html(target_url, enc="utf-8", tout=15):
    if not API_KEY:
        return ""
    s, q = chr(47), chr(63)
    api = "https:" + s + s + "api." + "scraperapi.com" + s + q
    qs = urllib.parse.urlencode({"api_key": API_KEY, "url": target_url})
    with urllib.request.urlopen(urllib.request.Request(api + qs), timeout=tout) as r:
        return r.read().decode(enc, errors="ignore")

def parse_by_shop(shop, html, floor):
    if shop == "Яндекс Маркет":
        raw = re.findall(r'(?:snippet-price-current|"value"|"price")\s*[:=>"\s]+(\d{4,6})', html)[:5]
    else:
        # Ищем цены в рублях из сниппетов DuckDuckGo для Ozon, DNS и Онлайн Трейд
        raw = re.findall(r'(\d{2,3}[\s\u00a0]\d{3})\s*(?:₽|руб|р\.)', html)[:10]
    nums = [int(re.sub(r"\D", "", x)) for x in raw if re.sub(r"\D", "", x)]
    return [n for n in nums if floor <= n <= 350000]

def check_shop_price(shop, word, ref=0):
    s, q = chr(47), chr(63)
    domains = {"Ozon": "ozon.ru", "DNS": "dns-shop.ru", "Онлайн Трейд": "onlinetrade.ru"}
    if shop == "Яндекс Маркет":
        # Добавляем категорию, чтобы не цеплять готовые ПК в сборе
        prefix = "процессор " if "ryzen" in word.lower() else ("видеокарта " if any(x in word.lower() for x in ["rtx", "rx"]) else "")
        url = "https:" + s + s + "market.yandex.ru" + s + "search" + q + "text=" + urllib.parse.quote(prefix + word)
    elif shop in domains:
        ddg_q = urllib.parse.quote(f"site:{domains[shop]} {word} цена руб")
        url = "https:" + s + s + "://duckduckgo.com" + s + "html" + s + q + "q=" + ddg_q
    else:
        return None, None
    try:
        html = fetch_html(url, "utf-8", 15)
        if len(html) < 1000 or "smartcaptcha" in html.lower():
            return None, None
        prices = parse_by_shop(shop, html, get_floor(word, ref))
        if prices:
            return min(prices), True
    except Exception as e:
        print(f" [DEBUG] {shop} ({word}): {e}", flush=True)
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
