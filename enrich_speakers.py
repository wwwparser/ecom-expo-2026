# -*- coding: utf-8 -*-
"""Обогащение спикеров соцсетями через выдачу XMLRiver.

По каждому спикеру ищем «Имя Фамилия должность компания» и вытаскиваем из выдачи
профили в соцсетях. Каждый спикер — один платный запрос (топ-10, Google, регион РФ).

Защита от однофамильцев: ссылка засчитывается, только если в title или URL
встречается фамилия, а в тексте выдачи — компания спикера. Иначе на сайт попадёт
чужой профиль, а проверять 156 карточек руками никто не будет.

Запуск: python enrich_speakers.py            # все, у кого ещё нет соцсетей
        python enrich_speakers.py --limit 10 # пилот
        python enrich_speakers.py --engine yandex
Выход:  data/raw/speaker_social.json (resume: уже обработанных не перезапрашиваем)
"""
import argparse
import concurrent.futures
import io
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from html import unescape

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "raw", "speaker_social.json")
PEOPLE = os.path.join(HERE, "data", "site", "people.json")

ENDPOINTS = {"google": "https://xmlriver.com/search/xml",
             "yandex": "https://xmlriver.com/search_yandex/xml"}
MAX_THREADS = 10
RESULTS_PER_PAGE = 10
# Россия: Criteria ID для Google country, lr для Яндекса
REGION = {"google": {"country": "2643", "lr": "ru"},
          "yandex": {"lr": "225", "lang": "ru"}}

NETWORKS = [
    ("t.me/", "Telegram"),
    ("vk.com/", "VK"),
    ("linkedin.com/in/", "LinkedIn"),
    ("habr.com/ru/users/", "Habr"),
    ("youtube.com/@", "YouTube"),
    ("dzen.ru/", "Дзен"),
    ("vc.ru/u/", "vc.ru"),
]

# Пилот показал: личных соцсетей у российских спикеров в выдаче почти нет
# (1 профиль на 8 человек), зато стабильно находятся страницы эксперта на сайте
# его компании, карточки на агрегаторах спикеров и программы других конференций.
# Поэтому собираем «где ещё про него написано», а не только соцсети.
PROFILE_HINTS = re.compile(
    r"/(experts?|speakers?|spiker|team|komanda|persons?|authors?|avtor)[/\-]", re.I)
CONFERENCE_HINTS = re.compile(
    r"(forum|conf|expo|summit|meetup|event|festival|prem)", re.I)

# Служебные разделы соцсетей — это не профиль человека.
JUNK = re.compile(r"(vk\.com/(video|wall|away|feed|club\d)|t\.me/(s/|joinchat|\+)"
                  r"|linkedin\.com/in/?$)", re.I)
# Сам источник данных — на сайт организаторов ссылаться незачем.
SELF = re.compile(r"expo\.oborot\.ru", re.I)
VIDEO = re.compile(r"(youtube\.com/watch|youtu\.be/|vkvideo\.ru/video|vk\.com/video|rutube\.ru/video)", re.I)


def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


class XmlRiverError(RuntimeError):
    pass


def decode(r):
    """Строго utf-8, запасной windows-1251. errors='ignore' убивает кириллицу."""
    for enc in ("utf-8", "windows-1251"):
        try:
            return r.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return r.content.decode("utf-8", "replace")


def raw_search(query, engine="google", retries=5):
    user, key = os.getenv("XMLRIVER_USER"), os.getenv("XMLRIVER_KEY")
    if not user or not key:
        raise RuntimeError("XMLRIVER_USER/XMLRIVER_KEY не заданы в .env")
    params = {"user": user, "key": key, "query": query,
              "groupby": RESULTS_PER_PAGE,
              "page": 1 if engine == "google" else 0}
    params.update(REGION[engine])

    last = ""
    for attempt in range(retries):
        try:
            r = requests.get(ENDPOINTS[engine], params=params, timeout=180)
        except requests.RequestException as e:
            last = str(e)
            time.sleep(4 * (attempt + 1))
            continue
        text = decode(r)
        m = re.search(r"<error[^>]*>(.*?)</error>", text, re.S)
        if not m:
            return text
        last = unescape(m.group(1)).strip()
        if attempt >= retries - 1:
            break
        # «заняты все каналы» — упёрлись в лимит потоков, короткий ретрай бесполезен
        time.sleep((15 if "канал" in last.lower() else 4) * (attempt + 1))
    raise XmlRiverError("XMLRiver [%s] «%s»: %s" % (engine, query, last))


def parse_serp(xml_text):
    root = ET.fromstring(xml_text)
    out = []
    for doc in root.iter("doc"):
        out.append({
            "url": doc.findtext("url", "") or "",
            "title": (doc.findtext("title", "") or "").strip(),
            "snippet": " ".join(p.text or "" for p in doc.iter("passage")).strip(),
        })
    return out


def company_of(role):
    """Последнее слово роли обычно и есть компания: «менеджер продукта Mindbox»."""
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9&.\-]{3,}", role or "")
    return words[-1].lower() if words else ""


# Служебные поддомены: по ним не понять источник, подпись берём следующим уровнем,
# иначе companies.rbc.ru подписывается как «Companies» вместо «Рбк».
GENERIC_SUB = {"www", "companies", "forum", "forums", "events", "event", "conf",
               "blog", "news", "m", "ru", "old", "new", "my", "lk"}


def pretty_source(url):
    """Подпись ссылки — значащая часть домена: mindbox.ru -> Mindbox."""
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    labels = [x for x in host.split(".") if x]
    while len(labels) > 2 and labels[0] in GENERIC_SUB:
        labels.pop(0)
    if labels and labels[0] in GENERIC_SUB and len(labels) > 1:
        labels.pop(0)
    return labels[0].capitalize() if labels else host


def pick_links(person, hits):
    """Что нашлось про спикера, с двойной проверкой: фамилия + компания.

    Без неё в выдаче по «Иван Петров директор» первым же результатом приходит
    однофамилец, и на карточке спикера оказывается посторонний человек. Имя
    должно встретиться в URL или заголовке, компания — где угодно в результате.

    Возвращает (ссылки, видео): видео уходят в отдельное поле карточки.
    """
    parts = person["name"].split()
    surname = parts[-1].lower() if parts else ""
    stem = surname[:-2] if len(surname) > 5 else surname  # склонения: Петрова/Петрову
    first = parts[0].lower() if parts else ""
    comp = company_of(person.get("role"))

    links, videos, seen = [], [], set()
    for h in hits:
        url = h["url"]
        if JUNK.search(url) or SELF.search(url):
            continue
        head = (url + " " + h["title"]).lower()
        low = head + " " + h["snippet"].lower()
        name_ok = bool(stem) and stem in head and (first in low or first in head)
        comp_ok = bool(comp) and comp in low
        if not (name_ok and comp_ok):
            continue

        base = url.split("?")[0].rstrip("/")
        if base in seen:
            continue
        seen.add(base)

        if VIDEO.search(base):
            videos.append({"url": base, "title": h["title"][:120] or "Выступление"})
            continue

        network = next((n for frag, n in NETWORKS if frag in base.lower()), "")
        if not network:
            if PROFILE_HINTS.search(base):
                network = pretty_source(base)
            elif CONFERENCE_HINTS.search(base):
                network = pretty_source(base)
            else:
                continue
        links.append({"network": network, "url": base})

    return links[:5], videos[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--engine", default="google", choices=list(ENDPOINTS))
    ap.add_argument("--threads", type=int, default=MAX_THREADS)
    a = ap.parse_args()

    load_env()
    with open(PEOPLE, encoding="utf-8") as f:
        people = json.load(f)

    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            done = json.load(f)

    todo = [p for p in people if p["name"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    print("спикеров всего %d, к запросу %d (по 1 платному запросу на каждого)"
          % (len(people), len(todo)))
    if not todo:
        return

    def work(p):
        query = "%s %s" % (p["name"], p.get("role") or "")
        try:
            hits = parse_serp(raw_search(query.strip(), a.engine))
        except Exception as e:
            return p["name"], {"error": str(e), "social": [], "videos": []}
        links, videos = pick_links(p, hits)
        return p["name"], {"social": links, "videos": videos, "hits": len(hits)}

    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.threads) as pool:
        for name, res in pool.map(work, todo):
            done[name] = res
            processed += 1
            mark = "!" if res.get("error") else " "
            print("%s[%d/%d] %-32s %d ссылок, %d видео"
                  % (mark, processed, len(todo), name[:32],
                     len(res["social"]), len(res.get("videos") or [])))
            if processed % 20 == 0:
                with open(OUT, "w", encoding="utf-8") as f:
                    json.dump(done, f, ensure_ascii=False, indent=1)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)

    got = sum(1 for v in done.values() if v.get("social") or v.get("videos"))
    errs = sum(1 for v in done.values() if v.get("error"))
    print("готово: ссылки нашлись у %d из %d, ошибок %d" % (got, len(done), errs))


if __name__ == "__main__":
    main()
