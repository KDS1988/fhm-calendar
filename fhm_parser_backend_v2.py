#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FHM Calendar Parser - Backend для веб-приложения (обновленная версия)
Парсит календарь матчей с referee.fhmoscow.com и сохраняет в JSON
"""
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
import logging
import json
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

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
    """ТОЧНАЯ КОПИЯ ОРИГИНАЛЬНОЙ ЛОГИКИ"""
    with sync_playwright() as p:
        logger.info("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            logger.info("🔐 Авторизация...")
            for attempt in range(3):
                try:
                    page.goto(LOGIN_URL, timeout=30000)
                    page.wait_for_load_state('domcontentloaded')
                    logger.info("✅ Страница загружена")
                    break
                except PlaywrightTimeoutError:
                    logger.warning(f"⚠️ Попытка {attempt + 1}/3")
                    if attempt == 2:
                        raise Exception("Не удалось загрузить страницу")

            logger.info("📝 Ввод логина/пароля...")
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск кнопки - ТОЧНО КАК В ОРИГИНАЛЕ
            logger.info("🖱 Поиск кнопки входа...")
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
                            logger.info(f"✅ Кнопка нажата: {selector}")
                            button_clicked = True
                            break
                    if button_clicked:
                        break
                except:
                    continue

            if not button_clicked:
                page.screenshot(path="login_error.png")
                raise Exception("Кнопка входа не найдена")

            page.wait_for_timeout(2000)

            logger.info("⏳ Загрузка vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')

            # Ждём таблицу - ТОЧНО КАК В ОРИГИНАЛЕ
            logger.info("⏳ Ожидаем таблицу 'БЛИЖАЙШИЕ МАТЧИ'...")
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

            # Получаем таблицу - ТОЧНЫЙ XPATH
            table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
            row_locators = table_locator.locator('tr:has(td)').all()

            logger.info(f"🔍 Найдено строк: {len(row_locators)}")

            # ПАРСИМ ВСЕ СТРОКИ (не фильтруем здесь!)
            data = []
            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                # Формируем пару - ТОЧНО КАК В ОРИГИНАЛЕ
                pair = " – ".join(filter(None, [texts[6], texts[7]])) if len(texts) > 7 else ""

                # full_row - ТОЧНАЯ СТРУКТУРА
                full_row = texts[:6] + [pair] + texts[8:11]
                while len(full_row) < 10:
                    full_row.append("")

                data.append(full_row)

            logger.info(f"📋 Всего строк: {len(data)}")

            # ФИЛЬТРАЦИЯ - КАК В ОРИГИНАЛЕ (после парсинга!)
            today = date.today()
            filtered_data = []

            for row in data:
                date_str = row[1]  # Дата во втором столбце
                match_date = parse_date_str(date_str)

                # ФИЛЬТР: только даты > today
                if match_date and match_date > today:
                    filtered_data.append(row)

            logger.info(f"✅ Отобрано {len(filtered_data)} матчей (дата > {today.strftime('%d.%m.%Y')})")

            # Конвертируем в JSON формат
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
                    'map': row[8] if row[8] else 'https://yandex.ru/maps/',
                    'address': row[9]
                }
                matches.append(match)

            # Извлекаем арены из пары (берем первую команду как примерное название арены)
            # На самом деле арена в текстах[8], но мы её не брали
            # Давайте добавим arena из исходных данных

            # ПЕРЕПАРСИМ с ареной
            matches_with_arena = []
            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                date_str = texts[1] if len(texts) > 1 else ''
                match_date = parse_date_str(date_str)

                if not match_date or match_date <= today:
                    continue

                pair = " – ".join(filter(None, [texts[6], texts[7]])) if len(texts) > 7 else ""
                arena = texts[8] if len(texts) > 8 else ''

                match = {
                    'day': texts[0] if len(texts) > 0 else '',
                    'date': date_str,
                    'tour': texts[2] if len(texts) > 2 else '',
                    'game_num': texts[3] if len(texts) > 3 else '',
                    'time': texts[4] if len(texts) > 4 else '',
                    'year': texts[5] if len(texts) > 5 else '',
                    'pair': pair,
                    'name': 'Первенство Москвы',
                    'arena': arena,
                    'map': 'https://yandex.ru/maps/',
                    'address': texts[10] if len(texts) > 10 else ''
                }
                matches_with_arena.append(match)

            # Сохраняем
            arenas = sorted(list(set(m['arena'] for m in matches_with_arena if m['arena'])))

            output = {
                'matches': matches_with_arena,
                'arenas': arenas,
                'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                'total_matches': len(matches_with_arena)
            }

            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            logger.info(f"💾 Сохранено в {OUTPUT_FILE}")
            logger.info(f"📊 Матчей: {len(matches_with_arena)} | Арен: {len(arenas)}")
            logger.info("="*60)
            logger.info("✅ ГОТОВО!")
            logger.info("="*60)

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            page.screenshot(path='error_screenshot.png')
            # Создаем пустой JSON чтобы сайт не сломался
            try:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'matches': [],
                        'arenas': [],
                        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        'total_matches': 0
                    }, f, ensure_ascii=False, indent=2)
                logger.info("💾 Создан пустой JSON")
            except:
                pass
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
