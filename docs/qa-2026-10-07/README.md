# Повторный QA — 7 октября 2026

- [Полный отчёт](REPORT.md) — итог, единственный воспроизведённый дефект, закрытые прошлые находки, метрики и ограничения.
- `api-results.json`, `extended-results.json`, `security-results.json` — пробы HTTP/API и security на отдельных SQLite-базах.
- `content-results.json`, `validation-rerun.md`, `matching-validation.txt`, `testing-validation.txt` — проверки генератора задач, парсера, теста и подбора.
- `audit.py`, `extended.py`, `security_checks.py`, `content_checks.py` — воспроизводимые скрипты; базы audit и `ui.db` здесь синтетические.
- `candidate-profile.pdf` — тестовый PDF, выгруженный из изолированной UI-базы.
- `npm-audit.json`, `audit-run.txt`, `extended-run.txt`, `security-run.txt`, `pytest-summary.txt`, `frontend-build.txt`, `pip-check.txt`, `database-schema.txt`, `ui-checks.txt`, `validation-run.txt` — результаты инструментальных и ручных проверок.

## Повтор ключевых проверок

Команды из корня проекта в PowerShell:

```powershell
backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q --tb=short
npm --prefix frontend run build
npm --prefix frontend audit
backend\.venv\Scripts\python.exe -m pip check
backend\.venv\Scripts\python.exe -X utf8 docs/qa-2026-10-07/audit.py
backend\.venv\Scripts\python.exe -X utf8 docs/qa-2026-10-07/extended.py
backend\.venv\Scripts\python.exe -X utf8 docs/qa-2026-10-07/security_checks.py
backend\.venv\Scripts\python.exe -X utf8 docs/qa-2026-10-07/content_checks.py
```

Скрипты API создают отдельные `audit-*.db` в этой QA-папке. `serve_ui.py` работает только на `127.0.0.1:8110`, использует отдельную `ui.db` и генерирует демонстрационные данные; он не подключается к `dev.db`.

Команды повторной синтетической валидации из `backend`:

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.validate --n 2000 --seed 1 --out ../docs/qa-2026-10-07/validation-rerun.md
.venv\Scripts\python.exe -X utf8 -m scripts.validate_matching --n 1000 --seed 1
.venv\Scripts\python.exe -X utf8 -m scripts.validate_testing --n 1000 --seed 1
```

Прогоны опираются на синтетические данные и демонстрационную интеграцию ФСП ID. Они не заменяют тестирование реального PostgreSQL, SMTP и внешнего реестра.
