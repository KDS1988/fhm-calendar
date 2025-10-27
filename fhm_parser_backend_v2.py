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
    """Парсит дату DD.MM.YYYY"""
    try:
        d, m, y = map(int, str(date_str).strip().split('.'))
        return date(y, m, d)
    except:
        return None


def main():
    """БЕЗ wait_for_function - прямой парсинг"""
    with sync_playwright() as p:
        logger.info("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            # Авторизация
            logger.info("🔐 Авторизация...")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')
            logger.info("✅ Страница входа загружена")

            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск кнопки
            button_clicked = False
            selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'form button',
                'input[value="Войти"]',
                '//input[@type="submit"]',
            ]

            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        if locator.first.is_visible():
                            locator.first.click()
                            logger.info(f"✅ Кнопка нажата: {selector}")
                            button_clicked = True
                            break
                except:
                    continue

            if not button_clicked:
                page.screenshot(path="login_error.png")
                raise Exception("Кнопка входа не найдена")

            page.wait_for_timeout(2000)

            # Переход на календарь
            logger.info("📅 Загрузка vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)  # Ждем ПОЛНУЮ загрузку
            logger.info("✅ Страница календаря загружена")

            # Дополнительное ожидание
            page.wait_for_timeout(5000)  # 5 секунд на всякий случай

            # Сохраняем HTML для анализа
            html_content = page.content()
            with open('vsporte_page.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            page.screenshot(path='vsporte_screenshot.png', full_page=True)
            logger.info("💾 Сохранены vsporte_page.html и vsporte_screenshot.png")

            # ПАРСИНГ БЕЗ ОЖИДАНИЯ - сразу пытаемся найти таблицу
            logger.info("🔍 Ищем таблицу (без wait_for_function)...")

            # Пробуем XPath
            table_locator = None
            try:
                table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
                if table_locator.count() > 0:
                    logger.info("✅ Таблица найдена через XPath")
                else:
                    logger.warning("⚠️ XPath не нашел таблицу")
                    table_locator = None
            except Exception as e:
                logger.warning(f"⚠️ XPath ошибка: {e}")

            # Если не нашли - ищем любые таблицы
            if not table_locator or table_locator.count() == 0:
                logger.info("🔍 Ищем любые таблицы на странице...")
                tables = page.locator('table').all()
                logger.info(f"  Найдено таблиц: {len(tables)}")

                for i, table in enumerate(tables):
                    try:
                        text = table.inner_text()
                        rows = len(table.locator('tr').all())
                        logger.info(f"  Таблица {i+1}: {rows} строк, содержит текст: {text[:100]}")

                        # Ищем таблицу с "БЛИЖАЙШ" или просто большую
                        if 'БЛИЖАЙШ' in text or 'МАТЧ' in text or rows > 10:
                            table_locator = page.locator('table').nth(i)
                            logger.info(f"✅ Используем таблицу {i+1}")
                            break
                    except Exception as e:
                        logger.debug(f"  Таблица {i+1}: ошибка {e}")

            if not table_locator or table_locator.count() == 0:
                logger.error("❌ Таблица не найдена!")
                logger.info("📁 Проверьте vsporte_page.html и vsporte_screenshot.png")
                raise Exception("Таблица с матчами не найдена")

            # ПАРСИНГ СТРОК
            row_locators = table_locator.locator('tr:has(td)').all()
            logger.info(f"📊 Найдено строк: {len(row_locators)}")

            if len(row_locators) == 0:
                logger.warning("⚠️ Таблица пустая!")
                # Пробуем все tr без фильтра
                row_locators = table_locator.locator('tr').all()
                logger.info(f"  Всего строк в таблице: {len(row_locators)}")

            today = date.today()
            matches = []

            for idx, row in enumerate(row_locators):
                try:
                    cells = row.locator('td').all()
                    if len(cells) < 8:
                        logger.debug(f"  Строка {idx}: мало ячеек ({len(cells)})")
                        continue

                    texts = [cell.inner_text().strip() for cell in cells]

                    # Извлекаем данные
                    day = texts[0] if len(texts) > 0 else ''
                    date_str = texts[1] if len(texts) > 1 else ''
                    tour = texts[2] if len(texts) > 2 else ''
                    game_num = texts[3] if len(texts) > 3 else ''
                    time_str = texts[4] if len(texts) > 4 else ''
                    year = texts[5] if len(texts) > 5 else ''
                    team1 = texts[6].split('\n')[0] if len(texts) > 6 else ''
                    team2 = texts[7].split('\n')[0] if len(texts) > 7 else ''
                    arena = texts[8] if len(texts) > 8 else ''
                    address = texts[10] if len(texts) > 10 else ''

                    # Проверка даты
                    match_date = parse_date_str(date_str)
                    if not match_date:
                        logger.debug(f"  Строка {idx}: некорректная дата '{date_str}'")
                        continue

                    if match_date <= today:
                        logger.debug(f"  Строка {idx}: старая дата {date_str}")
                        continue

                    # Пара
                    pair = f"{team1} – {team2}" if team1 and team2 else ""

                    match = {
                        'day': day,
                        'date': date_str,
                        'tour': tour,
                        'game_num': game_num,
                        'time': time_str,
                        'year': year,
                        'pair': pair,
                        'name': 'Первенство Москвы',
                        'arena': arena,
                        'map': 'https://yandex.ru/maps/',
                        'address': address
                    }

                    matches.append(match)
                    logger.info(f"  ✅ Строка {idx}: {pair} ({date_str})")

                except Exception as e:
                    logger.debug(f"  Строка {idx}: ошибка {e}")

            logger.info(f"✅ Спарсено {len(matches)} матчей")

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

            logger.info(f"💾 Сохранено в {OUTPUT_FILE}")
            logger.info(f"📊 Матчей: {len(matches)} | Арен: {len(arenas)}")
            logger.info("="*60)
            logger.info("✅ ГОТОВО!")
            logger.info("="*60)

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            page.screenshot(path='fatal_error.png', full_page=True)
            # Создаем пустой JSON
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
        finally:
            browser.close()


if __name__ == "__main__":
    main()
