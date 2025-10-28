#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FHM Parser - Enhanced version для GitHub Actions
С улучшенной обработкой сессий и cookies
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
import json
import os
import time

load_dotenv()

LOGIN_URL = 'http://referee.fhmoscow.com/adm/index.php'
TARGET_URL = 'http://referee.fhmoscow.com/adm/vsporte.php'
LOGIN = os.getenv('FHMO_LOGIN')
PASSWORD = os.getenv('FHMO_PASS')
OUTPUT_FILE = 'matches_data.json'

if not LOGIN or not PASSWORD:
    raise EnvironmentError("❌ FHMO_LOGIN и FHMO_PASS обязательны!")


def parse_date_str(date_str):
    """Парсит дату DD.MM.YYYY"""
    try:
        d, m, y = map(int, str(date_str).strip().split('.'))
        return date(y, m, d)
    except:
        return None


def main():
    """Enhanced парсинг с сохранением сессии"""
    with sync_playwright() as p:
        print("🌐 Запускаем браузер...")

        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )

        # ОДИН контекст для всех страниц
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            accept_downloads=False,
            java_script_enabled=True,
        )

        page = context.new_page()

        try:
            # === АВТОРИЗАЦИЯ ===
            print("🔐 Авторизация...")
            page.goto(LOGIN_URL, timeout=30000, wait_until='networkidle')
            time.sleep(1)

            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Клик по кнопке
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'form button']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        print(f"✅ Кнопка нажата: {selector}")
                        break
                except:
                    continue

            # Ждем редиректа после авторизации
            time.sleep(3)
            print(f"📍 После входа: {page.url}")

            # === ПЕРЕХОД НА КАЛЕНДАРЬ ===
            print("📅 Загружаем календарь...")

            # ВАРИАНТ 1: Прямой переход
            try:
                page.goto(TARGET_URL, timeout=30000, wait_until='networkidle')
                time.sleep(2)
                print(f"📍 На странице: {page.url}")
            except Exception as e:
                print(f"⚠️ Ошибка перехода: {e}")

            # Сохраняем HTML для отладки
            content = page.content()
            with open('calendar_page.html', 'w', encoding='utf-8') as f:
                f.write(content)
            print("💾 Сохранен calendar_page.html")

            # Проверка авторизации
            if 'Вход' in content or 'content_user_login' in content:
                print("❌ Требуется повторный вход на vsporte.php")

                # ВАРИАНТ 2: Пробуем через iframe или другой метод
                # Сохраняем cookies
                cookies = context.cookies()
                print(f"🍪 Сохранено cookies: {len(cookies)}")

                # Попробуем еще раз с задержкой
                time.sleep(5)
                page.goto(TARGET_URL, timeout=30000)
                time.sleep(3)
                content = page.content()

            # === ПАРСИНГ ===
            print("🔍 Поиск таблицы...")

            # Пробуем найти таблицу БЕЗ wait_for_function
            table_found = False
            table_locator = None

            try:
                table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
                if table_locator.count() > 0:
                    table_found = True
                    print("✅ Таблица найдена!")
            except:
                pass

            # Fallback: ищем любую большую таблицу
            if not table_found:
                print("🔍 Ищем альтернативные таблицы...")
                tables = page.locator('table').all()
                print(f"  Всего таблиц: {len(tables)}")

                for i, table in enumerate(tables):
                    try:
                        rows = len(table.locator('tr').all())
                        if rows > 10:
                            table_locator = page.locator('table').nth(i)
                            table_found = True
                            print(f"✅ Используем таблицу {i+1} ({rows} строк)")
                            break
                    except:
                        pass

            if not table_found:
                print("❌ Таблица не найдена")
                page.screenshot(path='no_table_screenshot.png', full_page=True)

                # Создаем пустой JSON
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'matches': [],
                        'arenas': [],
                        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        'total_matches': 0,
                        'error': 'Таблица не найдена на странице'
                    }, f, ensure_ascii=False, indent=2)
                print("💾 Создан пустой JSON")
                return

            # Парсим строки
            row_locators = table_locator.locator('tr:has(td)').all()
            print(f"📊 Найдено строк: {len(row_locators)}")

            today = date.today()
            matches = []

            for idx, row in enumerate(row_locators):
                try:
                    cells = row.locator('td').all()
                    if len(cells) < 8:
                        continue

                    texts = [cell.inner_text().strip() for cell in cells]

                    date_str = texts[1] if len(texts) > 1 else ''
                    match_date = parse_date_str(date_str)

                    if not match_date or match_date <= today:
                        continue

                    team1 = texts[6].split('\n')[0] if len(texts) > 6 else ''
                    team2 = texts[7].split('\n')[0] if len(texts) > 7 else ''
                    pair = f"{team1} – {team2}" if team1 and team2 else ""

                    match = {
                        'day': texts[0] if len(texts) > 0 else '',
                        'date': date_str,
                        'tour': texts[2] if len(texts) > 2 else '',
                        'game_num': texts[3] if len(texts) > 3 else '',
                        'time': texts[4] if len(texts) > 4 else '',
                        'year': texts[5] if len(texts) > 5 else '',
                        'pair': pair,
                        'name': texts[7] if len(texts) > 7 else 'Первенство Москвы',
                        'arena': texts[7] if len(texts) > 7 else '',
                        'map': 'https://yandex.ru/maps/',
                        'address': texts[9] if len(texts) > 9 else ''
                    }

                    matches.append(match)

                except Exception as e:
                    continue

            print(f"✅ Спарсено {len(matches)} матчей")

            # Сохранение
            arenas = sorted(list(set(m['arena'] for m in matches if m['arena'])))

            output = {
                'matches': matches,
                'arenas': arenas,
                'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                'total_matches': len(matches)
            }

            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            print(f"💾 Сохранено в {OUTPUT_FILE}")
            print(f"📊 Матчей: {len(matches)} | Арен: {len(arenas)}")
            print("="*60)
            print("✅ ГОТОВО!")
            print("="*60)

        except Exception as e:
            print(f"❌ Ошибка: {e}")

            # Сохраняем debug информацию
            try:
                page.screenshot(path='error_screenshot.png', full_page=True)
                with open('error_page.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                print("📸 Сохранены error_screenshot.png и error_page.html")
            except:
                pass

            # Создаем пустой JSON
            try:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'matches': [],
                        'arenas': [],
                        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        'total_matches': 0,
                        'error': str(e)
                    }, f, ensure_ascii=False, indent=2)
                print("💾 Создан пустой JSON с ошибкой")
            except:
                pass
        finally:
            browser.close()


if __name__ == "__main__":
    main()
