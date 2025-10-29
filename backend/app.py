from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import json
import os
from datetime import datetime
from parser import parse_vsporte

app = FastAPI(title="FHM VSporte Parser API")

# CORS настройки для доступа с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Путь к кешированным данным
DATA_FILE = "data/matches.json"
CACHE_HOURS = 1  # Обновлять кеш раз в час

def get_cached_data():
    """Получить данные из кеша или спарсить заново"""
    if os.path.exists(DATA_FILE):
        # Проверяем возраст файла
        file_age = datetime.now().timestamp() - os.path.getmtime(DATA_FILE)
        if file_age < CACHE_HOURS * 3600:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)

    # Парсим заново
    print("🔄 Обновляем данные...")
    data = parse_vsporte()

    # Сохраняем в кеш
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data

@app.get("/")
async def root():
    """Корневой endpoint с информацией об API"""
    return {
        "name": "FHM VSporte Parser API",
        "version": "1.0.0",
        "endpoints": {
            "/api/matches": "Получить все матчи",
            "/api/refresh": "Принудительно обновить данные",
            "/health": "Проверка работоспособности"
        }
    }

@app.get("/api/matches")
async def get_matches():
    """Получить список всех матчей"""
    try:
        data = get_cached_data()
        return {
            "success": True,
            "count": len(data),
            "data": data,
            "updated_at": datetime.fromtimestamp(
                os.path.getmtime(DATA_FILE)
            ).isoformat() if os.path.exists(DATA_FILE) else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh")
async def refresh_data():
    """Принудительно обновить данные"""
    try:
        # Удаляем кеш
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)

        # Парсим заново
        data = get_cached_data()

        return {
            "success": True,
            "message": "Данные успешно обновлены",
            "count": len(data),
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Проверка работоспособности API"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
