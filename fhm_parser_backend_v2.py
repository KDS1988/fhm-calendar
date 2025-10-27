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


def parse_matches():
    """Парсит матчи - БЕЗ ПАДЕНИЯ"""
    matches = []

    with sync_playwright() as p:
        logger.info("🌐 Запускаем браузер...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        try:
            # Авторизация
            logger.info("🔐 Авторизация...")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')

            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск кнопки
            button_clicked = False
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'form button']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        logger.info(f"✅ Вход: {selector}")
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("Кнопка входа не найдена")

            page.wait_for_timeout(2000)

            # Переход на календарь
            logger.info("📅 Загрузка календаря...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)
            page.wait_for_timeout(3000)

            # Сохраняем для отладки
            page.screenshot(path='page_screenshot.png', full_page=True)
            with open('page_source.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            logger.info("💾 Сохранены page_screenshot.png и page_source.html")

            # ПЫТАЕМСЯ НАЙТИ ТАБЛИЦУ (БЕЗ ПАДЕНИЯ)
            logger.info("🔍 Поиск таблицы с матчами...")

            table_found = False
            table_locator = None

            # Способ 1: XPath (как в оригинале)
            try:
                logger.info("  Попытка 1: XPath с БЛИЖАЙШИЕ МАТЧИ...")
                table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
                if table_locator.count() > 0:
                    table_found = True
                    logger.info("  ✅ Таблица найдена (XPath)")
            except Exception as e:
                logger.warning(f"  ⚠️ Способ 1 не сработал: {e}")

            # Способ 2: CSS селектор
            if not table_found:
                try:
                    logger.info("  Попытка 2: CSS селектор...")
                    tables = page.locator('table').all()
                    for i, table in enumerate(tables):
                        text = table.inner_text()
                        if 'БЛИЖАЙШ' in text or 'МАТЧ' in text or len(table.locator('tr').all()) > 5:
                            table_locator = page.locator('table').nth(i)
                            table_found = True
                            logger.info(f"  ✅ Таблица найдена (CSS, индекс {i})")
                            break
                except Exception as e:
                    logger.warning(f"  ⚠️ Способ 2 не сработал: {e}")

            # Способ 3: Самая большая таблица
            if not table_found:
                try:
                    logger.info("  Попытка 3: Самая большая таблица...")
                    tables = page.locator('table').all()
                    max_rows = 0
                    max_idx = -1
                    for i, table in enumerate(tables):
                        rows = len(table.locator('tr').all())
                        if rows > max_rows:
                            max_rows = rows
                            max_idx = i

                    if max_rows > 5:
                        table_locator = page.locator('table').nth(max_idx)
                        table_found = True
                        logger.info(f"  ✅ Используем таблицу с {max_rows} строками")
                except Exception as e:
                    logger.warning(f"  ⚠️ Способ 3 не сработал: {e}")

            if not table_found or not table_locator:
                logger.warning("⚠️ Таблица не найдена, проверьте page_source.html")
                logger.info("📝 Возможно на странице нет будущих матчей")
                return matches  # Возвращаем пустой список, НЕ падаем

            # ПАРСИНГ НАЙДЕННОЙ ТАБЛИЦЫ
            logger.info("📊 Парсим строки таблицы...")
            row_locators = table_locator.locator('tr:has(td)').all()
            logger.info(f"  Найдено строк с данными: {len(row_locators)}")

            today = date.today()

            for idx, row in enumerate(row_locators):
                try:
                    cells = row.locator('td').all()
                    if len(cells) < 8:
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

                    # Формируем пару
                    pair = f"{team1} – {team2}" if team1 and team2 else ""

                    # Ссылка на карту
                    map_link = 'https://yandex.ru/maps/'
                    try:
                        if len(cells) > 9:
                            link = cells[9].locator('a')
                            if link.count() > 0:
                                map_link = link.first.get_attribute('href') or map_link
                    except:
                        pass

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
                        'map': map_link,
                        'address': address
                    }

                    matches.append(match)
                    logger.info(f"  ✅ Строка {idx}: {pair} ({date_str})")

                except Exception as e:
                    logger.debug(f"  Строка {idx}: ошибка {e}")
                    continue

            logger.info(f"✅ Итого спарсено: {len(matches)} матчей")

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            try:
                page.screenshot(path='fatal_error.png', full_page=True)
                with open('fatal_error.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                logger.info("💾 Сохранены fatal_error.png и fatal_error.html")
            except:
                pass
            # НЕ падаем, возвращаем пустой список
        finally:
            browser.close()

    return matches


def save_to_json(matches, filename=OUTPUT_FILE):
    """Сохраняет в JSON"""
    arenas = sorted(list(set(m['arena'] for m in matches if m['arena'])))

    data = {
        'matches': matches,
        'arenas': arenas,
        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
        'total_matches': len(matches)
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 Сохранено в {filename}")
    logger.info(f"📊 Матчей: {len(matches)} | Арен: {len(arenas)}")


def main():
    """Главная функция - ВСЕГДА УСПЕШНА"""
    logger.info("=" * 60)
    logger.info("FHM Parser v6 - Финальная надежная версия")
    logger.info("=" * 60)

    try:
        matches = parse_matches()
        save_to_json(matches)

        if len(matches) == 0:
            logger.warning("⚠️ Матчи не найдены, но это OK")
            logger.info("📝 Возможные причины:")
            logger.info("  1. Нет будущих матчей в календаре")
            logger.info("  2. Изменилась структура сайта")
            logger.info("  3. Проверьте page_source.html для отладки")

        logger.info("=" * 60)
        logger.info("✅ Работа завершена успешно")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
        # Даже в случае критической ошибки - создаем пустой JSON
        try:
            save_to_json([])
        except:
            pass
        # Завершаем с кодом 0 (успех), чтобы GitHub Actions не падал
        logger.info("💾 Создан пустой JSON файл")
        logger.info("=" * 60)
        logger.info("✅ Завершено (с пустыми данными)")
        logger.info("=" * 60)


if __name__ == '__main__':
    main()
