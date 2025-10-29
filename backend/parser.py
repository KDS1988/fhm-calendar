from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import json
from datetime import date, datetime, timedelta
import os

# === Настройки ===
LOGIN_URL = 'http://referee.fhmoscow.com/adm/index.php'
TARGET_URL = 'http://referee.fhmoscow.com/adm/vsporte.php'
LOGIN = os.getenv('FHMO_LOGIN', 'VSporte')
PASSWORD = os.getenv('FHMO_PASS', '12345')

def parse_date_str(date_str):
    """Парсит строку вида 1.10.2025 или 01.10.2025"""
    try:
        d, m, y = map(int, str(date_str).strip().split('.'))
        return date(y, m, d)
    except:
        return None

def parse_vsporte():
    """Основная функция парсинга, возвращает список словарей"""
    with sync_playwright() as p:
        print("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        try:
            print("🔐 Переходим на страницу входа...")
            for attempt in range(3):
                try:
                    page.goto(LOGIN_URL, timeout=30000)
                    page.wait_for_load_state('domcontentloaded')
                    print("✅ Страница загружена")
                    break
                except PlaywrightTimeoutError:
                    print(f"⚠️ Таймаут при загрузке (попытка {attempt + 1})")
                    if attempt == 2:
                        raise Exception("❌ Не удалось загрузить страницу после 3 попыток")

            print("📝 Вводим логин и пароль...")
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Ищем кнопку входа
            print("🖱 Нажимаем кнопку входа...")
            selectors = [
                'input[type="submit"]',
                'input[value="Войти"]',
                'button[type="submit"]',
            ]

            button_clicked = False
            for selector in selectors:
                try:
                    if page.locator(selector).is_visible():
                        page.locator(selector).click()
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("❌ Кнопка входа не найдена")

            page.wait_for_timeout(2000)

            print("⏳ Переходим на vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')

            # Ждём таблицу
            print("⏳ Ожидаем таблицу 'БЛИЖАЙШИЕ МАТЧИ'...")
            page.wait_for_function("""
                () => {
                    const th = Array.from(document.querySelectorAll('th'))
                        .find(el => el.textContent.includes('БЛИЖАЙШИЕ МАТЧИ'));
                    if (!th) return false;
                    const table = th.closest('table');
                    const rows = table.querySelectorAll('tr:has(td)');
                    return rows.length > 0;
                }
            """, timeout=15000)

            # Получаем таблицу
            table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
            row_locators = table_locator.locator('tr:has(td)').all()
            print(f"🔍 Найдено строк с данными: {len(row_locators)}")

            data = []

            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                # Формируем пару команд
                pair = " – ".join(filter(None, [texts[6], texts[7]])) if len(texts) > 7 else ""

                # Парсим дату
                date_str = texts[1] if len(texts) > 1 else ""
                parsed_date = parse_date_str(date_str)
                formatted_date = parsed_date.strftime('%d.%m.%Y') if parsed_date else date_str

                # Формируем объект
                match_data = {
                    "day": texts[0] if len(texts) > 0 else "",
                    "date": formatted_date,
                    "tour": texts[2] if len(texts) > 2 else "",
                    "game_number": texts[3] if len(texts) > 3 else "",
                    "time": texts[4] if len(texts) > 4 else "",
                    "year": texts[5] if len(texts) > 5 else "",
                    "pair": pair,
                    "name": texts[8] if len(texts) > 8 else "",
                    "map_link": texts[9] if len(texts) > 9 else "",
                    "address": texts[10] if len(texts) > 10 else ""
                }

                data.append(match_data)

            print(f"📋 Найдено матчей: {len(data)}")
            return data

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            try:
                page.screenshot(path="error_screenshot.png")
            except:
                pass
            raise
        finally:
            browser.close()

if __name__ == "__main__":
    # Тестовый запуск
    result = parse_vsporte()
    print(json.dumps(result, ensure_ascii=False, indent=2))
