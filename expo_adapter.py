# -*- coding: utf-8 -*-
"""Адаптер: данные проекта -> контракт скилла expo-site (data/site/*.json).

Источники (всё уже собрано в этом проекте):
  exhibitors_ecom_expo_2026.xlsx   участники 2026 по рубрикам
  contacts_out/contacts.jsonl      контакты и соцсети участников 2026
  archive_contacts_out/…           то же по архиву
  archive_participants.jsonl       5534 участия за 2015-2026
  archive_topics.jsonl             тематика домена (классификация DeepSeek)
  tg_channels.json                 компания -> telegram-канал
  tg_results.jsonl                 посты каналов, приглашения, розыгрыши
  data/raw/program.json            программа конференции (collect_program.py)
  data/raw/speaker_cards.json      карточки спикеров: фото, био, тезисы

Решение по приватности: на сайт идут только сайт и соцсети. Почты и телефоны
собраны, но не публикуются — открытый репозиторий сразу становится базой
для спам-рассылок.

Запуск: python expo_adapter.py
"""
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

import openpyxl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "data", "site")
RAW = os.path.join(HERE, "data", "raw")
CONTENT = os.path.join(HERE, "content")

YEAR = 2026
EXPO_DATES = ("2026-06-24", "2026-06-25")


# ------------------------------------------------------------------ утилиты

def jsonl(path):
    out = []
    full = os.path.join(HERE, path)
    if not os.path.exists(full):
        return out
    with open(full, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def load_json(path, default=None):
    full = os.path.join(HERE, path)
    if not os.path.exists(full):
        return default
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def dump(name, data):
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    n = len(data) if isinstance(data, list) else 1
    print("  %-18s %s" % (name, n if isinstance(data, list) else "ok"))


def domain(url):
    """Домен без www и схемы — ключ сопоставления компаний между источниками.
    Название пишут по-разному («ООО Ромашка» / «Ромашка»), домен стабилен."""
    if not url:
        return ""
    u = re.sub(r"^https?://", "", url.strip().lower())
    u = u.split("/")[0].split("?")[0]
    return u[4:] if u.startswith("www.") else u


def norm_name(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r'\b(ооо|оао|зао|ип|ao|llc|ltd|inc)\b', " ", s)
    return re.sub(r"[^a-zа-я0-9]+", "", s)


# WhatsApp сознательно не берём: ссылка wa.me/api.whatsapp.com несёт в себе
# номер телефона, а телефоны мы не публикуем.
SOCIAL_FIELDS = [("telegram", "Telegram"), ("vk", "VK"), ("instagram", "Instagram"),
                 ("facebook", "Facebook"), ("ok", "OK"), ("max", "MAX")]


# t.me/+79991234567 — это не имя канала, а телефон в виде ссылки-приглашения.
# Такие ссылки отбрасываем вместе с обычными телефонами.
PHONE_LINK = re.compile(r"(t(elegram)?\.me|wa\.me|api\.whatsapp\.com)/?.*?\+?\d{10,}", re.I)


def social_from_contact(rec):
    """Соцсети в публикацию. Почты и телефоны сознательно не берём."""
    out = []
    seen = set()
    for field, label in SOCIAL_FIELDS:
        for url in (rec.get(field) or [])[:2]:
            if not url or url in seen or PHONE_LINK.search(url):
                continue
            seen.add(url)
            out.append({"network": label, "url": url})
    return out


# ------------------------------------------------------------------ источники

def read_exhibitors_xlsx():
    """Участники 2026. Первый лист — сводка, дальше по листу на рубрику."""
    path = os.path.join(HERE, "exhibitors_ecom_expo_2026.xlsx")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = []
    for sheet in wb.sheetnames[1:]:
        ws = wb[sheet]
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 or not r or not r[0]:
                continue
            rows.append({
                "name": str(r[0]).strip(),
                "site": (str(r[1]).strip() if r[1] else ""),
                "booth": (str(r[2]).strip() if r[2] else ""),
                "descr": (str(r[3]).strip() if r[3] else ""),
                "marketplace": bool(r[4]),
                "own_channel": bool(r[5]),
                "eid": (str(r[6]).strip() if len(r) > 6 and r[6] else ""),
                "group": sheet,
            })
    wb.close()
    return rows


def index_contacts():
    """Домен -> запись контактов. 2026 приоритетнее архивной."""
    idx = {}
    for path in ("archive_contacts_out/contacts.jsonl", "contacts_out/contacts.jsonl"):
        for rec in jsonl(path):
            d = domain(rec.get("site") or rec.get("home"))
            if d:
                idx[d] = rec
    return idx


def index_tg():
    """Компания (нормализованное имя) -> данные телеграм-канала."""
    by_name = {}
    results = {r["username"]: r for r in jsonl("tg_results.jsonl")}
    for ch in load_json("tg_channels.json", []) or []:
        key = norm_name(ch.get("company"))
        if not key:
            continue
        rec = dict(ch)
        rec.update(results.get(ch["username"], {}))
        by_name[key] = rec
    return by_name


def archive_history():
    """Домен и имя -> список лет участия. Домен надёжнее, имя — запасной ключ."""
    by_domain, by_name = defaultdict(set), defaultdict(set)
    for rec in jsonl("archive_participants.jsonl"):
        year = rec.get("year")
        d = domain(rec.get("site"))
        if d:
            by_domain[d].add(year)
        by_name[norm_name(rec.get("name"))].add(year)
    return by_domain, by_name


def topics_by_domain():
    return {r["domain"]: r["topic"] for r in jsonl("archive_topics.jsonl") if r.get("domain")}


# ------------------------------------------------------------------ участники

def build_exhibitors():
    rows = read_exhibitors_xlsx()
    contacts = index_contacts()
    tg = index_tg()
    hist_d, hist_n = archive_history()

    merged = {}
    for r in rows:
        d = domain(r["site"])
        key = d or norm_name(r["name"])
        if key in merged:
            # компания в нескольких рубриках — копим стенды и рубрики
            m = merged[key]
            if r["booth"] and r["booth"] not in m["stands"]:
                m["stands"].append(r["booth"])
            if r["group"] not in m["groups"]:
                m["groups"].append(r["group"])
            continue

        years = sorted(hist_d.get(d) or hist_n.get(norm_name(r["name"])) or [])
        years = [y for y in years if y != YEAR]
        c = contacts.get(d, {})
        social = social_from_contact(c)
        chan = tg.get(norm_name(r["name"]))
        if chan:
            url = "https://t.me/%s" % chan["username"]
            if not any(s["url"].rstrip("/").lower() == url.lower() for s in social):
                social.insert(0, {"network": "Telegram", "url": url})

        about = r["descr"] or c.get("description") or c.get("meta_desc") or ""
        merged[key] = {
            "name": r["name"],
            "group": r["group"],
            "groups": [r["group"]],
            "stands": [r["booth"]] if r["booth"] else [],
            "zone": "",
            "about": about,
            "website": r["site"],
            "contacts": {"emails": [], "phones": [], "social": social},
            "years": years,
            "marketplace": r["marketplace"],
            "own_channel": r["own_channel"],
            "telegram": chan["username"] if chan else "",
            "giveaway": bool(chan and chan.get("giveaway")),
            "giveaway_what": (chan or {}).get("giveaway_what", ""),
        }

    out = []
    for x in merged.values():
        bits = []
        if x["years"]:
            bits.append("На ECOM Expo %d-й раз, впервые в %d." % (len(x["years"]) + 1, min(x["years"])))
        if len(x["groups"]) > 1:
            bits.append("Рубрики: " + ", ".join(x["groups"]) + ".")
        if x["giveaway"] and x["giveaway_what"]:
            bits.append("Розыгрыш на стенде: " + x["giveaway_what"] + ".")
        if bits:
            x["about"] = re.sub(r"\s+", " ", x["about"] + " " + " ".join(bits)).strip()
        out.append(x)

    out.sort(key=lambda i: i["name"].lower())
    return out


# ------------------------------------------------------------------ программа

def split_person(raw):
    """«Марина Каганова, руководитель группы Авито» -> имя и должность.
    Имя — первые два-три слова до запятой; всё после — роль."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    if "," in raw:
        name, role = raw.split(",", 1)
        return name.strip(), role.strip()
    parts = raw.split()
    if len(parts) >= 2:
        return " ".join(parts[:2]), " ".join(parts[2:])
    return raw, ""


def theses_html(raw):
    """Тезисы приходят одной строкой с маркерами «•» — разворачиваем в список."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    points = [p.strip(" ;–-") for p in re.split(r"\s*[•·]\s*", raw) if p.strip(" ;–-")]
    if len(points) < 2:
        return '<div class="small">%s</div>' % raw
    return ('<ul class="small">%s</ul>'
            % "".join("<li>%s</li>" % p for p in points))


def build_program():
    prog = load_json("data/raw/program.json", {"sections": [], "halls": {}})
    cards = load_json("data/raw/speaker_cards.json", {}) or {}

    events, people = [], {}

    for sec in prog["sections"]:
        hall = sec.get("hall") or {}
        venue = " — ".join(x for x in [hall.get("number"), hall.get("title")] if x)
        start, _, end = (sec.get("time") or "").partition("-")

        ev_people, talk_html = [], []
        for role_kind, entries in (("Ведущий", sec.get("leaders") or []),
                                   ("Спикер", sec.get("talks") or [])):
            for t in entries:
                raw = t.get("speaker_raw") or t.get("name_raw") or ""
                card = cards.get(t.get("card_url") or "", {})
                name, role = split_person(card.get("name") or raw)
                if not name:
                    continue
                p = people.setdefault(name, {
                    "name": name, "role": role, "photo": card.get("photo", ""),
                    "bio": card.get("profile", ""), "social": [], "events": [], "videos": [],
                })
                if not p["bio"] and card.get("profile"):
                    p["bio"] = card["profile"]
                if not p["photo"] and card.get("photo"):
                    p["photo"] = card["photo"]
                p["events"].append({"id": sec["id"], "title": sec["title"],
                                    "date": sec.get("date", ""), "venue": venue})
                ev_people.append({"name": name, "role": role, "page": True, "links": ""})

                if role_kind == "Спикер":
                    talk_html.append(
                        '<li><b>%s</b><br><span class="small">%s</span>%s</li>'
                        % (t.get("title") or "", raw, theses_html(card.get("theses"))))

        leaders = ", ".join(split_person(l.get("name_raw"))[0] for l in (sec.get("leaders") or []))
        descr = []
        if leaders:
            descr.append("<p><b>Ведущий секции:</b> %s</p>" % leaders)
        for sp in sec.get("sponsors") or []:
            if sp.get("url"):
                descr.append('<p class="small">%s: <a href="%s" rel="nofollow noopener" '
                             'target="_blank">%s</a></p>'
                             % (sp.get("label") or "Партнёр", sp["url"], domain(sp["url"])))
        if talk_html:
            descr.append("<h2>Доклады</h2><ul>%s</ul>" % "".join(talk_html))

        events.append({
            "id": sec["id"],
            "title": ("%s %s" % (sec.get("number", ""), sec["title"])).strip(),
            "date": sec.get("date", ""),
            "start": start.strip(),
            "end": end.strip(),
            "venue": venue,
            "kind": hall.get("title", ""),
            "topic": "",
            "description": "".join(descr),
            "organizers": [],
            "people": ev_people,
            "links": [],
            "source_url": "https://expo.oborot.ru/#sec%s" % sec["id"],
        })

    events.sort(key=lambda e: (e["date"], e["start"], e["venue"]))
    plist = sorted(people.values(), key=lambda p: p["name"])

    # внешние ссылки и видео, найденные через выдачу (enrich_speakers.py)
    extra = load_json("data/raw/speaker_social.json", {}) or {}
    for p in plist:
        found = extra.get(p["name"]) or {}
        p["social"] = found.get("social") or []
        p["videos"] = found.get("videos") or []
    return events, plist


# ------------------------------------------------------------------ лента

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?[78][\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")


def scrub(text):
    """Компании иногда оставляют почту и телефон прямо в тексте поста.
    Пост публичный, но выкладывать контакты мы не договаривались — прячем."""
    text = EMAIL_RE.sub("[почта — в канале]", text or "")
    return PHONE_RE.sub("[телефон — в канале]", text)


def build_feed():
    """Лента последних постов Telegram-каналов участников, по дням.

    Источник — data/raw/channel_posts.json (collect_channel_posts.py): у постов
    есть дата со временем и просмотры, поэтому генератор раскладывает их по дням.
    Группа поста — рубрика компании, чтобы ленту можно было фильтровать.
    """
    data = load_json("data/raw/channel_posts.json", {}) or {}
    posts = []
    for rec in data.values():
        stand = ", ".join(rec.get("stands") or [])
        for p in rec.get("posts") or []:
            text = scrub(p.get("text") or "").strip()
            if not text:
                continue  # посты из одних картинок в текстовой ленте бесполезны
            posts.append({
                "date": p.get("datetime") or "",
                "text": text[:1500],
                "views": p.get("views"),
                "url": p.get("url") or "",
                "channel": rec.get("company") or rec["username"],
                "channel_url": "https://t.me/%s" % rec["username"],
                "author": ("стенд %s" % stand) if stand else "",
                "group": rec.get("group") or "",
            })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def build_giveaways():
    """Посты участников: приглашения на стенд и розыгрыши в дни выставки."""
    posts = []
    for r in jsonl("tg_results.jsonl"):
        company = r.get("company") or r.get("username")
        base = {"channel": company,
                "channel_url": "https://t.me/%s" % r["username"],
                "author": company,
                "views": None,
                "date": r.get("last_date") or EXPO_DATES[0]}
        if r.get("invites_ecom_expo") and (r.get("expo_post_text") or r.get("expo_quote")):
            p = dict(base)
            p["group"] = "Приглашения на стенд"
            p["text"] = scrub(r.get("expo_post_text") or r.get("expo_quote"))[:1200]
            p["url"] = r.get("expo_link") or base["channel_url"]
            posts.append(p)
        if r.get("giveaway") and (r.get("giveaway_post_text") or r.get("giveaway_what")):
            p = dict(base)
            p["group"] = "Розыгрыши и мерч"
            what = r.get("giveaway_what") or ""
            cond = r.get("giveaway_conditions") or ""
            body = r.get("giveaway_post_text") or ""
            p["text"] = ("Разыгрывают: %s. %s\n\n%s" % (what, cond, body)).strip()[:1200]
            p["url"] = r.get("giveaway_link") or base["channel_url"]
            posts.append(p)
    posts.sort(key=lambda p: (p["group"], p["channel"]))
    return posts


# ------------------------------------------------------------------ мета

def company_key(name, site):
    """Ключ компании между годами: домен, а если сайта нет — нормализованное имя."""
    return domain(site) or norm_name(name)


def all_participations(exhibitors):
    """Все участия 2015-2026. В archive_participants.jsonl лежат только архивные
    годы (по 2025), участники текущего года приходят из xlsx — сводим вместе,
    иначе «11 лет выставки» считаются по десяти.

    В архиве компания встречается в году по разу на каждую свою рубрику,
    поэтому пары «компания + год» дедуплицируем: иначе 2024 год показывает
    1094 участника вместо 251.
    """
    seen, rows = set(), []
    src = [(p.get("name"), p.get("site"), p.get("year"))
           for p in jsonl("archive_participants.jsonl")]
    src += [(x["name"], x["website"], YEAR) for x in exhibitors]
    for name, site, year in src:
        key = company_key(name, site)
        if (key, year) in seen:
            continue
        seen.add((key, year))
        rows.append({"key": key, "name": name, "year": year})
    return rows


def build_meta(exhibitors, events, people, feed, giveaways, channels, book=None):
    parts = all_participations(exhibitors)
    topics = topics_by_domain()

    years = Counter(p["year"] for p in parts)
    by_company = defaultdict(set)
    names = {}
    for p in parts:
        by_company[p["key"]].add(p["year"])
        names.setdefault(p["key"], p["name"])

    veterans = sorted(by_company.items(), key=lambda kv: (-len(kv[1]), names.get(kv[0], "")))
    top_rows = [[names.get(k, k), len(v)] for k, v in veterans[:15]]

    # Разрезы генератор сортирует по величине — для ряда по годам это ломает
    # хронологию, поэтому таблицу лет собираем сами и отдаём через meta.body.
    firsts, seen = {}, set()
    per_year = defaultdict(set)
    for p in parts:
        per_year[p["year"]].add(p["key"])
    for y in sorted(per_year):
        firsts[y] = len(per_year[y] - seen)
        seen |= per_year[y]

    mx = max(years.values())
    year_html = "".join(
        '<tr><td>%d</td><td>%d</td><td>%d</td>'
        '<td style="width:44%%"><i class="bar" style="width:%d%%"></i></td></tr>'
        % (y, years[y], firsts[y], max(2, years[y] * 100 // mx))
        for y in sorted(years))
    years_body = (
        '<h2 id="years">Сколько компаний приезжало по годам</h2>'
        '<div class="wrap"><table>'
        '<tr><th>Год</th><th>участников</th><th>из них впервые</th><th></th></tr>'
        '%s</table></div>'
        '<p class="small muted">2018 и 2019 годы организаторы убрали из открытого '
        'архива — это пропуск в данных, а не отменённая выставка.</p>' % year_html)

    group_rows = Counter(x["group"] for x in exhibitors).most_common()

    topic_rows = Counter(t for d, t in topics.items() if t).most_common(12)

    hall_rows = Counter(e["kind"] for e in events if e["kind"]).most_common()

    give = sum(1 for p in giveaways if p["group"] == "Розыгрыши и мерч")
    with_tg = sum(1 for x in exhibitors if x.get("telegram"))

    return {
        "title": "ECOM Expo’26 — независимый разбор выставки",
        "short_title": "ECOM Expo’26",
        "brand_note": "разбор выставки",
        "h1": "ECOM Expo’26: участники, программа и десять лет истории",
        "lead": ("Выставка технологий для электронной торговли, 24–25 июня 2026, "
                 "Москва. Здесь собрана программа всех залов, участники со стендами "
                 "и соцсетями, спикеры, а также архив выставки с 2015 года — "
                 "кто приезжает каждый год, а кто исчез бесследно."),
        "disclaimer": ("Независимый разбор по открытым данным сайта организаторов "
                       "и публичным Telegram-каналам участников. Это не официальный сайт "
                       "ECOM Expo."),
        "stats": [
            {"value": len(exhibitors), "label": "участников 2026", "href": "exhibitors"},
            {"value": len(events), "label": "секций программы", "href": "events"},
            {"value": len(people), "label": "спикеров", "href": "people"},
            {"value": len(by_company), "label": "компаний с 2015 года", "href": "archive"},
            {"value": len(parts), "label": "участий за 10 выпусков", "href": "archive"},
            {"value": channels, "label": "каналов участников", "href": "channels"},
            {"value": len(feed), "label": "постов в ленте", "href": "feed"},
        ],
        "breakdowns": [
            {"title": "Участники 2026 по рубрикам", "anchor": "groups",
             "head": "Рубрика", "unit": "компаний", "rows": group_rows},
            {"title": "Программа по потокам", "anchor": "halls",
             "head": "Поток", "unit": "секций", "rows": hall_rows},
            {"title": "Старожилы: больше всего участий", "anchor": "veterans",
             "head": "Компания", "unit": "лет на выставке", "rows": top_rows},
            {"title": "Чем занимаются участники (по данным их сайтов)", "anchor": "topics",
             "head": "Тематика", "unit": "компаний", "rows": topic_rows},
        ],
        "cards": [
            ["events", "Программа двух дней", "%d секций в 6 потоках, фильтры по дню и залу" % len(events)],
            ["exhibitors", "Участники", "%d компаний со стендами, сайтами и соцсетями" % len(exhibitors)],
            ["people", "Спикеры", "%d выступающих с биографиями и темами" % len(people)],
            ["feed", "Лента каналов", "Последние посты %d каналов участников по дням" % channels],
            ["articles", "Разборы", "Выставка в цифрах: кто держится десять лет, а кого вымыло"],
        ] + ([["book.html", "Книга «Ecom 2026»",
               "%d глав по всей программе, %d докладов — читать онлайн или скачать PDF"
               % (book["chapters"], book["talks"])]] if book else []) + [
        ],
        "events_page": "program.html",
        "events_nav": "Программа",
        "events_title": "Программа конференции",
        "exhibitors_nav": "Участники",
        "exhibitors_title": "Участники выставки",
        "people_nav": "Спикеры",
        "people_title": "Спикеры",
        "feed_nav": "Лента",
        "feed_title": "Лента каналов участников",
        "articles_nav": "Разборы",
        "articles_title": "Разборы",
        "articles_lead": "Что видно в данных за одиннадцать лет выставки.",
        "exhibitor_groups": [g for g, _ in group_rows],
        "index_title": "ECOM Expo’26 в цифрах",
        "assets": ["book/ecom-2026.html", "book/ecom-2026.pdf"] if book else [],
        "body": years_body,
        "telegram_channels": with_tg,
    }


ARCHIVE_HEAD = """<h1>Архив выставки, 2015–2026</h1>
<p class="lead">%(companies)s компаний и %(rows)s участий за одиннадцать выпусков.
Фильтр по году и поиск по названию работают без перезагрузки.
Годы 2018 и 2019 организаторы из открытого доступа убрали — это пропуск в данных,
а не отсутствие выставки.</p>
<div class="filters">%(select)s<input id="aq" placeholder="Поиск по компании…"></div>
<p class="muted small" id="ac"></p>
<div class="wrap"><table id="atable">
<tr><th>Компания</th><th>Участий</th><th>Годы</th><th>Сайт</th></tr>
%(rows_html)s
</table></div>
<script>
(function () {
  var q = document.getElementById('aq'), sel = document.getElementById('ay'),
      rows = [].slice.call(document.querySelectorAll('#atable tr[data-s]')),
      out = document.getElementById('ac');
  function apply() {
    var text = q.value.trim().toLowerCase(), year = sel.value, n = 0;
    rows.forEach(function (r) {
      var ok = (!text || r.dataset.s.indexOf(text) > -1) &&
               (!year || r.dataset.years.split(' ').indexOf(year) > -1);
      r.hidden = !ok;
      if (ok) n++;
    });
    out.textContent = n + ' из ' + rows.length;
  }
  q.addEventListener('input', apply);
  sel.addEventListener('change', apply);
  apply();
})();
</script>"""


def build_archive_page(exhibitors):
    """Отдельная страница архива: генератор такой раздел не умеет, поэтому
    собираем готовый HTML и отдаём его как авторскую страницу (pages.json)."""
    parts = all_participations(exhibitors)
    by_company = defaultdict(set)
    names, sites = {}, {}
    for p in parts:
        by_company[p["key"]].add(p["year"])
        names.setdefault(p["key"], p["name"])
    for p in jsonl("archive_participants.jsonl"):
        k = company_key(p.get("name"), p.get("site"))
        if p.get("site") and k not in sites:
            sites[k] = p["site"]
    for x in exhibitors:
        k = company_key(x["name"], x["website"])
        if x["website"]:
            sites[k] = x["website"]

    def esc(s):
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    ordered = sorted(by_company.items(),
                     key=lambda kv: (-len(kv[1]), names.get(kv[0], "").lower()))
    all_years = sorted({y for ys in by_company.values() for y in ys})

    rows_html = []
    for key, ys in ordered:
        years = sorted(ys)
        site = sites.get(key, "")
        link = ('<a href="%s" rel="nofollow noopener" target="_blank">%s</a>'
                % (esc(site), esc(domain(site)))) if site else '<span class="muted">—</span>'
        current = ' <span class="tag">2026</span>' if YEAR in ys else ""
        rows_html.append(
            '<tr data-s="%s" data-years="%s"><td><b>%s</b>%s</td>'
            '<td>%d</td><td class="small">%s</td><td class="small">%s</td></tr>'
            % (esc(names.get(key, "").lower()), " ".join(str(y) for y in years),
               esc(names.get(key, "")), current, len(years),
               ", ".join(str(y) for y in years), link))

    select = ('<select id="ay"><option value="">Все годы</option>%s</select>'
              % "".join('<option value="%d">%d</option>' % (y, y) for y in all_years))

    html = ARCHIVE_HEAD % {
        "companies": len(by_company),
        "rows": len(parts),
        "select": select,
        "rows_html": "".join(rows_html),
    }
    os.makedirs(CONTENT, exist_ok=True)
    with open(os.path.join(CONTENT, "archive.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  content/archive.html  %d компаний" % len(by_company))
    return len(by_company), len(parts)


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


CHANNELS_PAGE = """<h1>Telegram-каналы участников</h1>
<p class="lead">%(with_posts)s каналов компаний, стоящих на ECOM Expo’26: последние
посты, рубрика и номер стенда. Свежие сообщения всех каналов собраны
в <a href="feed.html">ленте по дням</a>.</p>
<div class="filters">%(select)s<input id="cq" placeholder="Поиск по компании или каналу…"></div>
<p class="muted small" id="cc"></p>
<div class="wrap"><table id="ctable">
<tr><th>Компания</th><th>Канал</th><th>Стенд</th><th>Постов</th><th>Последний пост</th></tr>
%(rows)s
</table></div>
<p class="small muted">Ещё у %(no_preview)s компаний в списке участников указан
телеграм-адрес, но публичной ленты по нему нет: это личные аккаунты менеджеров
или закрытые каналы — их посты недоступны и в подборку не попали.</p>
<script>
(function () {
  var q = document.getElementById('cq'), sel = document.getElementById('cg'),
      rows = [].slice.call(document.querySelectorAll('#ctable tr[data-s]')),
      out = document.getElementById('cc');
  function apply() {
    var text = q.value.trim().toLowerCase(), g = sel.value, n = 0;
    rows.forEach(function (r) {
      var ok = (!text || r.dataset.s.indexOf(text) > -1) && (!g || r.dataset.g === g);
      r.hidden = !ok;
      if (ok) n++;
    });
    out.textContent = n + ' из ' + rows.length;
  }
  q.addEventListener('input', apply);
  sel.addEventListener('change', apply);
  apply();
})();
</script>"""


def build_channels_page():
    """Каталог каналов участников — отдельная страница (генератор такой не умеет)."""
    data = load_json("data/raw/channel_posts.json", {}) or {}
    live = [r for r in data.values() if r.get("posts")]
    live.sort(key=lambda r: (r.get("company") or "").lower())

    rows, groups = [], set()
    for r in live:
        posts = r["posts"]
        last = max((p.get("datetime") or "")[:10] for p in posts)
        group = r.get("group") or ""
        groups.add(group)
        rows.append(
            '<tr data-s="%s" data-g="%s"><td><b>%s</b><br>'
            '<span class="small muted">%s</span></td>'
            '<td><a href="https://t.me/%s" rel="nofollow noopener" target="_blank">@%s</a></td>'
            '<td class="small">%s</td><td>%d</td><td class="small">%s</td></tr>'
            % (esc((r.get("company", "") + " " + r["username"]).lower()), esc(group),
               esc(r.get("company", "")), esc(group), esc(r["username"]), esc(r["username"]),
               esc(", ".join(r.get("stands") or []) or "—"), len(posts), esc(last)))

    select = ('<select id="cg"><option value="">Все рубрики</option>%s</select>'
              % "".join('<option value="%s">%s</option>' % (esc(g), esc(g))
                        for g in sorted(x for x in groups if x)))

    html = CHANNELS_PAGE % {
        "with_posts": len(live),
        "no_preview": len(data) - len(live),
        "select": select,
        "rows": "".join(rows),
    }
    os.makedirs(CONTENT, exist_ok=True)
    with open(os.path.join(CONTENT, "channels.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  content/channels.html %d каналов" % len(live))
    return len(live)


def plural(n, one, few, many):
    """33 главы, 21 глава, 148 докладов — без этого в лиде «33 глав»."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return "%d %s" % (n, one)
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return "%d %s" % (n, few)
    return "%d %s" % (n, many)


def build_book_page():
    """Страница книги: аннотация, состав частей и ссылки на онлайн-версию и PDF.

    Саму книгу не встраиваем в шаблон сайта: у неё своя печатная вёрстка,
    и в assets она лежит самостоятельным файлом, который открывается как есть.
    Возвращает None, если книга ещё не собрана (build_book.py не запускали).
    """
    html_path = os.path.join(HERE, "book", "ecom-2026.html")
    pdf_path = os.path.join(HERE, "book", "ecom-2026.pdf")
    if not os.path.exists(html_path):
        return None

    chapters = load_json("data/raw/book_chapters.json", {}) or {}
    talks = sum(c.get("talks", 0) for c in chapters.values())
    pages = ""
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            blob = f.read()
        pages = len(re.findall(rb"/Type\s*/Page[^s]", blob))
        size_mb = len(blob) / 1048576

    parts = [
        ("Часть I. О чём эта книга", "Что за выставка, как устроен разбор и откуда данные."),
        ("Часть II. Выставка в цифрах",
         "Масштаб события, рубрики стендов, темы докладов и одиннадцать лет истории участников."),
        ("Часть III. Маркетплейсы",
         "Восемь секций: контент карточки, продвижение и аналитика селлера, "
         "операционка, контрактное производство, ИИ на службе селлера."),
        ("Часть IV. Маркетинг и продажи",
         "Одиннадцать секций: инфлюенс-маркетинг, лояльность и повторные продажи, "
         "трафик и воронка, конверсия и средний чек, ИИ в маркетинге, бренд и СТМ."),
        ("Часть V. Логистика, платежи и операции",
         "Семь секций: логистическая эффективность, последняя миля, склад, "
         "платежи и кассы, финансовые инструменты, зарубежные поставщики."),
        ("Часть VI. ИТ и разработка",
         "Пять секций: интеграции и бэкенд, внешняя разработка и поддержка, "
         "автоматизация логистики."),
        ("Часть VII. Право, налоги и кадры",
         "Две секции совмещённого потока: споры с площадками, интеллектуальная "
         "собственность, налоги, бухгалтерия и наём."),
        ("Приложение", "Справочник 205 участников по рубрикам: стенд, профиль, "
                       "сколько раз компания была на выставке."),
    ]
    rows = "".join('<div class="card"><h3>%s</h3><p class="small">%s</p></div>'
                   % (esc(t), esc(d)) for t, d in parts)

    size_note = (" Объём — %s." % plural(pages, "страница", "страницы", "страниц")) if pages else ""

    html = """<style>
/* Класса .btn в теме сайта нет, а ссылки на книгу должны читаться как действия.
   Цвета берём из переменных темы, чтобы кнопки работали и в тёмном режиме. */
.book-actions { display: flex; gap: 10px; flex-wrap: wrap; margin: 18px 0 26px; }
.book-actions a { display: inline-block; padding: 10px 18px; border-radius: 8px;
  text-decoration: none; border: 1px solid var(--acc); font-weight: 600; }
.book-actions .primary { background: var(--acc); color: var(--bg); }
.book-actions .secondary { color: var(--acc); background: transparent; }
.book-actions a:hover { opacity: .85; }
</style>

<h1>Ecom 2026 — книга-обзор выставки</h1>

<p class="lead">Полный разбор программы ECOM Expo’26: %s по секциям,
%s с тезисами спикеров, голоса участников из их Telegram-каналов
и отраслевой контекст из поисковой выдачи.%s</p>

<div class="book-actions">
  <a class="primary" href="assets/ecom-2026.html">Читать онлайн</a>
  <a class="secondary" href="assets/ecom-2026.pdf">Скачать PDF%s</a>
</div>

<h2>Из чего состоит</h2>
<div class="grid">%s</div>

<h2>Как она сделана</h2>

<p>Введение, часть «Выставка в цифрах», вводные к частям и заключение написаны
вручную. Главы по секциям сгенерированы языковой моделью строго по фактуре:
ей передавались только реальные доклады с тезисами, посты каналов компаний-участников
за 2026 год и материалы поисковой выдачи, с запретом добавлять что-либо от себя.
Все упомянутые имена сверены с программой и с собранными постами.</p>

<p>Контакты участников в книгу не вошли намеренно — по той же причине,
по которой их нет на сайте: <a href="method.html">о методике</a>.</p>

<p class="small muted">Программа зафиксирована на дату сбора; организаторы правят
её до последнего дня. Актуальное расписание — в разделе
<a href="program.html">«Программа»</a>.</p>
""" % (plural(len(chapters), "глава", "главы", "глав"),
       plural(talks, "доклад", "доклада", "докладов"), size_note,
       (" · %.1f МБ" % size_mb) if pages else "", rows)

    os.makedirs(CONTENT, exist_ok=True)
    with open(os.path.join(CONTENT, "book.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  content/book.html    %d глав, %s страниц" % (len(chapters), pages or "?"))
    return {"chapters": len(chapters), "talks": talks, "pages": pages}


def build_giveaways_page(giveaways):
    """Розыгрыши и приглашения на стенд — раньше были нативной лентой,
    теперь лента занята постами каналов, поэтому это авторская страница."""
    by_group = defaultdict(list)
    for p in giveaways:
        by_group[p["group"]].append(p)

    blocks = []
    for group in ("Розыгрыши и мерч", "Приглашения на стенд"):
        items = by_group.get(group) or []
        if not items:
            continue
        cards = []
        for p in items:
            text = p["text"].strip()
            cards.append(
                '<div class="card"><h3><a href="%s" rel="nofollow noopener" '
                'target="_blank">%s</a></h3><p class="small">%s</p></div>'
                % (esc(p["url"]), esc(p["channel"]),
                   esc(text[:420] + ("…" if len(text) > 420 else ""))))
        blocks.append('<h2>%s <span class="muted small">— %d</span></h2>'
                      '<div class="grid">%s</div>' % (esc(group), len(items), "".join(cards)))

    html = ("""<h1>Розыгрыши и приглашения на стенды</h1>
<p class="lead">Что компании обещали посетителям в своих Telegram-каналах перед
выставкой: призы, мерч и приглашения с номерами стендов. Ссылка ведёт
на исходный пост — условия и сроки стоит проверять там.</p>
%s
<p class="small muted">Собрано из публичных каналов участников, разметка постов
автоматическая. Часть акций к моменту чтения уже завершилась.</p>"""
            % "".join(blocks))

    with open(os.path.join(CONTENT, "giveaways.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  content/giveaways.html %d записей" % len(giveaways))


def main():
    os.makedirs(SITE, exist_ok=True)
    print("собираю data/site/…")

    exhibitors = build_exhibitors()
    dump("exhibitors.json", exhibitors)

    events, people = build_program()
    dump("events.json", events)
    dump("people.json", people)

    feed = build_feed()
    dump("feed.json", feed)

    giveaways = build_giveaways()
    build_giveaways_page(giveaways)
    channels = build_channels_page()
    book = build_book_page()

    build_archive_page(exhibitors)

    meta = build_meta(exhibitors, events, people, feed, giveaways, channels, book)
    dump("meta.json", meta)

    book_page = ([{"file": "book.html", "nav": "Книга",
                   "title": "Ecom 2026 — книга-обзор выставки",
                   "description": "Полный разбор программы ECOM Expo’26 в HTML и PDF."}]
                 if book else [])

    dump("pages.json", book_page + [
        {"file": "channels.html", "nav": "Каналы",
         "title": "Telegram-каналы участников",
         "description": "Каналы компаний-участников ECOM Expo’26 с их постами."},
        {"file": "giveaways.html", "nav": "Розыгрыши",
         "title": "Розыгрыши и приглашения на стенды",
         "description": "Что участники обещали посетителям в своих Telegram-каналах."},
        {"file": "archive.html", "nav": "Архив",
         "title": "Архив выставки 2015–2026",
         "description": "Все компании, участвовавшие в ECOM Expo с 2015 года."},
        {"file": "method.html", "nav": "Как собрано",
         "title": "Как собран этот сайт",
         "description": "Источники данных, что проверено, где пробелы."},
    ])

    print("готово")


if __name__ == "__main__":
    main()
