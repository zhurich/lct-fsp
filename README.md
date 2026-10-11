# ФСП Карьера

Платформа подбора ИТ-специалистов с обратной механикой: кандидат проходит опрос и адаптивный тест, получает
категорию (специализация × грейд), а работодатель сам находит его и направляет приглашение с зарплатной вилкой.
Контакты кандидата открываются работодателю только после принятия приглашения.

Решение для специального трека ФСП.

## Адреса и демо-входы

Развёрнутый стенд: **http://89.110.105.165** (описание API — http://89.110.105.165/api/docs). База наполнена
демонстрационными данными, входы — в таблице ниже. Стенд работает в режиме проверки: регистрация без письма
с подтверждением, кандидат может сбросить свои попытки и пройти тест заново.

Для своего запуска:

| Что | Docker | Локальный запуск |
|---|---|---|
| Приложение | http://localhost:8080 | http://localhost:5183 |
| Описание API (Swagger) | http://localhost:8080/api/docs | http://localhost:8100/api/docs |
| Письма с подтверждением регистрации | http://localhost:8025 (Mailpit) | журнал бэкенда |

Демо-входы появляются после наполнения базы (команда — в разделах о запуске). Пароль у всех `demo12345`.

| Почта | Кто это | Что показать |
|---|---|---|
| `demo-employer@example.com` | Работодатель с потребностями, вакансиями и откликами | Подборка с объяснением, приглашение с зарплатой |
| `demo-candidate@example.com` | Кандидат с категорией и входящими приглашениями | Ответ на приглашение, раскрытие контактов |
| `demo-newcomer@example.com` | Новый кандидат без теста | Путь «опрос → тест → категория» с начала |
| `demo-newcomer2@example.com` … `demo-newcomer5@example.com` | Такие же чистые записи | По одной на проверяющего |

Вход через демонстрационный ФСП ID — кнопка «Войти через ФСП ID»: любая почта, пароль `fsp-demo`.
Готовые участники: `champion@fsp.example` (шесть соревнований, пять призовых мест), `participant@fsp.example`
(два участия без призовых мест), `newcomer@fsp.example` (без истории соревнований).

Чтобы работать за кандидата и работодателя одновременно, откройте второго в окне инкогнито.
На стенде проверки задайте в `.env` `DEMO_MODE=true`: регистрация пройдёт без письма с подтверждением, а
кандидат сможет сбросить свои попытки и пройти тест заново.

## Документация

- [docs/documentation.pdf](docs/documentation.pdf) — сопроводительная документация: архитектура, механики
  тестирования и подбора, валидация и её результаты, интеграция с ФСП, API, зависимости, запуск.
- [docs/documentation.md](docs/documentation.md) — её исходный текст, [docs/api.md](docs/api.md) — перечень
  методов API.
- Интерактивное описание API (Swagger) — по адресу `/api/docs` запущенного приложения.

## Структура

- `backend/app` — API на FastAPI: монолит с модулями в `app/modules`, SQLAlchemy, PostgreSQL.
- `backend/scripts` — демонстрационные данные, валидация, сборка документации.
- `backend/tests` — автоматические тесты.
- `frontend` — веб-приложение для обеих ролей на React, TypeScript и Mantine.
- `docker-compose.yml` — PostgreSQL, backend, frontend (nginx) и Mailpit для писем.
- `compose.server.yml` — то же для стенда на небольшом сервере, с заранее собранным фронтендом.

## Запуск в Docker

```bash
cp .env.example .env   # задать SECRET_KEY
docker compose up --build -d
docker compose exec backend python -m scripts.seed --reset   # демонстрационные данные, необязательно
```

- Приложение: http://localhost:8080
- Описание API: http://localhost:8080/api/docs
- Письма с подтверждением регистрации: http://localhost:8025

### Стенд на небольшом сервере

`compose.server.yml` — вариант для VPS с 1 ГБ памяти, по нему развёрнут стенд. Фронтенд в Docker не собирается
(сборка Node в такую память не помещается): `frontend/dist` собирается заранее и отдаётся готовым nginx. Сайт
на 80-м порту, Mailpit нет (письма пишутся в журнал бэкенда), контейнеры поднимаются после перезагрузки.

```bash
npm --prefix frontend ci && npm --prefix frontend run build   # на своей машине, затем скопировать на сервер
# на сервере, в .env: SECRET_KEY, POSTGRES_PASSWORD, PUBLIC_URL=http://<адрес>, DEMO_MODE=true,
# COMPOSE_FILE=compose.server.yml
docker compose up --build -d
docker compose exec -T backend python -m scripts.seed --reset
```

## Локальный запуск без Docker

Нужны Python 3.13 и Node.js 20. Используется SQLite (файл `dev.db` в корне), письма выводятся в журнал бэкенда.
Перед первым запуском создайте в корне файл `.env` со строкой `SECRET_KEY=<секрет>` (не короче 32 символов):
без него бэкенд не стартует. Секрет: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Команды выполняются из корня репозитория; на Linux и macOS вместо `.venv/Scripts/python` — `.venv/bin/python`.

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8100
```

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Приложение: http://localhost:5183, описание API: http://localhost:8100/api/docs.

Демонстрационные данные (команда удаляет все данные в базе):

```bash
PYTHONPATH=backend backend/.venv/Scripts/python -m scripts.seed --reset
```

Входы после наполнения — в разделе «Адреса и демо-входы».

## Проверки

```bash
cd backend
.venv/Scripts/python -m pytest                                               # тесты
.venv/Scripts/python -m scripts.validate --out ../docs/validation_report.md  # отчёт валидации, около 2 минут
.venv/Scripts/python -m scripts.build_docs                                   # PDF документации
cd ../frontend && npm run build                                              # типы и сборка интерфейса
```
