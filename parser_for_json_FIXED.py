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
    """РАБОТАЮЩИЙ парсинг - ищем по классу!"""
    with sync_playwright() as p:
        print("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()
        
        try:
            # Авторизация
            print("🔐 Авторизация...")
            for attempt in range(3):
                try:
                    page.goto(LOGIN_URL, timeout=30000)
                    page.wait_for_load_state('domcontentloaded')
                    print("✅ Страница загружена")
                    break
                except PlaywrightTimeoutError:
                    if attempt == 2:
                        raise
            
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)
            
            # Клик
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'form button']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        print(f"✅ Кнопка нажата")
                        break
                except:
                    continue
            
            page.wait_for_timeout(2000)
            
            # Переход на календарь
            print("📅 Загрузка vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')
            
            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Ищем по классу tablesorter!
            print("⏳ Ожидаем таблицу с классом 'tablesorter'...")
            try:
                page.wait_for_selector('table.tablesorter', timeout=15000)
                print("✅ Таблица найдена!")
            except PlaywrightTimeoutError:
                print("⚠️ Таймаут ожидания, пробуем продолжить...")
            
            time.sleep(2)
            
            # Парсинг по классу
            print("🔍 Парсим таблицу...")
            table_locator = page.locator('table.tablesorter')
            
            if table_locator.count() == 0:
                print("❌ Таблица не найдена")
                # Пробуем без класса
                table_locator = page.locator('table')
                if table_locator.count() == 0:
                    raise Exception("Ни одной таблицы не найдено")
                print(f"⚠️ Используем первую таблицу (всего: {table_locator.count()})")
                table_locator = table_locator.first
            else:
                print(f"✅ Найдена table.tablesorter")
                table_locator = table_locator.first
            
            # Получаем строки
            row_locators = table_locator.locator('tr:has(td)').all()
            print(f"📊 Найдено строк: {len(row_locators)}")
            
            # Парсим
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
                    'arena': row[7] if row[7] else '',
                    'map': 'https://yandex.ru/maps/',
                    'address': row[9] if len(row) > 9 else ''
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
                page.screenshot(path='final_error.png', full_page=True)
                with open('final_error.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
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
