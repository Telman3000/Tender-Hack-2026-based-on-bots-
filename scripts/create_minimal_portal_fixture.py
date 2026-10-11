"""Minimal portal XLSX fixtures for red-team (not official hackathon exports)."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_materials" / "Примеры выгрузок"
OUT.mkdir(parents=True, exist_ok=True)


def write_book(path: Path, ste_rows: list[tuple], char_rows: list[tuple]) -> None:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "STE"
    ws1.append(["ste_id", "name", "c2", "manufacturer", "c4", "chars_raw"])
    for r in ste_rows:
        ws1.append(list(r))
    ws2 = wb.create_sheet("chars")
    ws2.append(["category", "kpgz", "c2", "char_name", "char_type", "c5", "values_sample", "unit"])
    for r in char_rows:
        ws2.append(list(r))
    wb.save(path)


def main() -> None:
    write_book(
        OUT / "Одежда.xlsx",
        [
            ("1", "Костюм рабочий мужской л08-КБР", "", "ОФИСМАГ", "", "размер;рост;ткань"),
            ("2", "Футболка хлопок ОФИСМАГ", "", "ОФИСМАГ", "", "хлопок;размер"),
            ("3", "Куртка зимняя Аляска", "", "ОФИСМАГ", "", "размер;рост"),
        ],
        [
            ("Костюм рабочий", "14.12", "", "рост", "число", "", "170-176", "см"),
            ("Костюм рабочий", "14.12", "", "размер", "строка", "", "48-50", ""),
            ("Футболка", "14.14", "", "Содержание хлопка", "число", "", "100", "%"),
            ("Футболка", "14.14", "", "Масса", "число", "", "179", "г"),
        ],
    )
    write_book(
        OUT / "Мебель.xlsx",
        [
            ("10", "Стол офисный ДСП", "", "ОФИСМАГ", "", "высота;ширина;глубина"),
            ("11", "Стул офисный", "", "ОФИСМАГ", "", "цвет"),
        ],
        [
            ("Стол письменный", "31.01", "", "Высота", "число", "", "750", "мм"),
            ("Стол письменный", "31.01", "", "Ширина", "число", "", "1200", "мм"),
        ],
    )
    write_book(
        OUT / "Инструменты.xlsx",
        [
            ("20", "Молоток слесарный", "", "ОФИСМАГ", "", "масса"),
            ("21", "Ключ гаечный разводной", "", "ОФИСМАГ", "", "длина"),
        ],
        [
            ("Молоток", "25.73", "", "Масса молотка", "число", "", "500", "г"),
        ],
    )
    print("Wrote minimal portal fixtures to", OUT)


if __name__ == "__main__":
    main()
