"""Тестовый набор описаний вакансий с ручной разметкой.

Тексты написаны в разной манере — от формальных до разговорных, — чтобы проверить разбор потребности
правилами. Разметка (gold) — то, что должен извлечь разбор; она же служит запросом при проверке подбора.
"""

VACANCIES: list[dict] = [
    {
        "title": "Бэкенд-разработчик в платежи",
        "text": "Ищем в команду платежей бэкенд-разработчика уровня middle. Стек: Python, FastAPI, PostgreSQL, "
                "Kafka, Docker. Задачи — интеграции с банками и сервис сверки. Удалённо или гибрид, "
                "вилка от 200 до 280 тыс. руб.",
        "gold": {"specialization": "backend", "grade": "middle",
                 "stack": ["Python", "FastAPI", "PostgreSQL", "Kafka", "Docker"],
                 "work_formats": ["remote", "hybrid"], "salary": (200_000, 280_000)},
    },
    {
        "title": "Senior Java в логистику",
        "text": "Нужен сильный серверный разработчик: Java, Spring Boot, Kafka, PostgreSQL, опыт от 5 лет, "
                "проектирование микросервисов и наставничество. Офис в Москве. Зарплата 350 000 – 450 000 ₽.",
        "gold": {"specialization": "backend", "grade": "senior", "stack": ["Java", "Spring", "Kafka", "PostgreSQL"],
                 "work_formats": ["office"], "salary": (350_000, 450_000)},
    },
    {
        "title": "Фронтенд в личный кабинет",
        "text": "В продуктовую команду нужен frontend-разработчик (мидл): React, TypeScript, Redux, вёрстка по "
                "макетам Figma. Удалёнка. 180–240 тыс.",
        "gold": {"specialization": "frontend", "grade": "middle", "stack": ["React", "TypeScript", "Redux", "Figma"],
                 "work_formats": ["remote"], "salary": (180_000, 240_000)},
    },
    {
        "title": "Начинающий фронтендер",
        "text": "Возьмём джуна на фронт: HTML, CSS, JavaScript, желательно Vue. Научим, дадим наставника. "
                "Гибридный график, от 70 до 100 тыс. рублей.",
        "gold": {"specialization": "frontend", "grade": "junior", "stack": ["HTML", "CSS", "JavaScript", "Vue"],
                 "work_formats": ["hybrid"], "salary": (70_000, 100_000)},
    },
    {
        "title": "Android-разработчик",
        "text": "Развиваем мобильное приложение доставки. Нужен Android-разработчик с опытом от 2 лет: Kotlin, "
                "Jetpack Compose, работа с REST. Формат — удалённо.",
        "gold": {"specialization": "mobile", "grade": "middle", "stack": ["Android", "Kotlin", "Jetpack Compose", "REST"],
                 "work_formats": ["remote"], "salary": None},
    },
    {
        "title": "iOS, старший разработчик",
        "text": "Senior iOS: Swift, SwiftUI, архитектура приложения, код-ревью. Офис или гибрид, "
                "з/п от 300 до 400 тыс.",
        "gold": {"specialization": "mobile", "grade": "senior", "stack": ["iOS", "Swift", "SwiftUI"],
                 "work_formats": ["office", "hybrid"], "salary": (300_000, 400_000)},
    },
    {
        "title": "Автоматизатор тестирования",
        "text": "Требуется QA-инженер уровня middle для автотестов: Python, pytest, Playwright, Postman, SQL. "
                "Удалённая работа, 150–200 тыс.",
        "gold": {"specialization": "qa", "grade": "middle", "stack": ["Python", "pytest", "Playwright", "Postman", "SQL"],
                 "work_formats": ["remote"], "salary": (150_000, 200_000)},
    },
    {
        "title": "Стажёр-тестировщик",
        "text": "Приглашаем стажёра в отдел тестирования, можно без опыта. Нужно понимать, что такое тест-кейс, "
                "и не бояться Postman и Jira. Офис, Казань.",
        "gold": {"specialization": "qa", "grade": "intern", "stack": ["Postman", "Jira"],
                 "work_formats": ["office"], "salary": None},
    },
    {
        "title": "DevOps в платформенную команду",
        "text": "Нужен DevOps-инженер, senior: Kubernetes, Terraform, GitLab CI, Prometheus, Grafana, Linux. "
                "Удалённо. Вилка 320 000–420 000 руб.",
        "gold": {"specialization": "devops", "grade": "senior",
                 "stack": ["Kubernetes", "Terraform", "CI/CD", "Prometheus", "Grafana", "Linux"],
                 "work_formats": ["remote"], "salary": (320_000, 420_000)},
    },
    {
        "title": "Младший инженер инфраструктуры",
        "text": "Ищем junior в команду инфраструктуры: Linux, Docker, Ansible, базовые знания Nginx. "
                "Гибрид, от 90 до 130 тыс.",
        "gold": {"specialization": "devops", "grade": "junior", "stack": ["Linux", "Docker", "Ansible", "Nginx"],
                 "work_formats": ["hybrid"], "salary": (90_000, 130_000)},
    },
    {
        "title": "ML-инженер в рекомендации",
        "text": "Команде рекомендаций нужен ML-инженер уровня мидл: Python, PyTorch, Pandas, Airflow, Spark. "
                "Удалённо или офис, 250–330 тыс.",
        "gold": {"specialization": "data", "grade": "middle", "stack": ["Python", "PyTorch", "Pandas", "Airflow", "Spark"],
                 "work_formats": ["remote", "office"], "salary": (250_000, 330_000)},
    },
    {
        "title": "Аналитик данных",
        "text": "Аналитик данных, junior: SQL, Pandas, ClickHouse, умение объяснять выводы. Офис в "
                "Санкт-Петербурге, зарплата 100 000 – 140 000 ₽.",
        "gold": {"specialization": "data", "grade": "junior", "stack": ["SQL", "Pandas", "ClickHouse"],
                 "work_formats": ["office"], "salary": (100_000, 140_000)},
    },
    {
        "title": "Системный аналитик интеграций",
        "text": "Нужен системный аналитик с опытом от 3 лет: проектирование интеграций, REST, OpenAPI, BPMN, UML, "
                "SQL. Удалённо, от 230 до 300 тыс.",
        "gold": {"specialization": "analyst", "grade": "senior", "stack": ["REST", "OpenAPI", "BPMN", "UML", "SQL"],
                 "work_formats": ["remote"], "salary": (230_000, 300_000)},
    },
    {
        "title": "Бизнес-аналитик",
        "text": "Бизнес-аналитик middle в команду внутренних сервисов: сбор требований, BPMN, Jira, Confluence. "
                "Гибрид.",
        "gold": {"specialization": "analyst", "grade": "middle", "stack": ["BPMN", "Jira", "Confluence"],
                 "work_formats": ["hybrid"], "salary": None},
    },
]
