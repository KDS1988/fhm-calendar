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
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# === Настройки ===
LOGIN_URL = 'http://referee.fhmoscow.com/adm/index.php'
TARGET_URL = 'http://referee.fhmoscow.com/adm/vsporte.php'
LOGIN = os.getenv('FHMO_LOGIN')
PASSWORD = os.getenv('FHMO_PASS')
OUTPUT_FILE = 'matches_data.json'

if not LOGIN or not PASSWORD:
    raise EnvironmentError("❌ Переменные FHMO_LOGIN и FHMO_PASS должны быть заданы!")


def parse_date_str(date_str):
    """Парсит строку даты"""
    try:
        # Убираем лишние пробелы и переносы строк
        date_str = str(date_str).strip().replace('\n', '')
        # Пробуем разные форматы
        for sep in ['.', '-', '/']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 3:
                    d, m, y = map(int, parts)
                    if y < 100:  # Двузначный год
                        y += 2000
                    return date(y, m, d)
    except:
        pass
    return None


def analyze_page_structure(page):
    """Анализирует структуру страницы для отладки"""
    logger.info("🔬 Анализируем структуру страницы...")

    try:
        # Ищем все таблицы
        tables = page.locator('table').all()
        logger.info(f"📊 Найдено таблиц на странице: {len(tables)}")

        for i, table in enumerate(tables):
            try:
                rows = table.locator('tr').count()
                cells_first_row = table.locator('tr').first.locator('td, th').count()
                logger.info(f"  Таблица {i+1}: {rows} строк, {cells_first_row} колонок в первой строке")

                # Пытаемся получить текст первой строки
                try:
                    first_row_text = table.locator('tr').first.inner_text()
                    logger.info(f"    Первая строка: {first_row_text[:100]}")
                except:
                    pass
            except:
                logger.warning(f"  Не удалось проанализировать таблицу {i+1}")

        # Проверяем наличие форм
        forms = page.locator('form').count()
        logger.info(f"📝 Найдено форм: {forms}")

        # Проверяем заголовки
        headers = page.locator('h1, h2, h3, h4').all()
        if headers:
            logger.info(f"📌 Заголовки на странице:")
            for h in headers[:5]:  # Первые 5
                try:
                    logger.info(f"  - {h.inner_text()[:50]}")
                except:
                    pass

    except Exception as e:
        logger.error(f"❌ Ошибка анализа структуры: {e}")


def parse_matches():
    """Парсит календарь матчей"""
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

            # Ищем кнопку входа
            for selector in ['input[type="submit"]', 'button[type="submit"]', 'input[value*="ход"]']:
                try:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        logger.info("✅ Вход выполнен")
                        break
                except:
                    continue

            page.wait_for_timeout(2000)

            # Переход на страницу календаря
            logger.info("📅 Загружаем календарь...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)  # Ждем полной загрузки
            page.wait_for_timeout(3000)

            # Сохраняем полный HTML для анализа
            html_content = page.content()
            with open('full_page.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info("💾 Сохранен full_page.html")

            # Анализируем структуру
            analyze_page_structure(page)

            # СТРАТЕГИЯ 1: Ищем все tr с td (строки данных)
            logger.info("🔍 Стратегия 1: Поиск всех строк с данными...")
            all_rows = page.locator('table tr:has(td)').all()
            logger.info(f"  Найдено потенциальных строк данных: {len(all_rows)}")

            # Фильтруем строки, которые похожи на матчи
            for row_idx, row in enumerate(all_rows):
                try:
                    cells = row.locator('td').all()
                    if len(cells) < 8:  # Минимум 8 колонок для матча
                        continue

                    texts = [cell.inner_text().strip() for cell in cells]

                    # Проверяем, похоже ли это на матч (есть дата в формате DD.MM.YYYY)
                    has_date = False
                    date_col_idx = -1
                    for i, text in enumerate(texts[:5]):  # Дата обычно в первых колонках
                        if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', text):
                            has_date = True
                            date_col_idx = i
                            logger.info(f"  ✓ Строка {row_idx}: найдена дата в колонке {i}: {text}")
                            break

                    if not has_date:
                        continue

                    # Пытаемся извлечь данные матча
                    # Адаптируемся к структуре: date_col_idx указывает где дата
                    match_data = {}

                    # Определяем колонки динамически
                    if date_col_idx == 0:  # Дата в первой колонке
                        match_data = {
                            'date': texts[0] if len(texts) > 0 else '',
                            'day': texts[1] if len(texts) > 1 else '',
                            'tour': texts[2] if len(texts) > 2 else '',
                            'game_num': texts[3] if len(texts) > 3 else '',
                            'time': texts[4] if len(texts) > 4 else '',
                            'year': texts[5] if len(texts) > 5 else '',
                            'team1': texts[6] if len(texts) > 6 else '',
                            'team2': texts[7] if len(texts) > 7 else '',
                            'arena': texts[8] if len(texts) > 8 else '',
                            'address': texts[10] if len(texts) > 10 else ''
                        }
                    elif date_col_idx == 1:  # День, потом дата
                        match_data = {
                            'day': texts[0] if len(texts) > 0 else '',
                            'date': texts[1] if len(texts) > 1 else '',
                            'tour': texts[2] if len(texts) > 2 else '',
                            'game_num': texts[3] if len(texts) > 3 else '',
                            'time': texts[4] if len(texts) > 4 else '',
                            'year': texts[5] if len(texts) > 5 else '',
                            'team1': texts[6] if len(texts) > 6 else '',
                            'team2': texts[7] if len(texts) > 7 else '',
                            'arena': texts[8] if len(texts) > 8 else '',
                            'address': texts[10] if len(texts) > 10 else ''
                        }

                    # Проверяем, что это будущий матч
                    match_date = parse_date_str(match_data['date'])
                    if not match_date or match_date <= date.today():
                        continue

                    # Формируем пару команд
                    pair = f"{match_data['team1']} - {match_data['team2']}"

                    # Финальный объект
                    match = {
                        'day': match_data['day'],
                        'date': match_data['date'],
                        'tour': match_data['tour'],
                        'game_num': match_data['game_num'],
                        'time': match_data['time'],
                        'year': match_data['year'],
                        'pair': pair,
                        'name': 'Первенство Москвы',
                        'arena': match_data['arena'],
                        'map': 'https://yandex.ru/maps/',
                        'address': match_data['address']
                    }

                    matches.append(match)
                    logger.info(f"  ✅ Добавлен матч: {pair} ({match_data['date']})")

                except Exception as e:
                    logger.debug(f"  Строка {row_idx} не подошла: {e}")
                    continue

            logger.info(f"✅ Спарсено {len(matches)} матчей")

            # Если ничего не нашли, сохраняем дополнительную информацию
            if len(matches) == 0:
                logger.warning("⚠️ Матчи не найдены, сохраняем детальную информацию...")
                page.screenshot(path='detailed_screenshot.png', full_page=True)
                logger.info("💾 Сохранен detailed_screenshot.png (полная страница)")

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
    """Сохраняет данные в JSON"""
    arenas = sorted(list(set(m['arena'] for m in matches if m['arena'])))

    data = {
        'matches': matches,
        'arenas': arenas,
        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
        'total_matches': len(matches)
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 Сохранено: {filename}")
    logger.info(f"📊 Матчей: {len(matches)} | Арен: {len(arenas)}")


def main():
    try:
        logger.info("=" * 60)
        logger.info("FHM Calendar Parser v4 - Адаптивная версия")
        logger.info("=" * 60)

        matches = parse_matches()

        if not matches:
            logger.error("❌ Матчи не найдены!")
            logger.info("📁 Проверьте файлы для отладки:")
            logger.info("  - full_page.html")
            logger.info("  - detailed_screenshot.png")
            # Не падаем, создаем пустой JSON
            save_to_json([])
            return

        save_to_json(matches)

        logger.info("=" * 60)
        logger.info("✅ Готово!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        # Создаем пустой JSON чтобы сайт не сломался
        try:
            save_to_json([])
        except:
            pass
        raise


if __name__ == '__main__':
    main()
