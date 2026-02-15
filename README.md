# QA Resume Analyzer MVP (v0)

MVP web-приложение для рекрутеров:
- авторизация,
- создание вакансии (название + файл описания PDF/DOCX),
- загрузка резюме,
- фоновый анализ,
- таблица результатов + детализация,
- экспорт CSV.

## Стек
- FastAPI
- SQLAlchemy
- Jinja2 + Tailwind CDN
- SQLite (для демо v0)

## Запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открыть: http://127.0.0.1:8000

## Примечания
- Ограничение upload: 5 MB.
- Описание вакансии: только `.pdf` или `.docx` (без ручного JSON-блока настроек в форме).
- Резюме: `.pdf`, `.docx`, `.txt`.
- Полный текст резюме в БД не хранится.
- Дедуп реализован через `text_hash` (пока без блокировки дублей).
