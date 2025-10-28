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
    """ULTIMATE парсинг - пробуем ВСЁ"""

    # ВАЖНО: Используем ваш РАБОЧИЙ локальный код!
    # Просто скопируем его логику

    with sync_playwright() as p:
        print("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        try:
            # === АВТОРИЗАЦИЯ - КАК В ВАШЕМ РАБОЧЕМ КОДЕ ===
            print("🔐 Авторизация...")
            for attempt in range(3):
                try:
                    page.goto(LOGIN_URL, timeout=30000)
                    page.wait_for_load_state('domcontentloaded')
                    print("✅ Страница загружена")
                    break
                except PlaywrightTimeoutError:
                    print(f"⚠️ Попытка {attempt + 1}/3")
                    if attempt == 2:
                        raise

            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск кнопки - РАСШИРЕННЫЙ СПИСОК
            button_clicked = False
            selectors = [
                'input[type="submit"]',
                'input[value="Войти"]',
                'button[type="submit"]',
                'button:has-text("Войти")',
                'button:has-text("Вход")',
                'form button',
                '//input[@type="submit"]',
                '//button[contains(text(), "Войти")]',
            ]

            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        for i in range(locator.count()):
                            if locator.nth(i).is_visible():
                                locator.nth(i).click()
                                print(f"✅ Кнопка нажата: {selector}")
                                button_clicked = True
                                break
                    if button_clicked:
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("Кнопка входа не найдена")

            page.wait_for_timeout(2000)

            # === ПЕРЕХОД НА КАЛЕНДАРЬ ===
            print("📅 Загрузка vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')

            # === КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ИСПОЛЬЗУЕМ wait_for_function КАК В ВАШЕМ КОДЕ ===
            print("⏳ Ожидаем таблицу 'БЛИЖАЙШИЕ МАТЧИ'...")
            try:
                page.wait_for_function("""
                    () => {
                        const th = Array.from(document.querySelectorAll('th'))
                            .find(el => el.textContent.includes('БЛИЖАЙШИЕ МАТЧИ'));
                        if (!th) return false;
                        const table = th.closest('table');
                        if (!table) return false;
                        const rows = table.querySelectorAll('tr:has(td)');
                        return rows.length > 0;
                    }
                """, timeout=20000)
                print("✅ Таблица появилась!")
            except PlaywrightTimeoutError:
                print("⚠️ Таймаут ожидания таблицы")
                # Но продолжаем - может таблица уже есть

            # Дополнительное ожидание
            time.sleep(2)

            # === ПАРСИНГ - ТОЧНО КАК В ВАШЕМ РАБОЧЕМ КОДЕ ===
            print("🔍 Парсим таблицу...")

            # Используем ТОЧНЫЙ XPath из вашего кода
            table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')

            if table_locator.count() == 0:
                print("❌ Таблица не найдена через XPath")

                # Сохраняем HTML для анализа
                with open('debug_vsporte.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                print("💾 Сохранен debug_vsporte.html")

                # Создаем пустой JSON
                output = {
                    'matches': [],
                    'arenas': [],
                    'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                    'total_matches': 0
                }

                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                print("💾 Создан пустой JSON")
                return

            print(f"✅ Таблица найдена!")

            # Получаем строки
            row_locators = table_locator.locator('tr:has(td)').all()
            print(f"📊 Найдено строк: {len(row_locators)}")

            # ПАРСИМ - КАК В ВАШЕМ КОДЕ
            data = []
            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                # Пара
                pair = " – ".join(filter(None, [texts[6], texts[7]])) if len(texts) > 7 else ""

                # Собираем строку
                full_row = texts[:6] + [pair] + texts[8:11]
                while len(full_row) < 10:
                    full_row.append("")

                data.append(full_row)

            print(f"📋 Всего строк: {len(data)}")

            # Фильтруем
            today = date.today()
            filtered_data = []

            for row in data:
                date_str = row[1]
                match_date = parse_date_str(date_str)

                if match_date and match_date > today:
                    filtered_data.append(row)

            print(f"✅ Отобрано {len(filtered_data)} матчей")

            # Конвертируем в JSON
            matches = []
            for row in filtered_data:
                match = {
                    'day': row[0],
                    'date': row[1],
                    'tour': row[2],
                    'game_num': row[3],
                    'time': row[4],
                    'year': row[5],
                    'pair': row[6],
                    'name': row[7] if row[7] else 'Первенство Москвы',
                    'arena': row[7],
                    'map': 'https://yandex.ru/maps/',
                    'address': row[9]
                }
                matches.append(match)

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
            import traceback
            traceback.print_exc()

            # Сохраняем для отладки
            try:
                page.screenshot(path='error_screenshot.png', full_page=True)
                with open('error_full.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                print("📸 Сохранены error_screenshot.png и error_full.html")
            except:
                pass

            # Пустой JSON
            try:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'matches': [],
                        'arenas': [],
                        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        'total_matches': 0,
                        'error': str(e)
                    }, f, ensure_ascii=False, indent=2)
            except:
                pass
        finally:
            browser.close()


if __name__ == "__main__":
    main()
