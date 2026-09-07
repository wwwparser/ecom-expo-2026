# -*- coding: utf-8 -*-
"""Книга «Ecom 2026» — обзор всей программы выставки, в HTML и PDF.

Источники:
  data/site/events.json          34 секции, 182 доклада с тезисами и спикерами
  data/raw/channel_history.json  посты Telegram-каналов участников за 2026 год
  data/raw/book_serp.json        материалы отраслевой выдачи (XMLRiver, по секциям)
  data/site/exhibitors.json      участники, стенды, рубрики
  data/site/meta.json            сводные цифры и разрезы

Главы по секциям пишет бесплатная модель OpenRouter по жёсткой фактуре: ей
запрещено выходить за пределы переданных докладов, постов и источников.
Обзорные части (введение, разделы про рынок и архив, заключение) написаны
вручную и лежат в book_frontmatter.py.

Запуск: python build_book.py                 # собрать всё: главы -> HTML -> PDF
        python build_book.py --limit 3       # пилот на трёх секциях
        python build_book.py --no-serp       # без платных запросов
        python build_book.py --html-only     # не делать PDF
Выход:  book/ecom-2026.html, book/ecom-2026.pdf
        кэш глав: data/raw/book_chapters.json (resume)
"""
import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/Yuri/.claude/skills/openrouter-free/scripts")

from enrich_speakers import load_env, parse_serp, raw_search  # noqa: E402
from or_free import chat  # noqa: E402
from book_frontmatter import FRONT, PART_INTROS, CLOSING  # noqa: E402

if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "data", "site")
RAW = os.path.join(HERE, "data", "raw")
BOOK = os.path.join(HERE, "book")
CHAPTERS = os.path.join(RAW, "book_chapters.json")
SERP = os.path.join(RAW, "book_serp.json")

# Поток программы -> часть книги
PARTS = [
    ("marketplaces", "Часть II. Маркетплейсы",
     ["МАРКЕТПЛЕЙСЫ: оптимизация", "МАРКЕТПЛЕЙСЫ: масштабирование"]),
    ("marketing", "Часть III. Маркетинг и продажи", ["МАРКЕТИНГ", "МАРКЕТИНГ 2"]),
    ("operations", "Часть IV. Логистика, платежи и операции", ["БИЗНЕС-ПРОЦЕССЫ"]),
    ("it", "Часть V. ИТ и разработка", ["ИТ"]),
    ("legal", "Часть VI. Право, налоги и кадры", ["СОВМЕЩЕННЫЙ ПОТОК"]),
]

SYSTEM = """Ты пишешь главу отраслевой книги «Ecom 2026» — обзора выставки
ECOM Expo’26 (электронная торговля, Москва, 24–25 июня 2026).

Жёсткие требования:
1. Пиши ТОЛЬКО по фактуре из блоков «СЕКЦИЯ», «ГОЛОСА РЫНКА» и «ИСТОЧНИКИ».
   Не выдумывай ни цифр, ни компаний, ни цитат, которых там нет.
2. Каждый доклад секции должен быть упомянут: тема, спикер, компания и суть
   по тезисам. Не перечисляй списком — свяжи в текст по смыслу, группируя
   доклады по общей идее.
3. Пиши по-русски, деловым языком обозревателя. Без канцелярита, без пафоса,
   без обращений к читателю, без фраз «в заключение» и «время покажет».
4. Не пересказывай, что такое электронная торговля и маркетплейсы.
5. Структура главы: 3–5 разделов с подзаголовками <h3>, внутри <p>, где
   уместно — <ul><li>. Заголовков <h1> и <h2> НЕ ставь.
6. Объём 700–1100 слов.
7. Верни ЧИСТЫЙ HTML-фрагмент: без markdown, без ```, без <html> и <body>.

Если в блоке «ГОЛОСА РЫНКА» есть подходящие посты компаний — вплети одну-две
отсылки к тому, что эти компании пишут у себя, указав компанию по названию."""


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def section_talks(event):
    """Доклады секции: тема, спикер, тезисы — как их видит модель."""
    out = []
    for m in re.finditer(r"<li><b>(.*?)</b><br><span class=\"small\">(.*?)</span>(.*?)</li>",
                         event.get("description") or "", re.S):
        out.append({"title": strip_tags(m.group(1)),
                    "speaker": strip_tags(m.group(2)),
                    "theses": strip_tags(m.group(3))})
    return out


STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы
за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг
ли если или быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей
может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз
тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом
один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец
два об другой хоть после над больше тот через эти нас про них какая много разве три
эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более
всегда конечно всю между это как для его нас про наш ваш это все свой""".split())


def keywords(text, extra=()):
    """Значимые слова темы: длинные, без стоп-слов, в нижнем регистре."""
    words = re.findall(r"[А-Яа-яЁёA-Za-z]{5,}", (text or "").lower())
    return {w for w in words if w not in STOP} | set(extra)


def channel_voices(event, talks, history, limit=6):
    """Посты каналов участников, относящиеся к теме секции.

    Сначала берём каналы компаний, чьи спикеры выступают в этой секции: их
    голос самый уместный. Затем добираем тематически близкие посты остальных
    участников — по совпадению значимых слов темы секции и названий докладов.
    Без второго шага «голоса рынка» пустуют у двух третей глав: спикер и канал
    редко принадлежат одной и той же компании из нашего списка.
    """
    picked, used_channels = [], set()

    # 1. Компании, чьи спикеры выступают в секции
    by_company = {}
    for rec in history.values():
        company = (rec.get("company") or "").strip()
        if len(company) >= 4:
            by_company[company.lower()] = rec
    for t in talks:
        low = t["speaker"].lower()
        for company, rec in by_company.items():
            if company in low and rec["username"] not in used_channels:
                used_channels.add(rec["username"])
                for p in [x for x in rec.get("posts") or []
                          if len(x.get("text") or "") > 220][:2]:
                    picked.append("[%s, %s, выступает в этой секции] %s"
                                  % (rec.get("company"), p["datetime"][:10], p["text"][:700]))

    # 2. Тематически близкие посты остальных каналов
    topic = keywords(event["title"] + " " + " ".join(t["title"] for t in talks))
    if topic:
        scored = []
        for rec in history.values():
            if rec["username"] in used_channels:
                continue
            for p in rec.get("posts") or []:
                text = p.get("text") or ""
                if len(text) < 300:
                    continue
                hits = topic & keywords(text[:1500])
                if len(hits) >= 3:
                    scored.append((len(hits), rec, p))
        scored.sort(key=lambda s: -s[0])
        for _score, rec, p in scored:
            if rec["username"] in used_channels:
                continue  # не больше одного поста на канал, иначе один блогер займёт всё
            used_channels.add(rec["username"])
            picked.append("[%s, %s] %s" % (rec.get("company"), p["datetime"][:10],
                                           p["text"][:700]))
            if len(picked) >= limit:
                break

    return picked[:limit]


def serp_for(event, use_serp=True):
    """Отраслевые материалы по теме секции. Один платный запрос на секцию, с кэшем."""
    if not use_serp:
        return [], ""
    cache = load_json(SERP, {}) or {}
    key = event["id"]
    if key not in cache:
        load_env()
        topic = re.sub(r"^\d+\.\d+\s*", "", event["title"])
        query = "%s электронная торговля 2026" % topic
        try:
            cache[key] = parse_serp(raw_search(query))[:6]
        except Exception as e:
            print("    XMLRiver: %s" % str(e)[:80])
            cache[key] = []
        save_json(SERP, cache)
    hits = cache[key]
    text = "\n".join("- %s\n  %s\n  %s" % (h.get("title", ""), (h.get("snippet") or "")[:280],
                                           h.get("url", "")) for h in hits)
    return hits, text


def build_chapter(event, history, use_serp):
    talks = section_talks(event)
    if not talks:
        return None

    voices = channel_voices(event, talks, history)
    hits, serp_text = serp_for(event, use_serp)

    facts = ["СЕКЦИЯ: %s" % event["title"],
             "Когда: %s, %s–%s" % (event.get("date", ""), event.get("start", ""),
                                   event.get("end", "")),
             "Зал: %s" % event.get("venue", ""), ""]
    leaders = re.search(r"<b>Ведущий секции:</b>\s*([^<]+)", event.get("description") or "")
    if leaders:
        facts.append("Ведущий: %s" % leaders.group(1).strip())
    facts.append("")
    for t in talks:
        facts.append("ДОКЛАД: %s" % t["title"])
        facts.append("  Спикер: %s" % t["speaker"])
        if t["theses"]:
            facts.append("  Тезисы: %s" % t["theses"][:700])
    user = ("%s\n\nГОЛОСА РЫНКА (посты Telegram-каналов компаний-участников за 2026 год):\n%s\n\n"
            "ИСТОЧНИКИ (отраслевые материалы из поисковой выдачи):\n%s\n\n"
            "Напиши главу по требованиям из системного сообщения."
            % ("\n".join(facts)[:15000], ("\n\n".join(voices))[:6000] or "(нет)",
               serp_text[:4000] or "(нет)"))

    html = chat(SYSTEM, user, max_tokens=3200, temperature=0.4)
    if not html or len(html) < 500:
        return None
    html = re.sub(r"^```(?:html)?|```$", "", html.strip(), flags=re.M).strip()
    html = re.sub(r"</?(html|body)[^>]*>", "", html)
    html = re.sub(r"<h[12][^>]*>(.*?)</h[12]>", r"<h3>\1</h3>", html, flags=re.S)
    return {"html": html, "talks": len(talks), "voices": len(voices), "sources": hits}


def collect_chapters(limit=0, use_serp=True):
    events = load_json(os.path.join(SITE, "events.json"), []) or []
    history = load_json(os.path.join(RAW, "channel_history.json"), {}) or {}
    done = load_json(CHAPTERS, {}) or {}

    by_stream = defaultdict(list)
    for e in events:
        by_stream[e.get("kind") or ""].append(e)

    queue = []
    for key, _title, streams in PARTS:
        for stream in streams:
            for e in sorted(by_stream.get(stream, []),
                            key=lambda x: (x.get("date", ""), x.get("start", ""))):
                queue.append((key, e))

    todo = [(k, e) for k, e in queue if e["id"] not in done]
    if limit:
        todo = todo[:limit]
    print("секций всего %d, глав готово %d, к генерации %d"
          % (len(queue), len(done), len(todo)))

    for i, (key, e) in enumerate(todo, 1):
        ch = build_chapter(e, history, use_serp)
        if not ch:
            print("[%d/%d] %-52s пропуск (нет докладов или пустой ответ)"
                  % (i, len(todo), e["title"][:52]))
            continue
        ch.update({"part": key, "id": e["id"], "title": e["title"],
                   "date": e.get("date", ""), "start": e.get("start", ""),
                   "end": e.get("end", ""), "venue": e.get("venue", "")})
        done[e["id"]] = ch
        words = len(strip_tags(ch["html"]).split())
        print("[%d/%d] %-52s %4d слов, %d докл., %d постов"
              % (i, len(todo), e["title"][:52], words, ch["talks"], ch["voices"]))
        save_json(CHAPTERS, done)

    return queue, done


CSS = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm; }
@page { @bottom-center { content: counter(page); } }
:root { --ink:#1a1a1a; --muted:#6b7280; --line:#e5e7eb; --accent:#0f766e; }
* { box-sizing: border-box; }
body { font: 11.5pt/1.62 Georgia, "Times New Roman", serif; color: var(--ink);
       margin: 0 auto; max-width: 780px; padding: 24px; background: #fff; }
h1, h2, h3, .cover-title { font-family: "Segoe UI", Arial, sans-serif; }
.cover { text-align: center; padding: 60mm 0 0; page-break-after: always; }
.cover-title { font-size: 46pt; letter-spacing: -1px; margin: 0; color: var(--accent); }
.cover-sub { font-size: 16pt; color: var(--muted); margin-top: 12px; }
.cover-meta { margin-top: 40mm; font-size: 11pt; color: var(--muted); }
h1 { font-size: 22pt; margin: 0 0 6px; page-break-before: always; color: var(--accent); }
h1.part { font-size: 26pt; border-bottom: 3px solid var(--accent); padding-bottom: 10px; }
h2 { font-size: 15.5pt; margin: 26px 0 8px; }
h3 { font-size: 12.5pt; margin: 20px 0 6px; color: #111; }
p { margin: 0 0 10px; text-align: justify; hyphens: auto; }
ul, ol { margin: 0 0 12px 20px; padding: 0; }
li { margin: 0 0 5px; }
.lead { font-size: 12.5pt; color: #333; font-style: italic; }
.meta { color: var(--muted); font-size: 10pt; margin: 0 0 14px;
        border-left: 3px solid var(--accent); padding-left: 10px; }
.small { font-size: 9.5pt; color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th, td { border: 1px solid var(--line); padding: 5px 8px; text-align: left; }
th { background: #f6f7f8; }
.toc { page-break-after: always; }
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { margin: 3px 0; }
.toc .part-row { font-weight: 700; margin-top: 14px; font-family: "Segoe UI", Arial, sans-serif; }
.toc a { color: var(--ink); text-decoration: none; }
.sources { font-size: 9pt; color: var(--muted); margin-top: 14px;
           border-top: 1px solid var(--line); padding-top: 8px; }
.sources a { color: var(--muted); }
h1, h2, h3 { page-break-after: avoid; }
"""


def directory_html():
    """Справочник участников по рубрикам: компания, стенд, чем занимается.

    Контакты сюда не идут сознательно — книга распространяется файлом,
    а список рабочих почт в таком виде живёт своей жизнью."""
    exhibitors = load_json(os.path.join(SITE, "exhibitors.json"), []) or []
    by_group = defaultdict(list)
    for x in exhibitors:
        by_group[x.get("group") or "Другое"].append(x)

    blocks = ["""<h1 id="directory" class="part">Приложение. Участники и стенды</h1>
<p class="lead">205 компаний ECOM Expo’26 по рубрикам: номер стенда, чем
занимается, сколько раз уже была на выставке. Контакты не приводятся
намеренно.</p>"""]

    for group in sorted(by_group, key=lambda g: -len(by_group[g])):
        items = sorted(by_group[group], key=lambda i: (i.get("name") or "").lower())
        rows = []
        for x in items:
            about = re.sub(r"\s*На ECOM Expo.*$", "", x.get("about") or "").strip()
            years = x.get("years") or []
            history = ("%d-й раз" % (len(years) + 1)) if years else "впервые"
            rows.append("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>"
                        % (esc(x.get("name", "")), esc(", ".join(x.get("stands") or []) or "—"),
                           esc(about[:120]), esc(history)))
        blocks.append('<h2>%s <span class="small">— %d</span></h2>'
                      '<table><tr><th>Компания</th><th>Стенд</th><th>Чем занимается</th>'
                      '<th>На выставке</th></tr>%s</table>'
                      % (esc(group), len(items), "".join(rows)))
    return "".join(blocks)


def chapter_title(ch):
    """Пленарные секции в программе называются одинаково — «Открывающая секция
    дня». В оглавлении книги их четыре подряд, поэтому уточняем залом."""
    title = ch["title"]
    if title.lower().startswith("открывающая секция"):
        hall = (ch.get("venue") or "").split("—")[0].strip()
        if hall:
            return "%s: %s" % (title, hall)
    return title


def render_html(queue, chapters):
    parts_order = [(k, t) for k, t, _ in PARTS]
    by_part = defaultdict(list)
    for key, e in queue:
        ch = chapters.get(e["id"])
        if ch:
            by_part[key].append(ch)

    toc, body = [], []

    # оглавление: вводные части
    for anchor, title in [("intro", FRONT["intro_title"]), ("figures", FRONT["figures_title"])]:
        toc.append('<li class="part-row"><a href="#%s">%s</a></li>' % (anchor, esc(title)))

    body.append('<h1 id="intro" class="part">%s</h1>%s' % (esc(FRONT["intro_title"]), FRONT["intro"]))
    body.append('<h1 id="figures" class="part">%s</h1>%s'
                % (esc(FRONT["figures_title"]), FRONT["figures"]))

    n = 0
    for key, part_title in parts_order:
        chs = by_part.get(key) or []
        if not chs:
            continue
        toc.append('<li class="part-row"><a href="#part-%s">%s</a></li>' % (key, esc(part_title)))
        body.append('<h1 id="part-%s" class="part">%s</h1>' % (key, esc(part_title)))
        body.append(PART_INTROS.get(key, ""))
        for ch in chs:
            n += 1
            anchor = "ch%s" % ch["id"]
            toc.append('<li><a href="#%s">%d. %s</a></li>' % (anchor, n, esc(chapter_title(ch))))
            src = ""
            if ch.get("sources"):
                items = []
                seen = set()
                for h in ch["sources"]:
                    url = h.get("url", "")
                    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
                    if not url or host in seen:
                        continue
                    seen.add(host)
                    items.append('<a href="%s">%s</a>' % (esc(url), esc(host)))
                if items:
                    src = '<div class="sources">Материалы по теме: %s</div>' % " · ".join(items[:5])
            body.append(
                '<h2 id="%s">%d. %s</h2>'
                '<p class="meta">%s, %s–%s · %s · докладов: %d</p>%s%s'
                % (anchor, n, esc(chapter_title(ch)), esc(ch.get("date", "")), esc(ch.get("start", "")),
                   esc(ch.get("end", "")), esc(ch.get("venue", "")), ch.get("talks", 0),
                   ch["html"], src))

    toc.append('<li class="part-row"><a href="#closing">%s</a></li>' % esc(CLOSING["title"]))
    body.append('<h1 id="closing" class="part">%s</h1>%s' % (esc(CLOSING["title"]), CLOSING["html"]))

    toc.append('<li class="part-row"><a href="#directory">Приложение. Участники и стенды</a></li>')
    body.append(directory_html())

    words = len(strip_tags("".join(body)).split())
    html = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Ecom 2026 — обзор выставки ECOM Expo’26</title>
<style>%s</style></head><body>
<div class="cover">
  <div class="cover-title">Ecom 2026</div>
  <div class="cover-sub">Полный обзор программы выставки ECOM Expo’26</div>
  <div class="cover-meta">Москва, 24–25 июня 2026<br>
  %d глав по секциям программы · %d докладов · %d слов<br>
  Независимый разбор по открытым данным</div>
</div>
<div class="toc"><h1 class="part" style="page-break-before:avoid">Содержание</h1>
<ol>%s</ol></div>
%s
</body></html>""" % (CSS, n, sum(c.get("talks", 0) for c in chapters.values()),
                     words, "".join(toc), "".join(body))
    return html, words, n


def make_pdf(html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("file:///" + html_path.replace("\\", "/"), wait_until="networkidle")
        page.pdf(path=pdf_path, format="A4", print_background=True,
                 margin={"top": "20mm", "bottom": "18mm", "left": "18mm", "right": "18mm"},
                 display_header_footer=True,
                 header_template="<div></div>",
                 footer_template='<div style="width:100%;font-size:8pt;color:#888;'
                                 'text-align:center;">Ecom 2026 · '
                                 '<span class="pageNumber"></span></div>')
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-serp", action="store_true")
    ap.add_argument("--html-only", action="store_true")
    a = ap.parse_args()

    queue, chapters = collect_chapters(a.limit, not a.no_serp)
    html, words, n = render_html(queue, chapters)

    os.makedirs(BOOK, exist_ok=True)
    html_path = os.path.join(BOOK, "ecom-2026.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    # ~450 слов на страницу A4 при этой вёрстке
    print("HTML: %s — %d глав, %d слов (≈%d страниц)"
          % (html_path, n, words, round(words / 450)))

    if not a.html_only:
        pdf_path = os.path.join(BOOK, "ecom-2026.pdf")
        make_pdf(html_path, pdf_path)
        print("PDF: %s — %.1f МБ" % (pdf_path, os.path.getsize(pdf_path) / 1048576))


if __name__ == "__main__":
    main()
