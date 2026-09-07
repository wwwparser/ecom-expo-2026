# -*- coding: utf-8 -*-
"""
Строит HTML-отчёты по участникам ECOM Expo за все годы:

  build_reports.py year     → archive_by_year.html   (участники по годам + контакты)
  build_reports.py topic    → archive_by_topic.html  (участники по тематикам; классификация DeepSeek)

Источники:
  archive_participants.jsonl              — участники 2015–2025 (год, имя, сайт, descr)
  exhibitors_ecom_expo_2026.xlsx          — участники 2026 (текущие)
  archive_contacts_out/contacts.jsonl     — контакты+описания по доменам (архив)
  contacts_out/contacts.jsonl             — контакты+описания по доменам (2026)
  archive_topics.jsonl                    — кэш тематик по доменам (создаётся в режиме topic)
"""
from __future__ import annotations
import html as H
import io
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent
CONTACT_KEYS = ["emails", "phones", "telegram", "max", "whatsapp", "vk",
                "instagram", "facebook", "ok"]

TOPICS = [
    "Доставка, логистика, фулфилмент",
    "Маркетинг, реклама, SEO, трафик",
    "Разработка сайтов, CMS, IT-интеграции",
    "Платежи и финансы",
    "Маркетплейсы и товарный бизнес",
    "CRM, аналитика, автоматизация",
    "Связь, телефония, контакт-центры",
    "Производство, упаковка, оборудование",
    "Прочее",
]


def norm_domain(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "http://" + url
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def load_participants() -> dict:
    """domain -> {name, site, descr, years:set}."""
    parts = {}

    def add(name, site, descr, year):
        d = norm_domain(site)
        if not d:
            return
        p = parts.setdefault(d, {"name": name, "site": site, "descr": descr, "years": set()})
        p["years"].add(year)
        if year >= max(p["years"]):  # имя/описание берём по самому свежему году
            if name:
                p["name"] = name
            if descr and not p["descr"]:
                p["descr"] = descr

    jf = ROOT / "archive_participants.jsonl"
    if jf.exists():
        for line in jf.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            add(r.get("name", ""), r.get("site", ""), r.get("descr", ""), r["year"])

    xf = ROOT / "exhibitors_ecom_expo_2026.xlsx"
    if xf.exists():
        from openpyxl import load_workbook
        wb = load_workbook(xf, read_only=True, data_only=True)
        for ws in wb.worksheets:
            if ws.title == "Сводка":
                continue
            hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
            try:
                si, ni = hdr.index("Сайт"), hdr.index("Компания")
            except ValueError:
                continue
            di = hdr.index("Описание") if "Описание" in hdr else None
            for row in ws.iter_rows(min_row=2, values_only=True):
                site = row[si] if si < len(row) else None
                if not site:
                    continue
                name = (row[ni] if ni < len(row) else "") or ""
                descr = (row[di] if di is not None and di < len(row) else "") or ""
                add(str(name).strip(), str(site).strip(), str(descr).strip(), 2026)
    return parts


def load_contacts() -> dict:
    """domain -> contact record (description + контакты). Объединяет оба источника."""
    res = {}
    for jf in [ROOT / "archive_contacts_out" / "contacts.jsonl",
               ROOT / "contacts_out" / "contacts.jsonl"]:
        if not jf.exists():
            continue
        for line in jf.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = norm_domain(r.get("home") or r.get("site", ""))
            if not d:
                continue
            cur = res.get(d)
            # предпочитаем запись с описанием/контактами
            if not cur or (r.get("description") and not cur.get("description")):
                res[d] = r
    return res


# ---------- общие HTML-куски ----------

CSS = """
:root{--bg:#0f1216;--card:#1a1f27;--mut:#8b97a7;--txt:#e6ebf1;--acc:#27ae60}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--txt)}
header{position:sticky;top:0;background:#11151b;padding:14px 20px;border-bottom:1px solid #232a34;z-index:5}
h1{margin:0 0 6px;font-size:18px}.stat{color:var(--mut);font-size:13px}.stat b{color:var(--txt)}
#q{margin-top:10px;width:100%;max-width:440px;padding:9px 12px;border-radius:8px;border:1px solid #2c3543;background:#0c0f13;color:var(--txt)}
.sec{margin:0;padding:14px 20px 4px}
.sec h2{font-size:16px;margin:0;cursor:pointer;user-select:none;display:flex;gap:8px;align-items:center}
.sec h2 .cnt{color:var(--mut);font-size:13px;font-weight:400}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;padding:10px 20px 22px}
.card{background:var(--card);border:1px solid #232a34;border-radius:12px;padding:12px 14px}
.head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cname{font-weight:700;font-size:15px;color:var(--txt);text-decoration:none}.cname:hover{color:var(--acc)}
.yrs{color:var(--mut);font-size:11px;margin-left:auto}
.site{color:var(--mut);font-size:12px;margin:2px 0 7px;word-break:break-all}
.desc{font-size:13px;color:#c2ccd8;margin:0 0 9px;padding:7px 9px;background:#141921;border-radius:8px;border-left:3px solid var(--acc)}
.row{display:flex;gap:8px;margin:5px 0;align-items:flex-start}
.lbl{flex:0 0 66px;color:var(--mut);font-size:12px;padding-top:5px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-block;padding:4px 9px;border-radius:7px;font-size:12px;text-decoration:none;background:#222b36;color:#dbe4ee;border:1px solid #2f3a48}
.chip:hover{filter:brightness(1.25)}
.chip.tg{background:#1c4a63;border-color:#2b7aa0;color:#bfe6ff}
.chip.max{background:#4a2b63;border-color:#7d4fb0;color:#e7d4ff}
.chip.mail{background:#2a3b2a;border-color:#3e6b3e;color:#cdeccd}
.badge{font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px}
.badge.tg{background:#2b7aa0;color:#fff}.badge.max{background:#7d4fb0;color:#fff}
.empty{color:#5f6b7a;font-size:12px;font-style:italic}
.collapsed .grid{display:none}
footer{padding:14px 20px;color:var(--mut);font-size:12px}
"""

SCRIPT = """
function flt(){var v=document.getElementById('q').value.toLowerCase();
 document.querySelectorAll('.card').forEach(function(c){
   c.style.display=c.dataset.search.indexOf(v)>=0?'':'none';});
 document.querySelectorAll('.sec').forEach(function(s){
   var vis=s.querySelectorAll('.card:not([style*="none"])').length;
   s.style.display=vis?'':'none';});}
function tog(h){h.parentElement.classList.toggle('collapsed');}
"""


def chip_links(label, urls, cls):
    if not urls:
        return ""
    c = "".join(f'<a class="chip {cls}" href="{H.escape(u)}" target="_blank" rel="noopener">'
                f'{H.escape(u.replace("https://","").replace("http://",""))[:46]}</a>' for u in urls)
    return f'<div class="row"><span class="lbl">{label}</span><div class="chips">{c}</div></div>'


def card_html(p: dict, contact: dict) -> str:
    name = H.escape(p["name"] or norm_domain(p["site"]))
    site = H.escape(p["site"])
    years = ",".join(str(y) for y in sorted(p["years"], reverse=True))
    desc = (contact.get("description") if contact else "") or p.get("descr") or ""
    desc_html = f'<div class="desc">{H.escape(desc)}</div>' if desc else ""
    body = ""
    if contact:
        emails = "".join(f'<a class="chip mail" href="mailto:{H.escape(e)}">{H.escape(e)}</a>'
                         for e in contact.get("emails", []))
        phones = "".join(f'<a class="chip" href="tel:{H.escape(re.sub(chr(92)+"D","",p2))}">{H.escape(p2)}</a>'
                         for p2 in contact.get("phones", []))
        if emails:
            body += f'<div class="row"><span class="lbl">Email</span><div class="chips">{emails}</div></div>'
        if phones:
            body += f'<div class="row"><span class="lbl">Телефон</span><div class="chips">{phones}</div></div>'
        body += chip_links("Telegram", contact.get("telegram", []), "tg")
        body += chip_links("MAX", contact.get("max", []), "max")
        body += chip_links("WhatsApp", contact.get("whatsapp", []), "wa")
        body += chip_links("VK", contact.get("vk", []), "vk")
    if not body:
        body = '<div class="empty">контакты не собраны</div>'
    flags = ""
    if contact and contact.get("telegram"):
        flags += '<span class="badge tg">TG</span>'
    if contact and contact.get("max"):
        flags += '<span class="badge max">MAX</span>'
    blob = H.escape((p["name"] or "") + " " + p["site"] + " " + desc).lower()
    return f'''<div class="card" data-search="{blob}">
  <div class="head"><a class="cname" href="{site}" target="_blank" rel="noopener">{name}</a>{flags}
    <span class="yrs">{years}</span></div>
  <div class="site">{site}</div>{desc_html}{body}</div>'''


def page(title, subtitle, sections_html):
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{H.escape(title)}</title>
<style>{CSS}</style></head><body>
<header><h1>{H.escape(title)}</h1><div class="stat">{subtitle}</div>
<input id="q" placeholder="Фильтр по названию / сайту / описанию…" oninput="flt()"></header>
{sections_html}
<footer>Сгенерировано build_reports.py. Клик по Telegram/MAX/сайту открывает ссылку в новой вкладке.</footer>
<script>{SCRIPT}</script></body></html>'''


def build_year():
    parts = load_participants()
    contacts = load_contacts()
    # сгруппировать домены по годам
    by_year = {}
    for d, p in parts.items():
        for y in p["years"]:
            by_year.setdefault(y, []).append((d, p))
    secs = []
    for y in sorted(by_year, reverse=True):
        items = sorted(by_year[y], key=lambda dp: (dp[1]["name"] or dp[0]).lower())
        cards = "".join(card_html(p, contacts.get(d)) for d, p in items)
        secs.append(f'<div class="sec"><h2 onclick="tog(this)">▸ {y}'
                    f'<span class="cnt">{len(items)} участников</span></h2>'
                    f'<div class="grid">{cards}</div></div>')
    total = len(parts)
    withc = sum(1 for d in parts if d in contacts and (contacts[d].get("emails") or contacts[d].get("telegram")))
    sub = (f'Годы: {min(by_year)}–{max(by_year)} · уникальных компаний: <b>{total}</b> · '
           f'с собранными контактами: <b>{withc}</b>')
    out = ROOT / "archive_by_year.html"
    out.write_text(page("ECOM Expo — участники по годам", sub, "\n".join(secs)), encoding="utf-8")
    print(f"{out}  (компаний {total}, годы {min(by_year)}–{max(by_year)})")


# ---------- классификация по тематикам (DeepSeek) ----------

def get_ds_key():
    k = os.getenv("DEEPSEEK_API_KEY")
    if k:
        return k.strip()
    f = Path.home() / ".claude" / "secrets" / "api-keys.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DEEPSEEK_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def classify(key, name, desc):
    topics_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(TOPICS))
    prompt = (f"Отнеси компанию к ОДНОЙ тематике из списка (верни только номер 1-{len(TOPICS)}).\n"
              f"Компания: {name}\nОписание: {desc}\n\nТематики:\n{topics_list}\n\nОтвет — только число.")
    try:
        r = httpx.post("https://api.deepseek.com/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": "deepseek-chat",
                             "messages": [{"role": "user", "content": prompt}],
                             "temperature": 0, "max_tokens": 5}, timeout=40)
        r.raise_for_status()
        m = re.search(r"\d+", r.json()["choices"][0]["message"]["content"])
        if m:
            i = int(m.group()) - 1
            if 0 <= i < len(TOPICS):
                return TOPICS[i]
    except Exception as e:
        print("  classify err:", e, file=sys.stderr)
    return TOPICS[-1]


def build_topic():
    import concurrent.futures
    parts = load_participants()
    contacts = load_contacts()
    key = get_ds_key()
    cache_f = ROOT / "archive_topics.jsonl"
    cache = {}
    if cache_f.exists():
        for line in cache_f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            cache[r["domain"]] = r["topic"]

    todo = [(d, p) for d, p in parts.items() if d not in cache]
    print(f"Классификация: {len(parts)} компаний, в кэше {len(cache)}, осталось {len(todo)}")
    if todo and key:
        def work(dp):
            d, p = dp
            desc = (contacts.get(d, {}).get("description")) or p.get("descr") or p["name"]
            return d, classify(key, p["name"], desc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            for i, (d, t) in enumerate(ex.map(work, todo), 1):
                cache[d] = t
                with cache_f.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"domain": d, "topic": t}, ensure_ascii=False) + "\n")
                if i % 50 == 0:
                    print(f"  ...{i}/{len(todo)}")
    elif not key:
        print("Нет DeepSeek-ключа — пропускаю классификацию.", file=sys.stderr)

    by_topic = {}
    for d, p in parts.items():
        by_topic.setdefault(cache.get(d, TOPICS[-1]), []).append((d, p))
    secs = []
    for t in TOPICS:
        items = by_topic.get(t, [])
        if not items:
            continue
        items.sort(key=lambda dp: (dp[1]["name"] or dp[0]).lower())
        cards = "".join(card_html(p, contacts.get(d)) for d, p in items)
        secs.append(f'<div class="sec"><h2 onclick="tog(this)">▸ {H.escape(t)}'
                    f'<span class="cnt">{len(items)} компаний</span></h2>'
                    f'<div class="grid">{cards}</div></div>')
    total = len(parts)
    sub = f'Уникальных компаний: <b>{total}</b> · тематик: {len([t for t in TOPICS if by_topic.get(t)])} · классификация DeepSeek'
    out = ROOT / "archive_by_topic.html"
    out.write_text(page("ECOM Expo — участники по тематикам", sub, "\n".join(secs)), encoding="utf-8")
    print(f"{out}  (компаний {total})")


def _bar(label, value, maxv, extra=""):
    w = int(100 * value / maxv) if maxv else 0
    return (f'<div class="brow"><span class="blbl">{H.escape(str(label))}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{w}%"></span></span>'
            f'<span class="bval">{value}{extra}</span></div>')


def build_stats():
    parts = load_participants()
    contacts = load_contacts()
    topics = {}
    tf = ROOT / "archive_topics.jsonl"
    if tf.exists():
        for line in tf.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            topics[r["domain"]] = r["topic"]

    all_years = sorted({y for p in parts.values() for y in p["years"]})
    latest = max(all_years)

    # 1) рейтинг по числу участий
    ranked = sorted(parts.items(), key=lambda dp: (-len(dp[1]["years"]),
                                                    (dp[1]["name"] or dp[0]).lower()))
    rows = []
    for rank, (d, p) in enumerate(ranked, 1):
        ys = sorted(p["years"], reverse=True)
        name = H.escape(p["name"] or d)
        site = H.escape(p["site"])
        rows.append(f'<tr><td class="rk">{rank}</td>'
                    f'<td><a href="{site}" target="_blank" rel="noopener">{name}</a></td>'
                    f'<td class="cc">{len(ys)}</td>'
                    f'<td class="yy">{",".join(str(y) for y in ys)}</td></tr>')
    rank_table = ('<table class="tbl"><thead><tr><th>#</th><th>Компания</th>'
                  '<th>Участий</th><th>Годы</th></tr></thead><tbody>'
                  + "".join(rows) + "</tbody></table>")

    # 2) участников по годам
    per_year = {y: 0 for y in all_years}
    for p in parts.values():
        for y in p["years"]:
            per_year[y] += 1
    mx = max(per_year.values())
    year_bars = "".join(_bar(y, per_year[y], mx) for y in sorted(all_years, reverse=True))

    # 3) распределение по стажу (в скольких выставках участвовали)
    from collections import Counter
    streak = Counter(len(p["years"]) for p in parts.values())
    mxs = max(streak.values())
    streak_bars = "".join(_bar(f"{n} год(а/лет)", streak[n], mxs)
                          for n in sorted(streak, reverse=True))

    # 4) новички по годам (домен впервые появился)
    first_year = {d: min(p["years"]) for d, p in parts.items()}
    new_per_year = {y: 0 for y in all_years}
    for d, fy in first_year.items():
        new_per_year[fy] += 1
    mxn = max(new_per_year.values())
    new_bars = "".join(_bar(y, new_per_year[y], mxn) for y in sorted(all_years, reverse=True))

    # 5) «ушедшие»: последний год участия (кроме самого свежего)
    last_year = {d: max(p["years"]) for d, p in parts.items()}
    last_dist = {y: 0 for y in all_years}
    for d, ly in last_year.items():
        last_dist[ly] += 1
    mxl = max(last_dist.values())
    last_bars = "".join(_bar(y, last_dist[y], mxl,
                        extra=(" ← ещё участвуют" if y == latest else ""))
                        for y in sorted(all_years, reverse=True))

    # 6) тематики
    topic_html = ""
    if topics:
        tc = Counter(topics.get(d, "Прочее") for d in parts)
        mxt = max(tc.values())
        topic_html = ('<div class="block"><h2>Компании по тематикам</h2>'
                      + "".join(_bar(t, tc[t], mxt) for t, _ in tc.most_common())
                      + "</div>")

    # 7) покрытие контактами
    n = len(parts)
    cov = {k: 0 for k in ["email", "phone", "telegram", "max", "любой"]}
    for d in parts:
        c = contacts.get(d)
        if not c:
            continue
        if c.get("emails"):
            cov["email"] += 1
        if c.get("phones"):
            cov["phone"] += 1
        if c.get("telegram"):
            cov["telegram"] += 1
        if c.get("max"):
            cov["max"] += 1
        if any(c.get(k) for k in CONTACT_KEYS):
            cov["любой"] += 1
    cov_bars = "".join(_bar(k, v, n, extra=f" ({int(100*v/n)}%)") for k, v in cov.items())

    # 8) рост мессенджеров: доля участников каждого года, у кого сейчас есть TG/MAX
    msg_rows = []
    for y in sorted(all_years, reverse=True):
        doms = [d for d, p in parts.items() if y in p["years"]]
        if not doms:
            continue
        tg = sum(1 for d in doms if contacts.get(d, {}).get("telegram"))
        mxd = sum(1 for d in doms if contacts.get(d, {}).get("max"))
        msg_rows.append((y, len(doms), tg, mxd))
    mmax = max((r[2] * 100 // r[1]) for r in msg_rows) if msg_rows else 100
    msg_bars = "".join(
        _bar(f"{y}: TG", tg * 100 // tot, max(mmax, 1), extra=f"% · MAX {mxd*100//tot}%")
        for y, tot, tg, mxd in msg_rows)

    # 9) возвращенцы: есть разрыв между первым и последним годом (пропущенные доступные годы)
    dy = sorted(all_years)
    returnees = []
    for d, p in parts.items():
        span = [y for y in dy if min(p["years"]) <= y <= max(p["years"])]
        if len(p["years"]) < len(span):  # внутри интервала есть пропуски
            returnees.append((d, p, len(span) - len(p["years"])))
    returnees.sort(key=lambda x: -x[2])
    ret_html = "".join(
        f'<li><a href="{H.escape(p["site"])}" target="_blank" rel="noopener">'
        f'{H.escape(p["name"] or d)}</a> — годы {",".join(str(y) for y in sorted(p["years"]))}</li>'
        for d, p, _ in returnees[:25])

    # 10) когортная выживаемость: для года первого участия — доля, вернувшихся в след. доступный год
    cohort_rows = []
    for fy in dy[:-1]:
        cohort = [d for d, f in first_year.items() if f == fy]
        if len(cohort) < 5:
            continue
        nxt = [y for y in dy if y > fy]
        ret1 = 0
        if nxt:
            ny = nxt[0]
            ret1 = sum(1 for d in cohort if ny in parts[d]["years"])
        cohort_rows.append((fy, len(cohort), ret1 * 100 // len(cohort)))
    cmax = max((r[2] for r in cohort_rows), default=100)
    cohort_bars = "".join(_bar(f"{fy} → {fy+1 if (fy+1) in dy else 'след.'}", pct, max(cmax,1),
                          extra=f"% из {n}") for fy, n, pct in cohort_rows)

    # 11) тематики × годы (таблица счётчиков)
    ty_html = ""
    if topics:
        years_desc = sorted(all_years, reverse=True)
        tset = [t for t in TOPICS if any(topics.get(d) == t for d in parts)]
        head = "".join(f"<th>{y}</th>" for y in years_desc)
        trows = ""
        for t in tset:
            cells = ""
            for y in years_desc:
                cnt = sum(1 for d, p in parts.items() if topics.get(d) == t and y in p["years"])
                cells += f'<td class="cc">{cnt or ""}</td>'
            trows += f"<tr><td>{H.escape(t)}</td>{cells}</tr>"
        ty_html = (f'<div class="block"><h2>🧭 Тематики × годы</h2>'
                   f'<table class="tbl"><thead><tr><th>Тематика</th>{head}</tr></thead>'
                   f'<tbody>{trows}</tbody></table></div>')

    # топ-старожилы (участвовали почти каждый год)
    veterans = [(d, p) for d, p in ranked if len(p["years"]) >= len(all_years) - 1][:25]
    vet_html = "".join(
        f'<li><a href="{H.escape(p["site"])}" target="_blank" rel="noopener">'
        f'{H.escape(p["name"] or d)}</a> — {len(p["years"])} из {len(all_years)} лет</li>'
        for d, p in veterans)

    body = f'''
<div class="block"><h2>🏆 Рейтинг по числу участий (все годы)</h2>
  <p class="note">Сколько разных выставок (лет) компания участвовала. Данные за {min(all_years)}–{latest}.</p>
  {rank_table}</div>
<div class="block"><h2>🎖 Старожилы (участвовали почти каждый год)</h2><ul class="vet">{vet_html}</ul></div>
<div class="block"><h2>📈 Участников по годам</h2>{year_bars}</div>
<div class="block"><h2>🆕 Новые компании по годам (первое участие)</h2>{new_bars}</div>
<div class="block"><h2>👋 Последний год участия (распределение)</h2>
  <p class="note">Сколько компаний «в последний раз» видели в этом году. Большой столбец на {latest} — это активные сейчас.</p>{last_bars}</div>
<div class="block"><h2>🔁 Распределение по стажу</h2>{streak_bars}</div>
<div class="block"><h2>💬 Рост мессенджеров (доля участников года с Telegram/MAX сейчас)</h2>
  <p class="note">Контакты — текущий срез; показывает, у какой доли участников каждого года сегодня есть канал.</p>{msg_bars}</div>
<div class="block"><h2>🔄 Когортная выживаемость (вернулись на следующую доступную выставку)</h2>{cohort_bars}</div>
<div class="block"><h2>↩️ Возвращенцы (участвовали с разрывами) — {len(returnees)} компаний</h2><ul class="vet">{ret_html}</ul></div>
{ty_html}
{topic_html}
<div class="block"><h2>📇 Покрытие контактами (из собранных)</h2>{cov_bars}</div>
'''
    css_extra = """
.block{padding:8px 20px 16px;border-bottom:1px solid #1d242e}
.block h2{font-size:16px;margin:10px 0 8px}.note{color:var(--mut);font-size:12px;margin:0 0 10px}
.tbl{border-collapse:collapse;width:100%;font-size:13px}
.tbl th,.tbl td{padding:5px 8px;border-bottom:1px solid #232a34;text-align:left}
.tbl th{color:var(--mut);font-weight:600;position:sticky;top:96px;background:#11151b}
.tbl td a{color:var(--txt);text-decoration:none}.tbl td a:hover{color:var(--acc)}
.tbl .rk{color:var(--mut);width:40px}.tbl .cc{text-align:center;font-weight:700;color:var(--acc);width:70px}
.tbl .yy{color:var(--mut);font-size:11px}
.brow{display:flex;align-items:center;gap:10px;margin:3px 0}
.blbl{flex:0 0 130px;font-size:12px;text-align:right;color:#c2ccd8}
.btrack{flex:1;background:#141921;border-radius:5px;height:16px;overflow:hidden}
.bfill{display:block;height:100%;background:linear-gradient(90deg,#1f7a3d,#27ae60)}
.bval{flex:0 0 130px;font-size:12px;color:var(--mut)}
.vet{columns:2;font-size:13px;margin:0;padding-left:18px}.vet a{color:var(--txt);text-decoration:none}.vet a:hover{color:var(--acc)}
"""
    doc = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ECOM Expo — статистика участников</title>
<style>{CSS}{css_extra}</style></head><body>
<header><h1>ECOM Expo — статистика участников за все годы</h1>
<div class="stat">Уникальных компаний: <b>{n}</b> · годы: {min(all_years)}–{latest} · всего участий-строк: <b>{sum(per_year.values())}</b></div>
</header>{body}
<footer>Сгенерировано build_reports.py stats.</footer></body></html>'''
    out = ROOT / "archive_stats.html"
    out.write_text(doc, encoding="utf-8")
    print(f"{out}  (компаний {n}, годы {min(all_years)}–{latest})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "year"
    if mode == "year":
        build_year()
    elif mode == "topic":
        build_topic()
    elif mode == "stats":
        build_stats()
    else:
        print("Использование: build_reports.py [year|topic|stats]")
