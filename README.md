# Serv01

Serv01 — основа SaaS-платформы для настройки и мониторинга задач поиска и обработки
сайтов. Первая версия реализует защищённый API управления пользователями, профилями
данных и жизненным циклом задач. Интерактивная документация доступна в Swagger UI.

## Что уже работает

- регистрация и вход по JWT; пароли хешируются Argon2;
- изоляция задач и шаблонов между пользователями;
- создание, просмотр, редактирование, удаление и клонирование задач;
- переходы задач `draft → running → paused/stopped` с проверкой допустимости;
- параметры поиска, действия, лимиты, одноразовый или cron-запуск;
- CRUD шаблонов данных для заполнения форм;
- аудит действий и API для сайтов, отправок, логов и агрегированной статистики;
- SQLite для локального запуска и PostgreSQL через Docker Compose;
- проверки Ruff, mypy и pytest в GitHub Actions.

Поисковые провайдеры, очередь воркеров, браузерная автоматизация, captcha/payment
интеграции, веб-кабинет и экспорт отчётов — следующие независимые этапы. Текущий API
сохраняет конфигурацию и состояние задач, но не выполняет действия на внешних сайтах.
Такое разделение позволяет подключить воркеры через очередь без смешивания их прав и
ресурсов с публичным API.

Используйте автоматизацию только на ресурсах, где у вас есть явное разрешение.
Параметр `respect_robots_txt` включён по умолчанию; будущие воркеры должны соблюдать
его и заданные ограничения скорости. Обход защит и скрытая массовая отправка не входят
в эту реализацию.

## Быстрый старт

Требуется Python 3.12 или новее.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
.venv/bin/uvicorn serv01.main:app --reload
```

После запуска:

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI: <http://localhost:8000/openapi.json>
- проверка состояния: <http://localhost:8000/health>

Для запуска API вместе с PostgreSQL:

```bash
SERV01_JWT_SECRET="$(openssl rand -hex 32)" docker compose up --build
```

Compose предназначен для локальной проверки. Перед production-развёртыванием нужно
передать секреты через менеджер секретов, настроить TLS и постоянные резервные копии.

## Пример API

Регистрация возвращает bearer-токен:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "owner@example.com",
    "password": "correct horse battery staple",
    "full_name": "Task Owner"
  }'
```

Создание задачи (подставьте токен в `TOKEN`):

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Поиск партнёров",
    "keywords": ["поставщики оборудования"],
    "search_engine": "google",
    "search_depth": 10,
    "action_type": "crawl",
    "max_sites": 25,
    "respect_robots_txt": true
  }'
```

Основные маршруты:

| Метод | Маршрут | Назначение |
| --- | --- | --- |
| `POST` | `/api/auth/register`, `/api/auth/login` | регистрация и вход |
| `GET` | `/api/auth/me` | текущий пользователь |
| `GET/POST` | `/api/tasks` | список и создание задач |
| `GET/PATCH/DELETE` | `/api/tasks/{id}` | управление задачей |
| `POST` | `/api/tasks/{id}/start` | запуск или продолжение |
| `POST` | `/api/tasks/{id}/pause` | пауза |
| `POST` | `/api/tasks/{id}/stop` | остановка |
| `POST` | `/api/tasks/{id}/clone` | клонирование |
| `GET/POST` | `/api/templates` | список и создание шаблонов |
| `GET/PATCH/DELETE` | `/api/templates/{id}` | управление шаблоном |
| `GET` | `/api/sites`, `/api/submissions` | результаты воркеров |
| `GET` | `/api/logs`, `/api/stats` | аудит и статистика |

Для `/api/sites`, `/api/submissions`, `/api/logs` и `/api/stats` можно передать
`task_id`. API проверяет, что задача принадлежит текущему пользователю.

## Конфигурация

Настройки читаются из переменных окружения с префиксом `SERV01_` и из `.env`:

| Переменная | Значение по умолчанию |
| --- | --- |
| `SERV01_DATABASE_URL` | `sqlite+pysqlite:///./serv01.db` |
| `SERV01_JWT_SECRET` | только небезопасное значение для разработки |
| `SERV01_ACCESS_TOKEN_MINUTES` | `60` |
| `SERV01_CORS_ORIGINS` | локальные порты 3000 и 5173 |
| `SERV01_ENVIRONMENT` | `development` |

В режиме `production` приложение откажется запускаться с development-секретом.

## Разработка и проверки

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest -q
```

Тесты используют отдельную in-memory SQLite базу и проверяют API через HTTP. Схема
создаётся при старте приложения. До изменения существующей production-схемы следует
добавить версионируемые миграции (например, Alembic).

## Следующие этапы

1. Добавить Redis/RabbitMQ и отдельный планировщик, который атомарно забирает задачи в
   статусе `running`.
2. Реализовать адаптеры разрешённых поисковых API и дедупликацию доменов.
3. Подключить crawler с robots.txt, ограничением домена, глубины, времени и частоты.
4. Добавить worker API для записи сайтов, попыток и структурированных ошибок.
5. Реализовать React/Next.js кабинет поверх стабильного OpenAPI-контракта.
6. Добавить Alembic, объектное хранилище, метрики, резервные копии и нагрузочные тесты.
