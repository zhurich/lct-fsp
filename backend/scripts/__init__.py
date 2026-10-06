import sys


def utf8_output() -> None:
    """Переключает вывод на UTF-8: в консоли Windows с кодировкой cp1251 печать отчёта со знаками
    вроде «→» и «θ» падает, в том числе при перенаправлении в файл."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
