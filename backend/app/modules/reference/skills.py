"""Словарь технологий: каноническое название, варианты написания и специализации, для которых оно типично.

По нему стек кандидата и текст потребности работодателя приводятся к одним названиям («постгрес» и
«Postgres» → PostgreSQL), а по набору технологий угадывается специализация, если она не названа явно.
"""

import re

# Название: (варианты написания в нижнем регистре, специализации).
SKILLS: dict[str, tuple[list[str], list[str]]] = {
    "Python": (["python", "питон", "пайтон"], ["backend", "data", "qa"]),
    "Django": (["django", "джанго"], ["backend"]),
    "FastAPI": (["fastapi"], ["backend"]),
    "Flask": (["flask"], ["backend"]),
    "Java": (["java", "джава"], ["backend", "mobile"]),
    "Spring": (["spring boot", "spring"], ["backend"]),
    "Kotlin": (["kotlin", "котлин"], ["mobile", "backend"]),
    "Go": (["golang", "go"], ["backend", "devops"]),
    "C#": (["c#", "csharp"], ["backend"]),
    ".NET": ([".net", "dotnet", "asp.net"], ["backend"]),
    "C++": (["c++", "cpp"], ["backend"]),
    "PHP": (["php"], ["backend"]),
    "Laravel": (["laravel"], ["backend"]),
    "Node.js": (["node.js", "nodejs", "node"], ["backend"]),
    "JavaScript": (["javascript", "js"], ["frontend"]),
    "TypeScript": (["typescript", "ts"], ["frontend"]),
    "React": (["react.js", "reactjs", "react", "реакт"], ["frontend"]),
    "Vue": (["vue.js", "vuejs", "vue"], ["frontend"]),
    "Angular": (["angular"], ["frontend"]),
    "Next.js": (["next.js", "nextjs"], ["frontend"]),
    "Redux": (["redux"], ["frontend"]),
    "HTML": (["html"], ["frontend"]),
    "CSS": (["css", "scss", "sass"], ["frontend"]),
    "Figma": (["figma", "фигма"], ["frontend", "analyst"]),
    "SQL": (["sql"], ["backend", "data", "analyst", "qa"]),
    "PostgreSQL": (["postgresql", "postgres", "постгрес"], ["backend"]),
    "MySQL": (["mysql"], ["backend"]),
    "MongoDB": (["mongodb", "mongo"], ["backend"]),
    "Redis": (["redis"], ["backend"]),
    "ClickHouse": (["clickhouse"], ["data", "backend"]),
    "Elasticsearch": (["elasticsearch", "elastic"], ["backend"]),
    "Kafka": (["kafka", "кафка"], ["backend"]),
    "RabbitMQ": (["rabbitmq", "rabbit"], ["backend"]),
    "REST": (["rest api", "rest"], ["backend", "analyst"]),
    "GraphQL": (["graphql"], ["backend", "frontend"]),
    "gRPC": (["grpc"], ["backend"]),
    "OpenAPI": (["openapi", "swagger"], ["analyst", "backend"]),
    "Docker": (["docker", "докер"], ["devops", "backend"]),
    "Kubernetes": (["kubernetes", "k8s", "кубернетес"], ["devops"]),
    "Linux": (["linux", "линукс"], ["devops"]),
    "Git": (["git"], []),
    "CI/CD": (["ci/cd", "cicd", "gitlab ci", "github actions", "jenkins"], ["devops"]),
    "Terraform": (["terraform"], ["devops"]),
    "Ansible": (["ansible"], ["devops"]),
    "Prometheus": (["prometheus"], ["devops"]),
    "Grafana": (["grafana"], ["devops"]),
    "Nginx": (["nginx"], ["devops"]),
    "AWS": (["aws"], ["devops"]),
    "Swift": (["swift"], ["mobile"]),
    "SwiftUI": (["swiftui"], ["mobile"]),
    "iOS": (["ios"], ["mobile"]),
    "Android": (["android", "андроид"], ["mobile"]),
    "Jetpack Compose": (["jetpack compose", "jetpack"], ["mobile"]),
    "Flutter": (["flutter", "dart"], ["mobile"]),
    "React Native": (["react native"], ["mobile"]),
    "Selenium": (["selenium"], ["qa"]),
    "Playwright": (["playwright"], ["qa"]),
    "Cypress": (["cypress"], ["qa"]),
    "Postman": (["postman"], ["qa"]),
    "pytest": (["pytest"], ["qa"]),
    "JUnit": (["junit"], ["qa"]),
    "Allure": (["allure"], ["qa"]),
    "Pandas": (["pandas"], ["data"]),
    "NumPy": (["numpy"], ["data"]),
    "scikit-learn": (["scikit-learn", "sklearn"], ["data"]),
    "PyTorch": (["pytorch", "torch"], ["data"]),
    "TensorFlow": (["tensorflow"], ["data"]),
    "Spark": (["pyspark", "spark"], ["data"]),
    "Airflow": (["airflow"], ["data"]),
    "Machine Learning": (["machine learning", "машинное обучение", "ml"], ["data"]),
    "NLP": (["nlp"], ["data"]),
    "BPMN": (["bpmn"], ["analyst"]),
    "UML": (["uml"], ["analyst"]),
    "Jira": (["jira"], ["analyst", "qa"]),
    "Confluence": (["confluence"], ["analyst"]),
}

_BY_ALIAS = {alias: name for name, (aliases, _) in SKILLS.items() for alias in [name.lower(), *aliases]}
# Длинные варианты ищутся первыми, чтобы «react native» не распознался как React.
# Границы слова свои: стандартная \b не подходит для C#, C++ и .NET.
_PATTERNS = [
    (re.compile(rf"(?<![\w+#.]){re.escape(alias)}(?![\w+#])", re.IGNORECASE), name)
    for alias, name in sorted(_BY_ALIAS.items(), key=lambda pair: -len(pair[0]))
]


def normalize_skill(raw: str) -> str:
    """Каноническое название технологии; неизвестная технология возвращается как есть."""
    cleaned = raw.strip()
    return _BY_ALIAS.get(cleaned.lower(), cleaned)


def skill_key(raw: str) -> str:
    """Ключ для сравнения технологий без учёта регистра и варианта написания."""
    return normalize_skill(raw).lower()


def extract_skills(text: str) -> list[str]:
    """Технологии из словаря, упомянутые в свободном тексте, в порядке первого упоминания."""
    found: dict[str, int] = {}
    for pattern, name in _PATTERNS:
        match = pattern.search(text)
        while match:
            found[name] = min(found.get(name, match.start()), match.start())
            # Найденный фрагмент затирается, чтобы более короткий вариант не сработал на нём же.
            text = text[: match.start()] + " " * (match.end() - match.start()) + text[match.end() :]
            match = pattern.search(text)
    return sorted(found, key=found.get)
