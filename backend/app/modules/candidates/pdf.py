"""Стандартизированный PDF-профиль кандидата.

Структура одинакова для всех: контакты, подтверждённая категория, стек, опыт, достижения ФСП. Подтверждённые
платформой сведения (категория, балл теста, достижения из реестра) отделены от того, что кандидат сообщил
о себе сам.
"""

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from app.core.config import settings
from app.modules.assessment.models import CandidateCategory
from app.modules.candidates.models import CandidateProfile
from app.modules.fsp.registry import LEVELS
from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS

# Шрифт с кириллицей: (обычный, полужирный). В образе Docker ставится пакет fonts-dejavu-core,
# на Windows и macOS берётся системный Arial.
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


class PdfUnavailable(RuntimeError):
    """На сервере нет шрифта с кириллицей."""


def _fonts() -> tuple[str, str]:
    candidates = list(_FONT_CANDIDATES)
    if settings.pdf_font_dir:
        folder = Path(settings.pdf_font_dir)
        candidates.insert(0, (str(folder / "DejaVuSans.ttf"), str(folder / "DejaVuSans-Bold.ttf")))
    for regular, bold in candidates:
        if Path(regular).is_file() and Path(bold).is_file():
            return regular, bold
    raise PdfUnavailable("Не найден шрифт с кириллицей: установите fonts-dejavu-core или задайте PDF_FONT_DIR")


def build_profile_pdf(profile: CandidateProfile, email: str, category: CandidateCategory | None) -> bytes:
    regular, bold = _fonts()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_font("main", "", regular)
    pdf.add_font("main", "B", bold)
    pdf.add_page()

    def line(text: str, size: int = 10, style: str = "", gray: bool = False) -> None:
        pdf.set_font("main", style, size)
        pdf.set_text_color(110 if gray else 20)
        pdf.multi_cell(0, size * 0.55, text, new_x="LMARGIN", new_y="NEXT")

    def section(title: str) -> None:
        pdf.ln(4)
        line(title, 12, "B")
        pdf.set_draw_color(200)
        pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
        pdf.ln(3)

    line("ФСП Карьера · профиль кандидата", 9, gray=True)
    pdf.ln(2)
    line(profile.full_name or "Имя не указано", 20, "B")
    contacts = [email, profile.phone, profile.telegram, profile.city]
    line(" · ".join(item for item in contacts if item), 10, gray=True)

    section("Подтверждено платформой")
    if category:
        line(f"{SPECIALIZATIONS[category.specialization]} · {GRADES[category.grade]['name']}", 14, "B")
        line(
            f"Категория присвоена по результату адаптивного теста {category.assigned_at:%d.%m.%Y}, "
            f"балл {category.score * 100:.0f} из 100."
        )
    else:
        line("Категория не присвоена: тестирование ещё не пройдено.")
    if profile.fsp_achievements:
        pdf.ln(2)
        line(f"Достижения Федерации спортивного программирования (ФСП ID {profile.fsp_id}):", style="B")
        if profile.fsp_rank:
            line(f"Спортивный разряд: {profile.fsp_rank}.")
        for item in profile.fsp_achievements:
            place = f"{item['place']} место" if item["place"] else "участие"
            line(f"•  {item['date'][:4]} — {item['event']}, {LEVELS[item['level']].lower()} уровень: {place}. {item['discipline']}")

    section("Со слов кандидата")
    facts = [
        ("Специализация", SPECIALIZATIONS.get(profile.specialization or "", "")),
        ("Стаж", f"{profile.experience_years:g} г." if profile.experience_years else ""),
        ("Стек", ", ".join(profile.stack)),
        ("Роли в команде", ", ".join(profile.roles)),
        ("Софт-скиллы", ", ".join(profile.soft_skills)),
        ("Формат работы", ", ".join(WORK_FORMATS[code].lower() for code in profile.work_formats)),
    ]
    for label, value in facts:
        if value:
            line(f"{label}: {value}")
    if profile.about:
        pdf.ln(2)
        line(profile.about)

    pdf.ln(6)
    line(f"Сформировано автоматически {datetime.now():%d.%m.%Y}.", 8, gray=True)
    return bytes(pdf.output())
