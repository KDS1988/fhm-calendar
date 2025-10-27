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
    """Парсит матчи - ТОЧНАЯ КОПИЯ ОРИГИНАЛА"""
    matches = []

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

            logger.info("📝 Ввод логина и пароля...")
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск кнопки - КАК В ОРИГИНАЛЕ
            logger.info("🖱 Ищем кнопку входа...")
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

            # Переход на календарь
            logger.info("⏳ Загрузка vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')

            # ОЖИДАНИЕ ТАБЛИЦЫ - КАК В ОРИГИНАЛЕ
            logger.info("⏳ Ожидаем таблицу \'БЛИЖАЙШИЕ МАТЧИ\'...")
            page.wait_for_function("""
                () => {
                    const th = Array.from(document.querySelectorAll(\'th\'))
                        .find(el => el.textContent.includes(\'БЛИЖАЙШИЕ МАТЧИ\'));
                    if (!th) return false;
                    const table = th.closest(\'table\');
                    const rows = table.querySelectorAll(\'tr:has(td)\');
                    return rows.length > 0;
                }
            """, timeout=15000)

            # ПАРСИНГ ТАБЛИЦЫ - ТОЧНАЯ КОПИЯ XPATH
            logger.info("🔍 Парсим таблицу...")
            table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
            row_locators = table_locator.locator('tr:has(td)').all()

            logger.info(f"✅ Найдено строк: {len(row_locators)}")

            today = date.today()

            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                # Извлекаем данные - КАК В ОРИГИНАЛЕ
                day = texts[0] if len(texts) > 0 else ''
                date_str = texts[1] if len(texts) > 1 else ''
                tour = texts[2] if len(texts) > 2 else ''
                game_num = texts[3] if len(texts) > 3 else ''
                time_str = texts[4] if len(texts) > 4 else ''
                year = texts[5] if len(texts) > 5 else ''
                team1 = texts[6] if len(texts) > 6 else ''
                team2 = texts[7] if len(texts) > 7 else ''
                arena = texts[8] if len(texts) > 8 else ''
                # texts[9] - "На карте"
                address = texts[10] if len(texts) > 10 else ''

                # Проверка даты
                match_date = parse_date_str(date_str)
                if not match_date or match_date <= today:
                    continue

                # Формируем пару
                pair = f"{team1} – {team2}" if team1 and team2 else ""

                # Ссылка на карту
                map_link = ''
                try:
                    if len(cells) > 9:
                        link = cells[9].locator('a')
                        if link.count() > 0:
                            map_link = link.first.get_attribute('href') or ''
                except:
                    pass

                if not map_link:
                    map_link = 'https://yandex.ru/maps/'

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

            logger.info(f"✅ Спарсено {len(matches)} матчей")

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            page.screenshot(path='error_screenshot.png', full_page=True)
            with open('error_page.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            raise
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
    try:
        logger.info("=" * 60)
        logger.info("FHM Parser v5 - Точная копия оригинала")
        logger.info("=" * 60)

        matches = parse_matches()

        if not matches:
            logger.warning("⚠️ Матчи не найдены")
            save_to_json([])
            return

        save_to_json(matches)

        logger.info("=" * 60)
        logger.info("✅ Готово!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        try:
            save_to_json([])
        except:
            pass
        raise


if __name__ == '__main__':
    main()
