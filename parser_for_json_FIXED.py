#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FHM Parser - Enhanced version для GitHub Actions
С улучшенной обработкой сессий и cookies
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import date, datetime, timedelta
import json
import os

# === Настройки ===
LOGIN_URL = 'http://referee.fhmoscow.com/adm/index.php'
TARGET_URL = 'http://referee.fhmoscow.com/adm/vsporte.php'
LOGIN = os.getenv('FHMO_LOGIN')
PASSWORD = os.getenv('FHMO_PASS')
OUTPUT_FILE = 'matches_data.json'

if not LOGIN or not PASSWORD:
    raise EnvironmentError("❌ FHMO_LOGIN и FHMO_PASS обязательны!")


def parse_date_str(date_str):
    """Парсит строку вида 1.10.2025 или 01.10.2025"""
    try:
        d, m, y = map(int, str(date_str).strip().split('.'))
        return date(y, m, d)
    except:
        return None


def main():
    with sync_playwright() as p:
        print("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
            # ИСПРАВЛЕНО: правильный синтаксис fill()
            page.locator('input[name="login"]').fill(LOGIN)
            page.locator('input[name="password"]').fill(PASSWORD)
            
            # Поиск кнопки
            print("🖱 Пытаемся найти кнопку входа...")
            button_clicked = False
            selectors = [
                'input[type="submit"]',
                'input[value="Войти"]',
                'button[type="submit"]',
                'button:has-text("Войти")',
                'button:has-text("Вход")',
                'form button',
                'button >> text="Войти"',
                '//input[@type="submit"]',
                '//button[contains(text(), "Войти")]',
                '//button[contains(text(), "Вход")]',
                '//button[@type="submit"]',
                '//form//button',
            ]
            
            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    count = locator.count()
                    for i in range(count):
                        if locator.nth(i).is_visible():
                            locator.nth(i).click()
                            print(f"✅ Кнопка найдена и нажата: {selector}")
                            button_clicked = True
                            break
                    if button_clicked:
                        break
                except Exception as e:
                    continue
            
            if not button_clicked:
                print("❌ Кнопка входа не найдена")
                page.screenshot(path="login_page_error.png")
                raise Exception("Кнопка входа не найдена")
            
            page.wait_for_timeout(2000)
            
            print("⏳ Переходим на vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')
            
            # Ожидание таблицы
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
            
            # Парсинг
            data = []
            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue
                
                texts = [cell.inner_text().strip() for cell in cells]
                pair = " – ".join(filter(None, [texts[6], texts[7]])) if len(texts) > 7 else ""
                full_row = texts[:6] + [pair] + texts[8:11]
                
                while len(full_row) < 10:
                    full_row.append("")
                
                data.append(full_row)
            
            print(f"📋 Всего строк: {len(data)}")
            
            # Фильтрация
            today = date.today()
            filtered_data = []
            
            for row in data:
                date_str = row[1]
                match_date = parse_date_str(date_str)
                
                if match_date and match_date > today:
                    filtered_data.append(row)
            
            print(f"✅ Отобрано {len(filtered_data)} матчей (дата > {today.strftime('%d.%m.%Y')})")
            
            # Конвертация в JSON
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
                    'arena': row[7] if row[7] else '',
                    'map': row[8] if row[8] else 'https://yandex.ru/maps/',
                    'address': row[9] if len(row) > 9 else ''
                }
                matches.append(match)
            
            # Арены
            arenas = sorted(list(set(m['arena'] for m in matches if m['arena'])))
            
            # Формируем JSON
            output = {
                'matches': matches,
                'arenas': arenas,
                'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                'total_matches': len(matches)
            }
            
            # Сохраняем
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
            
            try:
                page.screenshot(path="error_screenshot.png")
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
            except:
                pass
        finally:
            browser.close()


if __name__ == "__main__":
    main()
