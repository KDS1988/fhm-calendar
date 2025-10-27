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
    """С ПРОВЕРКОЙ АВТОРИЗАЦИИ"""
    with sync_playwright() as p:
        logger.info("🌐 Запускаем браузер...")

        # ВАЖНО: Сохраняем cookies между страницами
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']  # Скрываем что мы бот
        )

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            accept_downloads=True,
            has_touch=False,
            is_mobile=False,
        )

        page = context.new_page()

        try:
            # ===== АВТОРИЗАЦИЯ =====
            logger.info("🔐 Переход на страницу входа...")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_load_state('networkidle')

            # Сохраняем начальную страницу
            with open('01_login_page.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            page.screenshot(path='01_login_page.png')
            logger.info("💾 Сохранены 01_login_page.html и .png")

            logger.info("📝 Заполняем форму...")
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Сохраняем перед кликом
            with open('02_before_submit.html', 'w', encoding='utf-8') as f:
                f.write(page.content())

            # Клик по кнопке
            logger.info("🖱 Клик по кнопке входа...")
            button_clicked = False
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'form button']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        logger.info(f"✅ Кнопка нажата: {selector}")
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("Кнопка входа не найдена")

            # ВАЖНО: Ждем навигации или сохранения cookies
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                logger.warning("⚠️ Таймаут networkidle, но продолжаем")

            page.wait_for_timeout(3000)

            # Сохраняем страницу после клика
            with open('03_after_submit.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            page.screenshot(path='03_after_submit.png')
            logger.info("💾 Сохранены 03_after_submit.html и .png")

            # ПРОВЕРКА: Успешна ли авторизация?
            current_url = page.url
            content = page.content()

            logger.info(f"📍 Текущий URL: {current_url}")

            # Признаки НЕ успешной авторизации
            if 'index.php' in current_url or 'Вход' in content or 'content_user_login' in content:
                logger.error("❌ АВТОРИЗАЦИЯ НЕ ПРОШЛА!")
                logger.error("Вернулись на страницу входа или получили ошибку")
                logger.info("📁 Проверьте файлы 01-03_*.html для анализа")
                logger.info("🔑 Проверьте правильность логина и пароля в GitHub Secrets")
                raise Exception("Авторизация не удалась - неправильные учетные данные?")

            logger.info("✅ Авторизация выглядит успешной")

            # ===== ПЕРЕХОД НА КАЛЕНДАРЬ =====
            logger.info("📅 Переход на vsporte.php...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)
            page.wait_for_timeout(3000)

            # Сохраняем страницу календаря
            with open('04_vsporte_page.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            page.screenshot(path='04_vsporte_page.png', full_page=True)
            logger.info("💾 Сохранены 04_vsporte_page.html и .png")

            # Проверяем что мы на правильной странице
            content = page.content()
            if 'Вход' in content or 'content_user_login' in content:
                logger.error("❌ На странице календаря требуется повторный вход!")
                logger.error("Возможно сессия не сохранилась")
                raise Exception("Не удалось получить доступ к календарю")

            # ===== ПАРСИНГ =====
            logger.info("🔍 Ищем таблицу...")

            table_locator = None
            try:
                table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
                if table_locator.count() > 0:
                    logger.info("✅ Таблица найдена!")
                else:
                    logger.warning("⚠️ Таблица не найдена по XPath")
            except Exception as e:
                logger.warning(f"⚠️ XPath ошибка: {e}")

            # Fallback - все таблицы
            if not table_locator or table_locator.count() == 0:
                logger.info("🔍 Ищем среди всех таблиц...")
                tables = page.locator('table').all()
                logger.info(f"  Всего таблиц: {len(tables)}")

                for i, table in enumerate(tables):
                    try:
                        rows = len(table.locator('tr').all())
                        if rows > 5:
                            table_locator = page.locator('table').nth(i)
                            logger.info(f"✅ Используем таблицу {i+1} с {rows} строками")
                            break
                    except:
                        pass

            if not table_locator or table_locator.count() == 0:
                logger.error("❌ Таблица не найдена!")
                raise Exception("Таблица с матчами не найдена")

            # Парсим строки
            row_locators = table_locator.locator('tr:has(td)').all()
            logger.info(f"📊 Найдено строк: {len(row_locators)}")

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
                        'name': 'Первенство Москвы',
                        'arena': texts[8] if len(texts) > 8 else '',
                        'map': 'https://yandex.ru/maps/',
                        'address': texts[10] if len(texts) > 10 else ''
                    }

                    matches.append(match)
                    logger.info(f"  ✅ {pair} ({date_str})")

                except Exception as e:
                    logger.debug(f"  Строка {idx}: {e}")

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
