# -*- coding: utf-8 -*-
"""
ECOM EXPO 2026 — сбор участников выставки со страницы expo.oborot.ru
и выгрузка в Excel: на каждой вкладке — компании из своей рубрики.

Источник данных: блок «Список экспонентов» (https://expo.oborot.ru/#schemeplan).
Все данные присутствуют в статическом HTML (раскрывающиеся блоки — это
обычные CSS-аккордеоны), поэтому браузер/Selenium не требуются.

Запуск:
    python scraper.py                     # скачать с сайта и сохранить Excel
    python scraper.py --html page.html    # разобрать локально сохранённый HTML
    python scraper.py --group booth_number # другая группировка (см. GROUPINGS)

Результат: exhibitors_ecom_expo_2026.xlsx
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

URL = "https://expo.oborot.ru/"
BASE = "https://expo.oborot.ru"
DEFAULT_OUT = "exhibitors_ecom_expo_2026.xlsx"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Доступные варианты группировки экспонентов на странице.
# Ключ data-scheme-booth-table -> человекочитаемое имя.
GROUPINGS = {
    "main_category": "По рубрикам",          # 7 рубрик (рекомендуется)
    "company_name": "По алфавиту",
    "booth_number": "По номеру стенда",
    "serviсe_purpose": "По типу услуг",      # внимание: 'с' в ключе кириллическая (как в HTML)
}

# Номер стенда в конце ссылки: "Компания (G6.9)"
BOOTH_RE = re.compile(r"\(([^()]{1,12})\)\s*$")
# ID экспонента из onclick="fetchExhibitorData('/detail/one_exhibitor/',441171)"
DETAIL_ID_RE = re.compile(r"fetchExhibitorData\([^,]+,\s*(\d+)\)")
# Ячейка компании: cell_col_1 / cell_col_2 / cell_col_3 (3-колоночная вёрстка)
CELL_RE = re.compile(r"\bcell_col_\d+\b")


@dataclass
class Exhibitor:
    rubric: str = ""
    name: str = ""
    website: str = ""
    booth: str = ""
    description: str = ""
    works_via_marketplaces: bool = False
    own_sales_channel: bool = False
    detail_id: Optional[int] = None


# Порядок и подписи колонок в Excel
COLUMNS = [
    ("name", "Компания"),
    ("website", "Сайт"),
    ("booth", "Стенд"),
    ("description", "Описание"),
    ("works_via_marketplaces", "Работа через маркетплейсы"),
    ("own_sales_channel", "Собственный канал продаж"),
    ("detail_id", "ID экспонента"),
]


def fetch_html(url: str = URL) -> str:
    """Скачать страницу. Кодировка сайта — UTF-8."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_cell(cell, rubric: str) -> Optional[Exhibitor]:
    """Разобрать один блок .cell_col_1 (одна компания)."""
    title = cell.select_one(".exh_title")
    if not title:
        return None

    link = title.select_one("a")
    name = _clean(link.get_text()) if link else _clean(title.get_text())
    if not name:
        return None

    website = (link.get("href") or "").strip() if link else ""
    if website.lower().startswith("javascript"):
        website = ""

    # Номер стенда — из текста после ссылки, напр. "AKFA (G6.9)"
    booth = ""
    title_text = _clean(title.get_text(" "))
    m = BOOTH_RE.search(title_text)
    if m:
        booth = m.group(1).strip()

    descr_el = cell.select_one(".exh_descr")
    description = _clean(descr_el.get_text(" ")) if descr_el else ""

    works_mp = cell.select_one("img.icon_for_marketplace") is not None
    own_shop = cell.select_one("img.icon_for_shop") is not None

    detail_id = None
    detail_a = cell.select_one("a.detail_link[onclick]")
    if detail_a:
        dm = DETAIL_ID_RE.search(detail_a.get("onclick", ""))
        if dm:
            detail_id = int(dm.group(1))

    return Exhibitor(
        rubric=rubric,
        name=name,
        website=website,
        booth=booth,
        description=description,
        works_via_marketplaces=works_mp,
        own_sales_channel=own_shop,
        detail_id=detail_id,
    )


def parse_exhibitors(html: str, group: str = "main_category") -> "list[Exhibitor]":
    """Извлечь экспонентов из выбранной группировки.

    Возвращает список Exhibitor с заполненным полем `rubric`
    (= название вкладки/рубрики в этой группировке).
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one(f'[data-scheme-booth-table="{group}"]')
    if table is None:
        raise RuntimeError(
            f"Не найдена группировка '{group}'. "
            f"Доступны: {', '.join(GROUPINGS)}"
        )

    tabs = table.select("[data-scheme-booth-table-tab]")
    contents = table.select("[data-scheme-booth-table-content]")
    result: list[Exhibitor] = []

    for tab, content in zip(tabs, contents):
        rubric = _clean(tab.get_text(" "))
        # Блок рубрики свёрстан в 3 колонки: ячейки имеют классы
        # cell_col_1 / cell_col_2 / cell_col_3 — берём все три.
        for cell in content.find_all(class_=CELL_RE):
            ex = parse_cell(cell, rubric)
            if ex:
                result.append(ex)
    return result


# ---- Excel ------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="1F7A3D")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=12)


def _safe_sheet_title(name: str, used: set) -> str:
    """Имя листа Excel: <=31 символ, без : \\ / ? * [ ], уникальное."""
    title = re.sub(r"[:\\/?*\[\]]", " ", name).strip() or "Лист"
    title = title[:31]
    base, i = title, 2
    while title.lower() in used:
        suffix = f" ({i})"
        title = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(title.lower())
    return title


def write_excel(exhibitors: "list[Exhibitor]", out_path: str, group_label: str) -> None:
    # Сгруппировать по рубрике с сохранением порядка появления
    by_rubric: dict[str, list[Exhibitor]] = {}
    for ex in exhibitors:
        by_rubric.setdefault(ex.rubric, []).append(ex)

    wb = Workbook()
    used_titles: set = set()

    # Сводный лист
    summary = wb.active
    summary.title = _safe_sheet_title("Сводка", used_titles)
    summary["A1"] = f"ECOM EXPO 2026 — экспоненты ({group_label})"
    summary["A1"].font = TITLE_FONT
    summary["A3"] = "Рубрика"
    summary["B3"] = "Кол-во компаний"
    for c in ("A3", "B3"):
        summary[c].font = HEADER_FONT
        summary[c].fill = HEADER_FILL
    row = 4
    for rubric, items in by_rubric.items():
        summary.cell(row, 1, rubric)
        summary.cell(row, 2, len(items))
        row += 1
    summary.cell(row, 1, "ИТОГО").font = Font(bold=True)
    summary.cell(row, 2, len(exhibitors)).font = Font(bold=True)
    summary.column_dimensions["A"].width = 40
    summary.column_dimensions["B"].width = 18

    # По листу на рубрику
    for rubric, items in by_rubric.items():
        ws = wb.create_sheet(_safe_sheet_title(rubric, used_titles))
        for col_idx, (_, header) in enumerate(COLUMNS, start=1):
            c = ws.cell(1, col_idx, header)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for r, ex in enumerate(items, start=2):
            d = asdict(ex)
            for col_idx, (key, _) in enumerate(COLUMNS, start=1):
                val = d[key]
                if isinstance(val, bool):
                    val = "да" if val else ""
                ws.cell(r, col_idx, val)
        # Ширины колонок
        widths = [32, 34, 10, 60, 16, 16, 14]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(items) + 1}"
        # перенос текста в колонке описания
        for r in range(2, len(items) + 2):
            ws.cell(r, 4).alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(out_path)


# ---- CLI --------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Сбор экспонентов ECOM EXPO 2026 -> Excel")
    ap.add_argument("--html", help="Путь к локально сохранённому HTML (вместо скачивания)")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"Имя Excel-файла (по умолчанию {DEFAULT_OUT})")
    ap.add_argument("--group", default="main_category", choices=list(GROUPINGS),
                    help="Группировка по вкладкам (по умолчанию main_category = по рубрикам)")
    ap.add_argument("--save-html", help="Сохранить скачанный HTML в указанный файл")
    args = ap.parse_args(argv)

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8", errors="ignore")
        print(f"Читаю локальный HTML: {args.html}")
    else:
        print(f"Скачиваю {URL} ...")
        html = fetch_html()
        if args.save_html:
            Path(args.save_html).write_text(html, encoding="utf-8")
            print(f"HTML сохранён: {args.save_html}")

    exhibitors = parse_exhibitors(html, group=args.group)
    if not exhibitors:
        print("ВНИМАНИЕ: экспоненты не найдены — возможно, изменилась вёрстка сайта.",
              file=sys.stderr)
        return 1

    write_excel(exhibitors, args.out, GROUPINGS[args.group])

    # Краткая сводка в консоль
    by_rubric: dict[str, int] = {}
    for ex in exhibitors:
        by_rubric[ex.rubric] = by_rubric.get(ex.rubric, 0) + 1
    print(f"\nНайдено компаний: {len(exhibitors)} в {len(by_rubric)} рубриках")
    for rubric, n in by_rubric.items():
        print(f"  {n:4}  {rubric}")
    print(f"\nГотово -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
