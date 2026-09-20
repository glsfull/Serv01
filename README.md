# Serv01

Serv01 — FastAPI-сервис для безопасного запуска наблюдаемых задач обхода сайтов.
Пользователь создаёт задачу через API или серверный веб-интерфейс, API ставит прогон
в Redis/RQ, а отдельный воркер открывает явно разрешённые страницы в headless Chromium,
соблюдает `robots.txt`, сохраняет метаданные и скриншоты.

## Возможности

- регистрация и вход по JWT; для веб-интерфейса тот же JWT хранится в HttpOnly cookie;
- CRUD и клонирование пользовательских задач и шаблонов;
- отдельные записи `task_runs` со статусами `queued/running/success/failed`;
- очередь Redis + RQ и отдельный процесс воркера;
- точный allowlist доменов до любого сетевого обращения;
- проверка `robots.txt`, честный User-Agent и таймаут не более 30 секунд на страницу;
- Playwright Chromium, снимки страниц и только чтение списка тегов `<form>`;
- история прогонов, собранные страницы и защищённая выдача PNG через API;
- Jinja2-интерфейс: `/dashboard`, `/tasks`, `/templates`, `/login`, `/register`;
- SQLite локально и полный стек PostgreSQL/Redis/API/worker в Docker Compose.

## Граница безопасности

По умолчанию разрешены только демонстрационные домены; чтобы добавить свои — правьте
`SERV01_ALLOWED_HOSTS`. Совпадение строгое: разрешение `example.com` не разрешает
`sub.example.com` или `example.com.evil.test`. Перенаправления и ресурсы страницы на
домены вне списка блокируются до загрузки.

Этот этап **не** регистрируется на внешних сайтах, не отправляет и не заполняет формы,
не обходит CAPTCHA, не использует антидетект, прокси, ротацию User-Agent или поисковые
API. Платежи, роли/тарифы, React и инфраструктура Kubernetes/Prometheus также остаются
за рамками этапа.

## Локальный запуск

Нужен **Python 3.12**. Python 3.14 не поддерживается на этом этапе из-за совместимости
браузерного стека. Также нужны Redis и Chromium для Playwright.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/playwright install chromium
cp .env.example .env
```

В первом терминале запустите API:

```bash
.venv/bin/uvicorn serv01.main:app --reload
```

Во втором — Redis, затем воркер:

```bash
redis-server
.venv/bin/rq worker --url redis://localhost:6379 default
```

После запуска доступны:

- веб-интерфейс: <http://localhost:8000/login>;
- Swagger UI: <http://localhost:8000/docs>;
- health check: <http://localhost:8000/health>.

Для ручной проверки реального браузера без Redis:

```bash
.venv/bin/python scripts/smoke_e2e.py https://example.com
```

Скрипт применяет тот же allowlist и `robots.txt`, затем пишет снимок в
`./data/screenshots/smoke.png`.

## Docker Compose

Полный стек запускается одной командой и работает от непривилегированного пользователя
в контейнерах приложения:

```bash
SERV01_JWT_SECRET="$(openssl rand -hex 32)" docker compose up --build
```

Compose поднимает `api`, `worker`, `redis` и `database`. API и worker используют общий
том `serv01-data` для скриншотов. После старта проверьте:

```bash
curl --fail http://localhost:8000/health
.venv/bin/python examples/verify_compose.py
```

Второй вызов регистрирует тестового пользователя, выполняет разрешённый прогон,
проверяет PNG и подтверждает блокировку домена вне allowlist.

## Пример API

Регистрация возвращает bearer-токен и одновременно устанавливает HttpOnly cookie:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"correct horse battery staple","full_name":"Owner"}'
```

Создайте задачу и передайте токен в `TOKEN`:

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Example crawl",
    "keywords": ["example"],
    "urls": ["https://example.com"],
    "respect_robots_txt": true
  }'

curl -X POST http://localhost:8000/api/tasks/TASK_ID/start \
  -H "Authorization: Bearer $TOKEN"
```

Ответ запуска содержит состояние задачи и `task_run_id`. Результат читается через:

| Метод | Маршрут | Назначение |
| --- | --- | --- |
| `POST` | `/api/tasks/{id}/start` | создать прогон и поставить его в RQ |
| `POST` | `/api/tasks/{id}/stop` | снять queued job или запросить отмену running job |
| `GET` | `/api/tasks/{id}/runs` | история прогонов |
| `GET` | `/api/tasks/{id}/runs/{rid}` | прогон, страницы и URL снимков |
| `GET` | `/api/screenshots/{rid}/{n}` | защищённая выдача PNG владельцу |

## Настройки

Переменные читаются из окружения и `.env` с префиксом `SERV01_`:

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `SERV01_DATABASE_URL` | `sqlite+pysqlite:///./serv01.db` | база API и worker |
| `SERV01_REDIS_URL` | `redis://localhost:6379/0` | Redis для RQ |
| `SERV01_QUEUE_NAME` | `default` | имя очереди |
| `SERV01_ALLOWED_HOSTS` | `example.com,www.iana.org,httpbin.org` | строгий список разрешённых хостов |
| `SERV01_SCREENSHOT_DIR` | `./data/screenshots` | общий каталог PNG |
| `SERV01_BOT_USER_AGENT` | `Serv01Bot/0.1 (+contact@example.com)` | честный идентификатор робота |
| `SERV01_PAGE_TIMEOUT_SECONDS` | `30` | таймаут страницы, максимум 30 секунд |
| `SERV01_JWT_SECRET` | небезопасное dev-значение | ключ JWT; обязателен в production |
| `SERV01_ACCESS_TOKEN_MINUTES` | `60` | срок JWT/cookie |

Для собственного домена, которым вы управляете:

```dotenv
SERV01_ALLOWED_HOSTS=example.com,www.iana.org,httpbin.org,my-site.example
```

Поддомены добавляются отдельно. В production замените контакт в User-Agent на реальный.

## Проверки

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest -q
docker compose config
```

Тесты используют in-memory SQLite, поддельную очередь и поддельный crawler, поэтому CI
не обращается к внешним сайтам и не требует Chromium. `scripts/smoke_e2e.py` намеренно
остаётся отдельной ручной проверкой реального Playwright.

При существующей production-базе новые таблицы и поля следует ввести миграцией перед
обновлением. Для чистого локального или Compose-запуска схема создаётся автоматически.
