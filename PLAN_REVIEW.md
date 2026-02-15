# QA Resume Analyzer — разбор плана и приоритеты запуска MVP

## Что уже хорошо определено

- Чётко сформулирована цель продукта: скоринг QA-резюме под конкретную вакансию с explainability.
- Стек реалистичен для быстрого запуска MVP (FastAPI + Postgres + Celery + SSR на Jinja2).
- Выделены основные сущности данных (`User`, `Org`, `Job`, `Resume`, `Analysis`).
- Есть базовая формула оценки и понятная цветовая интерпретация.
- Учтены вопросы безопасности и мульти-тенантности (`org_id`).

## Критичные уточнения перед разработкой

1. **RBAC и роли**
   - Зафиксировать роли (`admin`, `recruiter`, `viewer`) и матрицу прав.
2. **Жизненный цикл анализа**
   - Статусы `Analysis`: `queued`, `processing`, `done`, `failed`.
3. **Схема `details_json`**
   - Нужен контракт API/Frontend: какие ключи обязательны, где хранить evidence.
4. **Повторные загрузки / дедуп**
   - Как обрабатывать одинаковый `text_hash` в рамках `org` и между разными вакансиями.
5. **Весовая модель**
   - Где живут веса (`global`, `org`, `job`) и кто может менять.
6. **Границы soft/sanity правил**
   - Добавить конфигурируемые пороги, чтобы уменьшить ложные срабатывания.

## Предложение по контракту `details_json` (MVP)

```json
{
  "hard": {
    "must_have": [{"skill": "python", "level": "used", "evidence": ["..."]}],
    "nice_to_have": [{"skill": "playwright", "level": "mention", "evidence": ["..."]}],
    "score": 78
  },
  "soft": {
    "grammar_issues": 3,
    "capslock_flags": 0,
    "aggressive_lexicon_flags": 0,
    "score": 92
  },
  "sanity": {
    "experience_vs_stack": [],
    "role_vs_responsibility": [],
    "date_overlaps": [{"period_a": "...", "period_b": "..."}],
    "keyword_stuffing": false,
    "score": 85
  },
  "penalties": [
    {"code": "DATE_OVERLAP", "value": 5, "reason": "..."}
  ]
}
```

## Рекомендуемые API endpoint'ы для MVP

- `POST /auth/login`
- `POST /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/resumes/upload`
- `POST /analyses/run` (или автозапуск после upload)
- `GET /jobs/{id}/analyses` (таблица + фильтры)
- `GET /analyses/{id}` (детализация)
- `GET /jobs/{id}/export.csv`

## План реализации MVP (итерации)

### Итерация 1 — каркас платформы
- FastAPI проект, миграции, модели SQLAlchemy.
- Аутентификация, `org_id`-изоляция.
- CRUD вакансии.

### Итерация 2 — загрузка и парсинг резюме
- Upload PDF/DOCX в S3-совместимое хранилище.
- Извлечение текста + `text_hash`.
- Очередь задач Celery/Redis.

### Итерация 3 — scoring pipeline
- Hard/Soft/Sanity scoring.
- Сохранение `Analysis` + `details_json`.
- Перерасчёт лейбла по порогам.

### Итерация 4 — UI и экспорт
- Таблица резюме (score, label, mini-bars, фильтры).
- Dropdown-детализация по категориям.
- Экспорт CSV.

## Риски и как снизить

- **Качество парсинга PDF/DOCX**: fallback-парсеры, лог ошибок по типам файлов.
- **Ложные срабатывания sanity/soft**: пороги и whitelist/blacklist-словарь.
- **Производительность**: все тяжёлые операции только в фоне; пагинация списка анализов.
- **Юридические риски по данным CV**: retention policy + минимум логирования PII.

## Definition of Done для MVP

- Пользователь логинится и создаёт вакансию.
- Загружает пакет резюме.
- Анализ выполняется асинхронно и отображается в таблице.
- Для каждого кандидата видны score, цвет, объяснение по категориям.
- CSV экспортирует итоговую таблицу.
