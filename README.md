# FHM VSporte Parser - Веб-приложение

Веб-приложение для парсинга данных о матчах с сайта referee.fhmoscow.com/adm/vsporte.php

## 🚀 Быстрый старт

### Требования

- Python 3.9+
- Node.js (для разработки фронтенда, опционально)

### Установка

1. Клонируйте репозиторий:
```bash
git clone <your-repo-url>
cd fhm-vsporte-parser
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

4. Настройте переменные окружения:
```bash
cp .env.example .env
# Отредактируйте .env и укажите ваши логин/пароль
```

5. Запустите backend:
```bash
python app.py
```

API будет доступен по адресу: http://localhost:8000

6. Откройте frontend:
```bash
# Просто откройте файл frontend/index.html в браузере
# или используйте любой локальный веб-сервер
python -m http.server 3000
```

Frontend будет доступен по адресу: http://localhost:3000

## 📁 Структура проекта

```
fhm-vsporte-parser/
├── backend/
│   ├── app.py              # FastAPI приложение
│   ├── parser.py           # Модуль парсинга
│   ├── requirements.txt    # Python зависимости
│   └── data/              # Кешированные данные
├── frontend/
│   └── index.html         # Веб-интерфейс
├── .github/
│   └── workflows/
│       └── update-data.yml # GitHub Actions
├── .env.example           # Пример переменных окружения
└── README.md
```

## 🌐 Развертывание на GitHub Pages

### Backend (Railway/Render/Heroku)

1. Создайте аккаунт на Railway.app
2. Подключите ваш GitHub репозиторий
3. Railway автоматически определит Python проект
4. Добавьте переменные окружения FHMO_LOGIN и FHMO_PASS
5. Деплой произойдет автоматически

### Frontend (GitHub Pages)

1. Откройте Settings → Pages в вашем репозитории
2. Выберите ветку main и папку /frontend
3. Сохраните настройки
4. Сайт будет доступен по адресу: https://<username>.github.io/<repo-name>/

**Важно:** После развертывания backend обновите URL API в файле `frontend/index.html`:
```javascript
const API_URL = 'https://your-backend-url.railway.app';
```

## 📡 API Endpoints

### GET /api/matches
Получить список всех матчей
```bash
curl http://localhost:8000/api/matches
```

### POST /api/refresh
Принудительно обновить данные
```bash
curl -X POST http://localhost:8000/api/refresh
```

### GET /health
Проверка работоспособности
```bash
curl http://localhost:8000/health
```

## 🔄 Автоматическое обновление

GitHub Actions автоматически обновляет данные каждые 6 часов.

Для ручного запуска:
1. Перейдите в раздел Actions
2. Выберите workflow "Update Data"
3. Нажмите "Run workflow"

## 🛠 Разработка

### Локальная разработка backend:
```bash
cd backend
uvicorn app:app --reload --port 8000
```

### Локальная разработка frontend:
```bash
cd frontend
python -m http.server 3000
```

## 📝 Лицензия

MIT

## 👤 Автор

Дмитрий Корнеев
