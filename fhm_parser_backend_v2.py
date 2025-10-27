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

# Проверка переменных окружения
if not LOGIN or not PASSWORD:
    raise EnvironmentError("❌ Переменные FHMO_LOGIN и FHMO_PASS должны быть заданы!")


def parse_date_str(date_str):
    """
    Парсит строку даты в формате DD.MM.YYYY или D.M.YYYY

    Args:
        date_str: Строка даты

    Returns:
        Объект date или None при ошибке
    """
    try:
        d, m, y = map(int, str(date_str).strip().split('.'))
        return date(y, m, d)
    except:
        return None


def parse_matches():
    """
    Парсит календарь матчей с сайта FHM

    Returns:
        list: Список матчей в формате словарей
    """
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
            logger.info("🔐 Авторизация на сайте...")
            for attempt in range(3):
                try:
                    page.goto(LOGIN_URL, timeout=30000)
                    page.wait_for_load_state('domcontentloaded')
                    break
                except PlaywrightTimeoutError:
                    logger.warning(f"⚠️ Попытка {attempt + 1}/3")
                    if attempt == 2:
                        raise Exception("Не удалось загрузить страницу после 3 попыток")

            # Заполнение формы
            page.fill('input[name="login"]', LOGIN)
            page.fill('input[name="password"]', PASSWORD)

            # Поиск и клик по кнопке входа
            selectors = [
                'input[type="submit"]',
                'input[value="Войти"]',
                'button[type="submit"]',
                'button:has-text("Войти")',
                'form button'
            ]

            button_clicked = False
            for selector in selectors:
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0 and locator.first.is_visible():
                        locator.first.click()
                        logger.info(f"✅ Вход выполнен")
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("❌ Не удалось найти кнопку входа")

            page.wait_for_timeout(2000)

            # Переход на страницу календаря
            logger.info("📅 Загружаем календарь...")
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(3000)  # Увеличиваем ожидание

            # УЛУЧШЕННАЯ ЛОГИКА: Попробуем разные способы найти таблицу
            table_locator = None

            # Способ 1: Ищем по тексту заголовка
            try:
                logger.info("🔍 Попытка 1: Поиск по заголовку 'БЛИЖАЙШИЕ МАТЧИ'...")
                table_locator = page.locator('th:has-text("БЛИЖАЙШИЕ МАТЧИ")').locator('xpath=ancestor::table').first
                if table_locator.count() > 0:
                    logger.info("✅ Таблица найдена (способ 1)")
            except:
                logger.warning("⚠️ Способ 1 не сработал")

            # Способ 2: Ищем таблицу с классом или id (если есть)
            if not table_locator or table_locator.count() == 0:
                try:
                    logger.info("🔍 Попытка 2: Поиск всех таблиц...")
                    # Берем все таблицы и ищем ту, что содержит нужные данные
                    tables = page.locator('table').all()
                    for i, table in enumerate(tables):
                        try:
                            # Проверяем, есть ли в таблице текст "БЛИЖАЙШИЕ" или заголовки колонок
                            text = table.inner_text()
                            if 'БЛИЖАЙШИЕ' in text or 'День' in text:
                                table_locator = page.locator(f'table').nth(i)
                                logger.info(f"✅ Таблица найдена (способ 2, индекс {i})")
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Способ 2 не сработал: {e}")

            # Способ 3: Берем последнюю большую таблицу на странице
            if not table_locator or table_locator.count() == 0:
                try:
                    logger.info("🔍 Попытка 3: Берем самую большую таблицу...")
                    tables = page.locator('table').all()
                    max_rows = 0
                    max_index = 0
                    for i, table in enumerate(tables):
                        try:
                            rows = table.locator('tr').count()
                            if rows > max_rows:
                                max_rows = rows
                                max_index = i
                        except:
                            continue

                    if max_rows > 5:  # Минимум 5 строк
                        table_locator = page.locator('table').nth(max_index)
                        logger.info(f"✅ Таблица найдена (способ 3, {max_rows} строк)")
                except Exception as e:
                    logger.warning(f"⚠️ Способ 3 не сработал: {e}")

            if not table_locator or table_locator.count() == 0:
                # Сохраняем скриншот и HTML для отладки
                page.screenshot(path='debug_screenshot.png')
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                logger.error("❌ Не удалось найти таблицу с матчами")
                logger.info("💾 Сохранены debug_screenshot.png и debug_page.html для отладки")
                raise Exception("Таблица с матчами не найдена")

            # Парсинг строк таблицы
            row_locators = table_locator.locator('tr:has(td)').all()
            logger.info(f"🔍 Найдено строк в таблице: {len(row_locators)}")

            if len(row_locators) == 0:
                logger.warning("⚠️ Таблица найдена, но строк с данными нет")
                # Попробуем все tr без фильтра
                row_locators = table_locator.locator('tr').all()
                logger.info(f"🔍 Всего строк (включая заголовки): {len(row_locators)}")

            for row in row_locators:
                cells = row.locator('td').all()
                if len(cells) < 8:
                    continue

                texts = [cell.inner_text().strip() for cell in cells]

                # Извлекаем команды
                team1 = texts[6].split('\n')[0] if len(texts) > 6 else ''
                team2 = texts[7].split('\n')[0] if len(texts) > 7 else ''
                pair = f"{team1} - {team2}" if team1 and team2 else ''

                # Извлекаем арену и адрес
                arena = texts[8] if len(texts) > 8 else ''
                address = texts[10] if len(texts) > 10 else ''

                # Пытаемся извлечь ссылку на карту
                map_link = ''
                try:
                    map_cell = cells[9] if len(cells) > 9 else None
                    if map_cell:
                        link = map_cell.locator('a')
                        if link.count() > 0:
                            map_link = link.first.get_attribute('href') or ''
                except:
                    pass

                # Формируем объект матча
                match = {
                    'day': texts[0] if len(texts) > 0 else '',
                    'date': texts[1] if len(texts) > 1 else '',
                    'tour': texts[2] if len(texts) > 2 else '',
                    'game_num': texts[3] if len(texts) > 3 else '',
                    'time': texts[4] if len(texts) > 4 else '',
                    'year': texts[5] if len(texts) > 5 else '',
                    'pair': pair,
                    'name': 'Первенство Москвы',
                    'arena': arena,
                    'map': map_link if map_link else 'https://yandex.ru/maps/',
                    'address': address
                }

                # Фильтр: только будущие матчи
                match_date = parse_date_str(match['date'])
                if match_date and match_date > date.today():
                    matches.append(match)

            logger.info(f"✅ Спарсено {len(matches)} будущих матчей")

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            try:
                page.screenshot(path='error_screenshot.png')
                logger.info("📸 Скриншот ошибки сохранен: error_screenshot.png")
                # Сохраняем HTML для отладки
                with open('error_page.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                logger.info("📄 HTML страницы сохранен: error_page.html")
            except:
                pass
            raise
        finally:
            browser.close()

    return matches


def save_to_json(matches, filename=OUTPUT_FILE):
    """
    Сохраняет данные матчей в JSON файл

    Args:
        matches: Список матчей
        filename: Имя файла для сохранения
    """
    # Извлекаем уникальные арены
    arenas = sorted(list(set(m['arena'] for m in matches if m['arena'])))

    data = {
        'matches': matches,
        'arenas': arenas,
        'last_update': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
        'total_matches': len(matches)
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 Данные сохранены в {filename}")
    logger.info(f"📊 Матчей: {len(matches)} | Арен: {len(arenas)}")

    # Показать пример первого матча
    if matches:
        logger.info("\n📋 Пример данных первого матча:")
        example = matches[0]
        logger.info(f"  День: {example['day']}")
        logger.info(f"  Дата: {example['date']}")
        logger.info(f"  Пара: {example['pair']}")
        logger.info(f"  Адрес: {example['address']}")


def main():
    """Основная функция"""
    try:
        logger.info("=" * 60)
        logger.info("FHM Calendar Parser - Запуск (улучшенная версия v3)")
        logger.info("=" * 60)

        # Парсинг
        matches = parse_matches()

        if not matches:
            logger.warning("⚠️ Не найдено матчей для сохранения")
            return

        # Сохранение
        save_to_json(matches)

        logger.info("=" * 60)
        logger.info("✅ Парсинг завершен успешно!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise


if __name__ == '__main__':
    main()
