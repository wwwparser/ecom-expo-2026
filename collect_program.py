# -*- coding: utf-8 -*-
"""Сбор программы конференции ECOM Expo с главной страницы expo.oborot.ru.

Программа лежит в статическом HTML главной (SPA нет, внутреннего API нет):
  • шапка с залами         data-section-header-hall-id -> название и номер зала
  • секции  id="sec<ID>"   номер, название, время, спонсор, ведущий, доклады
  • доклады <li>           тема, спикер с должностью, ссылка /speaker-about/<p>/<t>/<s>

Карточки спикеров (фото, био, тезисы) докачиваются отдельно с паузами и resume.

Запуск:  python collect_program.py            # разобрать + докачать карточки
         python collect_program.py --no-cards # только разбор HTML
         python collect_program.py --refresh  # перекачать главную
Выход:   data/raw/program.json, data/raw/speaker_cards.json
"""
import io
import json
import os
import re
import sys
import time
import argparse

import requests
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw")
HOME = os.path.join(RAW, "home.html")
OUT_PROG = os.path.join(RAW, "program.json")
OUT_CARDS = os.path.join(RAW, "speaker_cards.json")
BASE = "https://expo.oborot.ru"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Referer": BASE + "/",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def fetch_home():
    """Скачивает главную. Сервер не шлёт charset, но отдаёт UTF-8 — декодируем явно,
    иначе requests угадывает cp1251 и весь русский текст превращается в мусор."""
    r = session().get(BASE + "/", timeout=90)
    r.raise_for_status()
    html = r.content.decode("utf-8")
    os.makedirs(RAW, exist_ok=True)
    with open(HOME, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def fix_brackets(s):
    """Ссылку «(подробнее)» вырезаем вместе с тегом, из-за чего у названий вида
    «Easy Commerce (ОККАМ)» отваливается закрывающая скобка. Возвращаем её."""
    s = clean(s).strip(" ()")
    if s.count("(") > s.count(")"):
        s += ")" * (s.count("(") - s.count(")"))
    return s


MONTHS = {"января": "01", "февраля": "02", "марта": "03", "апреля": "04",
          "мая": "05", "июня": "06", "июля": "07", "августа": "08",
          "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12"}


def parse_days(html):
    """Секция -> день. Дни размечены заголовками .ecom2021_progday_title
    («День 1 / 24 июня 2026»), после каждого идёт свой блок программы.

    Считаем по смещению в сыром HTML, а не по дереву: вёрстка не закрывает
    часть див��в, и любой парсер вытаскивает секции из блока дня наружу —
    через дерево они все оказываются в первом дне.
    """
    marks = []
    for m in re.finditer(r'ecom2021_progday_title.*?<h2[^>]*>(.*?)</h2>', html, re.S):
        raw = clean(re.sub(r"<[^>]+>", " ", m.group(1)))
        d = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", raw)
        iso = ""
        if d and d.group(2).lower() in MONTHS:
            iso = "%s-%s-%02d" % (d.group(3), MONTHS[d.group(2).lower()], int(d.group(1)))
        marks.append((m.start(), {"day": len(marks) + 1, "label": raw, "date": iso}))

    days = {}
    for m in re.finditer(r'id="(sec\d+)"', html):
        info = {}
        for pos, mark in marks:
            if pos < m.start():
                info = mark
        days[m.group(1)] = info
    return days


def parse_halls(soup):
    """Номер зала -> {title, number}. Шапка программы повторяется для каждого
    блока времени, поэтому берём первое вхождение каждого hall-id."""
    halls = {}
    for div in soup.select("div[data-section-header-hall-id]"):
        hid = div["data-section-header-hall-id"]
        if hid in halls:
            continue
        title = div.select_one(".ecom2021_hall_number_title")
        num = div.select_one(".ecom2021_hall_number_number")
        halls[hid] = {
            "title": clean(title.get_text() if title else ""),
            "number": clean(num.get_text() if num else ""),
        }
    return halls


def parse_talks(sec):
    """Доклады секции. В <li>: <b>тема</b>, после <br> — спикер с должностью,
    ссылка на карточку. Пустые <li> (только иконки) отбрасываем."""
    talks = []
    for li in sec.select("li"):
        b = li.find("b")
        title = clean(b.get_text()) if b else ""
        link = li.select_one("a.programme-speaker-about-url")
        # текст спикера — то, что осталось после удаления темы и служебных блоков
        tmp = BeautifulSoup(str(li), "html.parser")
        for junk in tmp.select("b, a, .programme__doklad-icons"):
            junk.decompose()
        speaker = fix_brackets(tmp.get_text())
        if not title and not speaker:
            continue
        talks.append({
            "title": title,
            "speaker_raw": speaker,
            "card_url": link["href"] if link else "",
        })
    return talks


def parse_leaders(sec):
    """Ведущие секции: блок .prog_leader, строки «Имя, должность (подробнее)»."""
    out = []
    for block in sec.select(".prog_leader"):
        tmp = BeautifulSoup(str(block), "html.parser")
        for junk in tmp.select("b, a"):
            junk.decompose()
        name = fix_brackets(tmp.get_text())
        link = block.select_one("a.programme-leader-about-url")
        if name:
            out.append({"name_raw": name, "card_url": link["href"] if link else ""})
    return out


def parse_sponsors(sec):
    out = []
    for sp in sec.select(".prog_sponsor"):
        a = sp.find("a", href=True)
        img = sp.find("img")
        label = sp.select_one(".sect_sponsor_text")
        src = img.get("src", "") if img else ""
        out.append({
            "label": clean(label.get_text(separator=" ") if label else ""),
            "url": a["href"] if a else "",
            "logo": (BASE + src) if src.startswith("/") else src,
        })
    return out


def parse_program(html):
    soup = BeautifulSoup(html, "html.parser")
    halls = parse_halls(soup)
    days = parse_days(html)
    sections = []
    seen = set()
    for sec in soup.select('div[id^="sec"]'):
        sid = sec.get("id", "")
        if not re.fullmatch(r"sec\d+", sid) or sid in seen:
            continue
        seen.add(sid)
        title_el = (sec.select_one(".ecom2021_section_title")
                    or sec.select_one(".prog-section__title_mobile"))
        title = clean(title_el.get_text()) if title_el else ""
        # «1.1 Продающий контент» -> номер + чистое название
        m = re.match(r"^(\d+\.\d+)\s+(.*)$", title)
        number, name = (m.group(1), m.group(2)) if m else ("", title)
        time_el = sec.select_one(".prog_sect_time_start")
        hall_id = sec.get("data-section-hall", "")
        day = days.get(sid, {})
        sections.append({
            "id": sid.replace("sec", ""),
            "day": day.get("day", 0),
            "date": day.get("date", ""),
            "day_label": day.get("label", ""),
            "number": number,
            "title": name,
            "time": clean(time_el.get_text()) if time_el else "",
            "hall_id": hall_id,
            "hall": halls.get(hall_id, {}),
            "sponsors": parse_sponsors(sec),
            "leaders": parse_leaders(sec),
            "talks": parse_talks(sec),
        })
    return {"halls": halls, "sections": sections}


def fetch_cards(program, pause=0.7):
    """Докачивает карточки спикеров и ведущих. Resume: уже скачанные пропускаем."""
    cards = {}
    if os.path.exists(OUT_CARDS):
        with open(OUT_CARDS, encoding="utf-8") as f:
            cards = json.load(f)

    urls = []
    for sec in program["sections"]:
        for t in sec["talks"]:
            if t["card_url"]:
                urls.append(t["card_url"])
        for lead in sec["leaders"]:
            if lead["card_url"]:
                urls.append(lead["card_url"])
    urls = [u for u in dict.fromkeys(urls) if u not in cards]
    print("карточек к загрузке: %d" % len(urls))

    s = session()
    for i, u in enumerate(urls, 1):
        try:
            r = s.get(BASE + u, timeout=30)
            soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
            img = soup.select_one(".about-speaker-photo")
            src = img.get("src", "") if img else ""

            def txt(cls, sep=" "):
                el = soup.select_one(cls)
                return clean(el.get_text(separator=sep)) if el else ""

            cards[u] = {
                "photo": (BASE + src) if src.startswith("/") else src,
                "theme": txt(".about-speaker-theme"),
                "name": txt(".about-speaker-name"),
                "profile": txt(".about-speaker-profile"),
                "section": txt(".about-speaker-section"),
                # именно __content: .about-speaker-theses — это заголовок
                # «Тезисы доклада:», сам список лежит уровнем ниже
                "theses": txt(".about-speaker-theses__content"),
            }
            print("[%d/%d] %s" % (i, len(urls), cards[u]["name"][:60]))
        except Exception as e:
            print("[%d/%d] ОШИБКА %s: %s" % (i, len(urls), u, e))
            cards[u] = {"error": str(e)}

        if i % 20 == 0:
            with open(OUT_CARDS, "w", encoding="utf-8") as f:
                json.dump(cards, f, ensure_ascii=False, indent=1)
        time.sleep(pause)

    with open(OUT_CARDS, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=1)
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="перекачать главную")
    a = ap.parse_args()

    if a.refresh or not os.path.exists(HOME):
        print("качаю главную…")
        html = fetch_home()
    else:
        with open(HOME, encoding="utf-8") as f:
            html = f.read()
    print("HTML: %d символов" % len(html))

    prog = parse_program(html)
    talks = sum(len(s["talks"]) for s in prog["sections"])
    print("залов: %d, секций: %d, докладов: %d"
          % (len(prog["halls"]), len(prog["sections"]), talks))
    with open(OUT_PROG, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=1)

    if not a.no_cards:
        cards = fetch_cards(prog)
        print("карточек всего: %d" % len(cards))


if __name__ == "__main__":
    main()
