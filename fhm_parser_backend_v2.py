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
    """ФИНАЛЬНАЯ ВЕРСИЯ - с сохранением сессии"""
    with sync_playwright() as p:
        logger.info("🌐 Запускаем браузер...")

        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )

        # ВАЖНО: Один контекст для всех страниц (сохраняет cookies/сессию)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        )

        page = context.new_page()

        try:
            # ===== АВТОРИЗАЦИЯ =====
            logger.info("🔐 Переход на страницу входа...")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_load_state('networkidle')
            logger.info("✅ Страница входа загружена")

            logger.info("📝 Заполняем форму...")
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            logger.info("🖱 Клик по кнопке входа...")
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'form button']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        logger.info(f"✅ Кнопка нажата: {selector}")
                        break
                except:
                    continue

            # Ждем завершения авторизации
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass

            page.wait_for_timeout(3000)

            logger.info(f"📍 После входа: {page.url}")

            # ===== ПЕРЕХОД НА КАЛЕНДАРЬ (в том же контексте!) =====
            logger.info("📅 Переход на vsporte.php (сессия сохранена)...")

            # ВАРИАНТ 1: Через page.goto (сохраняет cookies)
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)
            page.wait_for_timeout(3000)

            logger.info(f"📍 На странице: {page.url}")

            # Сохраняем для отладки
            content = page.content()
            with open('vsporte_final.html', 'w', encoding='utf-8') as f:
                f.write(content)
            page.screenshot(path='vsporte_final.png', full_page=True)
            logger.info("💾 Сохранены vsporte_final.html и .png")

            # Проверка доступа
            if 'Вход' in content or 'content_user_login' in content:
                logger.error("❌ Сессия не сохранилась даже с одним контекстом!")
                logger.error("Возможно сайт требует дополнительных шагов авторизации")

                # Пробуем через клик по ссылке вместо goto
                logger.info("🔄 Пробуем альтернативный способ...")
                page.goto(LOGIN_URL, timeout=30000)
                page.fill('input[name="login"]', LOGIN)
                page.fill('input[name="password"]', PASSWORD)
                page.locator('input[type="submit"]').first.click()
                page.wait_for_load_state('networkidle', timeout=10000)

                # Теперь КЛИКАЕМ по ссылке на vsporte (если есть)
                try:
                    vsporte_link = page.locator('a[href*="vsporte"]')
                    if vsporte_link.count() > 0:
                        logger.info("🔗 Нашли ссылку на vsporte, кликаем...")
                        vsporte_link.first.click()
                        page.wait_for_load_state('networkidle', timeout=10000)
                        content = page.content()
                except:
                    pass

            # ===== ПАРСИНГ =====
            logger.info("🔍 Ищем таблицу...")

            table_locator = None
            try:
                table_locator = page.locator('//th[contains(., "БЛИЖАЙШИЕ МАТЧИ")]/ancestor::table')
                if table_locator.count() > 0:
                    logger.info("✅ Таблица найдена!")
                else:
                    logger.warning("⚠️ Таблица с 'БЛИЖАЙШИЕ МАТЧИ' не найдена")
            except Exception as e:
                logger.warning(f"⚠️ XPath ошибка: {e}")

            # Fallback
            if not table_locator or table_locator.count() == 0:
                logger.info("🔍 Ищем любые большие таблицы...")
                tables = page.locator('table').all()
                logger.info(f"  Всего таблиц: {len(tables)}")

                max_rows = 0
                best_table_idx = -1

                for i, table in enumerate(tables):
                    try:
                        rows = len(table.locator('tr').all())
                        if rows > max_rows and rows > 5:
                            max_rows = rows
                            best_table_idx = i
                            logger.info(f"  Таблица {i+1}: {rows} строк")
                    except:
                        pass

                if best_table_idx >= 0:
                    table_locator = page.locator('table').nth(best_table_idx)
                    logger.info(f"✅ Используем таблицу {best_table_idx+1} с {max_rows} строками")

            if not table_locator or table_locator.count() == 0:
                logger.error("❌ Таблица не найдена!")
                logger.info("📁 Проверьте vsporte_final.html")
                raise Exception("Таблица с матчами не найдена")

            # Парсим
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

            logger.info(f"✅ Итого спарсено: {len(matches)} матчей")

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
