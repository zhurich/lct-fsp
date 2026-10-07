"""Сборка сопроводительной документации в PDF.

Запуск: python -m scripts.build_docs   (из каталога backend)

Собирает docs/documentation.md, описание API из спецификации OpenAPI приложения и отчёт валидации
docs/validation_report.md в один файл docs/documentation.pdf. Описание API берётся из кода, поэтому
не расходится с ним; оно же сохраняется отдельно в docs/api.md.
"""

import re
from pathlib import Path

import markdown
from fpdf import FPDF, FontFace

from app.main import app
from scripts import utf8_output

DOCS = Path(__file__).resolve().parents[2] / "docs"

# Наборы шрифтов с кириллицей: обычный, полужирный, курсив, моноширинный.
_FONT_SETS = [
    [f"/usr/share/fonts/truetype/dejavu/{name}.ttf" for name in ("DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique", "DejaVuSansMono")],
    [f"C:/Windows/Fonts/{name}.ttf" for name in ("arial", "arialbd", "ariali", "consola")],
]


def api_markdown() -> str:
    """Таблицы методов API по разделам спецификации OpenAPI."""
    sections: dict[str, list[str]] = {}
    for path, methods in app.openapi()["paths"].items():
        for method, operation in methods.items():
            errors = [
                f"{code} — {response['description']}"
                for code, response in operation["responses"].items()
                # 422 без своего описания — стандартная ошибка валидации, она есть почти у всех методов.
                if code.startswith(("4", "5")) and response["description"] != "Validation Error"
            ]
            row = f"| `{method.upper()} {path}` | {operation.get('summary', '')} | {'; '.join(errors) or '—'} |"
            sections.setdefault(operation.get("tags", ["Прочее"])[0], []).append(row)
    lines = [
        "Все методы начинаются с `/api`, принимают и возвращают JSON (кроме загрузки резюме и выгрузки PDF). "
        "Авторизация — cookie `access_token`, которую выставляет метод входа. Общие коды ошибок: 401 — не выполнен "
        "вход, 403 — раздел другой роли, 422 — ошибка в данных запроса (текст — в поле `detail`). Полные схемы "
        "запросов и ответов — в интерактивном описании `/api/docs` и в `/api/openapi.json`.",
    ]
    for tag, rows in sections.items():
        lines += ["", f"### {tag}", "", "| Метод и путь | Назначение | Свои коды ошибок |", "|---|---|---|", *rows]
    return "\n".join(lines) + "\n"


def build() -> Path:
    api = api_markdown()
    (DOCS / "api.md").write_text("# Описание API\n\n" + api, encoding="utf-8")
    report = (DOCS / "validation_report.md").read_text(encoding="utf-8")
    # В приложении заголовки отчёта опускаются на уровень ниже, чтобы не спорить с разделами документа.
    report = "\n".join("#" + line if line.startswith("#") else line for line in report.splitlines()[1:])
    source = (
        (DOCS / "documentation.md").read_text(encoding="utf-8")
        + "\n\n## Приложение А. Описание API\n\n"
        + api
        + "\n\n## Приложение Б. Полный отчёт валидации\n"
        + report
    )
    html = markdown.markdown(source, extensions=["tables", "fenced_code"])
    # fpdf2 не поддерживает вложенные теги в ячейках таблиц — оформление внутри ячеек снимается.
    html = re.sub(
        r"(<t[dh][^>]*>)(.*?)(</t[dh]>)",
        lambda cell: cell.group(1) + re.sub(r"</?(?:code|strong|em|a)[^>]*>", "", cell.group(2)) + cell.group(3),
        html,
        flags=re.S,
    )

    html = html.replace("<td>", '<td align="left">')
    # В таблицах из двух колонок первая — короткое название, ей хватает трети ширины.
    html = re.sub(r"<tr>\s*<th>([^<]*)</th>\s*<th>([^<]*)</th>\s*</tr>", r'<tr><th width="30%">\1</th><th width="70%">\2</th></tr>', html)
    # В таблицах API первая колонка — длинный путь метода.
    html = html.replace(
        "<th>Метод и путь</th>\n<th>Назначение</th>\n<th>Свои коды ошибок</th>",
        '<th width="44%">Метод и путь</th><th width="30%">Назначение</th><th width="26%">Свои коды ошибок</th>',
    )

    fonts = next(fonts for fonts in _FONT_SETS if all(Path(font).is_file() for font in fonts))
    pdf = FPDF()
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(auto=True, margin=16)
    for style, font in zip(("", "B", "I"), fonts):
        pdf.add_font("main", style, font)
    pdf.add_font("main", "BI", fonts[1])
    pdf.add_font("mono", "", fonts[3])
    pdf.set_title("ФСП Карьера — сопроводительная документация")
    pdf.add_page()
    pdf.set_font("main", size=10)
    mono = FontFace(family="mono", size_pt=8.5)
    pdf.write_html(
        html,
        table_line_separators=True,
        tag_styles={
            "h1": FontFace(family="main", emphasis="B", size_pt=22, color=(20, 40, 90)),
            "h2": FontFace(family="main", emphasis="B", size_pt=15, color=(20, 40, 90)),
            "h3": FontFace(family="main", emphasis="B", size_pt=12),
            "pre": mono,
            "code": mono,
        },
    )
    target = DOCS / "documentation.pdf"
    pdf.output(str(target))
    return target


if __name__ == "__main__":
    utf8_output()
    result = build()
    print(f"{result} ({result.stat().st_size // 1024} КБ)")
