import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

def check_onlinetrade(search_word):
    """Пытается получить минимальную цену и наличие товара в Онлайн Трейд."""
    try:
        encoded = urllib.parse.quote(search_word)
        url = f"https://onlinetrade.ru{encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("windows-1251", errors="ignore")
            
            # Ищем все цены в карточках товаров на странице поиска
            prices = re.findall(r'class="price[^"]*"[^>]*>([\d\s]+)\s*₽', html)
            valid_prices = []
            for p in prices:
                clean_num = int(re.sub(r'\D', '', p))
                if clean_num > 1000:  # Отсекаем случайные мелкие цифры
                    valid_prices.append(clean_num)
            
            if valid_prices:
                return min(valid_prices), True
            elif "Ничего не найдено" in html:
                return 0, False
    except Exception as e:
        print(f"Ошибка при проверке {search_word}: {e}")
    
    # Если сайт заблокировал запрос или не ответил — возвращаем None (оставим старую цену)
    return None, None

def main():
    with open("prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data["products"]:
        if item["shop"] == "Онлайн Трейд":
            new_price, in_stock = check_onlinetrade(item["searchWord"])
            if new_price is not None:
                item["price"] = new_price
                item["inStock"] = in_stock
                print(f"Обновлено для {item['searchWord']}: {new_price} руб., в наличии: {in_stock}")

    # Фиксируем текущее время по Москве (UTC+3)
    msk_tz = timezone(timedelta(hours=3))
    data["updated_at"] = datetime.now(msk_tz).strftime("%d.%m.%Y %H:%M МСК")

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
