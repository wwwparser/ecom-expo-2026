# -*- coding: utf-8 -*-
"""Статьи по тематикам программы: фактура выставки + выдача XMLRiver -> бесплатные модели.

Конвейер на каждую тему:
  1. фактура из data/site/events.json — секции, доклады, спикеры, компании, тезисы;
  2. XMLRiver (Google, регион РФ) по нескольким запросам темы — заголовки,
     сниппеты и ссылки на отраслевые материалы (кэшируются, чтобы не платить дважды);
  3. генерация текста бесплатной моделью OpenRouter по жёсткому стилевому промпту;
  4. сохранение в content/articles/topic-<slug>.html с блоком meta для генератора сайта.

Модель получает ТОЛЬКО собранную фактуру и обязана опираться на неё: свободный
пересказ «по памяти» у бесплатных моделей выдумывает цифры и названия компаний.

Запуск: python build_topic_articles.py                # все темы
        python build_topic_articles.py --topic marketplaces
        python build_topic_articles.py --no-serp      # только на данных программы
Выход:  content/articles/topic-*.html, кэш выдачи в data/raw/topic_serp.json
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/Yuri/.claude/skills/openrouter-free/scripts")

from enrich_speakers import load_env, parse_serp, raw_search  # noqa: E402
from or_free import chat  # noqa: E402

if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "data", "site", "events.json")
ARTICLES = os.path.join(HERE, "content", "articles")
SERP_CACHE = os.path.join(HERE, "data", "raw", "topic_serp.json")

# Поток в программе -> тема статьи. Потоки «МАРКЕТИНГ» и «МАРКЕТИНГ 2» — это один
# и тот же трек, разведённый по залам, поэтому сводим их в одну тему.
STREAM_TO_TOPIC = {
    "МАРКЕТПЛЕЙСЫ: оптимизация": "marketplaces",
    "МАРКЕТПЛЕЙСЫ: масштабирование": "marketplaces",
    "МАРКЕТИНГ": "marketing",
    "МАРКЕТИНГ 2": "marketing",
    "ИТ": "it",
    "БИЗНЕС-ПРОЦЕССЫ": "operations",
    "СОВМЕЩЕННЫЙ ПОТОК": "legal",
}

TOPICS = {
    "marketplaces": {
        "title": "Маркетплейсы: о чём говорят на ECOM Expo’26",
        "tag": "Маркетплейсы",
        "queries": [
            "рынок маркетплейсов России 2026 статистика доля продаж",
            "продвижение на Wildberries Ozon 2026 изменения алгоритмов",
            "селлеры маркетплейсов 2026 исследование расходы комиссии",
        ],
    },
    "marketing": {
        "title": "Маркетинг в электронной торговле: повестка 2026 года",
        "tag": "Маркетинг",
        "queries": [
            "тренды интернет-маркетинга e-commerce 2026 Россия",
            "стоимость привлечения клиента ecommerce 2026 рост",
            "ИИ в маркетинге 2026 исследование применение бизнес",
        ],
    },
    "operations": {
        "title": "Логистика, платежи и деньги: операционный контур интернет-торговли",
        "tag": "Операции",
        "queries": [
            "логистика последней мили Россия 2026 рынок доставки",
            "платежи в интернет-торговле 2026 рассрочка BNPL Россия",
            "склады фулфилмент e-commerce 2026 ставки дефицит",
        ],
    },
    "it": {
        "title": "ИТ для e-commerce: интеграции, разработка и автономность",
        "tag": "ИТ",
        "queries": [
            "импортозамещение ИТ e-commerce 2026 Россия",
            "интеграции backend интернет-магазина 2026 архитектура",
            "аутсорс разработки Россия 2026 рынок ставки",
        ],
    },
    "legal": {
        "title": "Право, налоги и кадры: что меняется для интернет-торговли",
        "tag": "Регулирование",
        "queries": [
            "регулирование маркетплейсов закон 2026 Россия",
            "налоги для селлеров маркетплейсов 2026 изменения",
            "дефицит кадров e-commerce 2026 зарплаты",
        ],
    },
}

SYSTEM = """Ты пишешь аналитическую статью для независимого сайта-разбора отраслевой
выставки ECOM Expo’26 (электронная торговля, Москва, 24–25 июня 2026).

Жёсткие требования:
1. Опирайся ТОЛЬКО на факты из блоков «ПРОГРАММА» и «ИСТОЧНИКИ». Ничего не
   придумывай: ни цифр, ни названий компаний, ни цитат, которых там нет.
2. Если данных для утверждения не хватает — не пиши это утверждение вовсе.
3. Пиши по-русски, деловым языком, без канцелярита, без маркетингового пафоса,
   без обращений «дорогой читатель» и без выводов вида «время покажет».
4. Никаких вводных абзацев о том, что такое электронная торговля.
5. Структура: 4–6 разделов с подзаголовками <h2>, внутри абзацы <p> и,
   где уместно, списки <ul><li>. Заголовка <h1> НЕ ставь.
6. Названия докладов и компаний бери дословно из блока «ПРОГРАММА».
7. Объём 500–800 слов.
8. Верни ЧИСТЫЙ HTML-фрагмент без <html>, <body>, без markdown и без ```.

Стиль: спокойная констатация того, что видно в данных, с объяснением, почему
это так. Как пишет отраслевой обозреватель, который сам прочитал программу."""


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def program_facts(topic_key):
    """Фактура по теме: секции, доклады со спикерами и тезисами."""
    events = load_json(EVENTS, []) or []
    mine = [e for e in events if STREAM_TO_TOPIC.get(e.get("kind")) == topic_key]
    lines, talks_total, companies = [], 0, set()

    for e in sorted(mine, key=lambda x: (x.get("date", ""), x.get("start", ""))):
        head = "СЕКЦИЯ «%s» — %s, %s, %s" % (
            e["title"], e.get("date", ""), e.get("start", ""), e.get("venue", ""))
        lines.append(head)
        body = e.get("description") or ""
        for m in re.finditer(r"<li><b>(.*?)</b><br><span class=\"small\">(.*?)</span>(.*?)</li>",
                             body, re.S):
            title, speaker, rest = (strip_tags(m.group(1)), strip_tags(m.group(2)),
                                    strip_tags(m.group(3)))
            talks_total += 1
            company = speaker.split(",")[-1].strip() if "," in speaker else ""
            if company:
                companies.add(company)
            lines.append("  • Доклад: %s" % title)
            lines.append("    Спикер: %s" % speaker)
            if rest:
                lines.append("    Тезисы: %s" % rest[:400])
        lines.append("")

    return {"text": "\n".join(lines), "sections": len(mine),
            "talks": talks_total, "companies": sorted(companies)}


def serp_facts(topic_key, use_serp=True):
    """Материалы по теме из выдачи. Кэш — чтобы повторный прогон был бесплатным."""
    if not use_serp:
        return "", []
    cache = load_json(SERP_CACHE, {}) or {}
    if topic_key in cache:
        hits = cache[topic_key]
    else:
        load_env()
        hits = []
        for q in TOPICS[topic_key]["queries"]:
            try:
                for h in parse_serp(raw_search(q))[:6]:
                    hits.append({"query": q, **h})
            except Exception as e:
                print("    XMLRiver «%s»: %s" % (q, str(e)[:90]))
        cache[topic_key] = hits
        os.makedirs(os.path.dirname(SERP_CACHE), exist_ok=True)
        with open(SERP_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)

    lines = []
    for h in hits:
        snippet = (h.get("snippet") or "")[:320]
        lines.append("- %s\n  %s\n  %s" % (h.get("title", ""), snippet, h.get("url", "")))
    return "\n".join(lines), hits


def write_article(key, html, facts, hits):
    meta = TOPICS[key]
    sources = ""
    if hits:
        seen, items = set(), []
        for h in hits:
            url = h.get("url", "")
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            if not url or host in seen:
                continue
            seen.add(host)
            items.append('<li><a href="%s" rel="nofollow noopener" target="_blank">%s</a> — %s</li>'
                         % (url, host, (h.get("title") or "")[:110]))
            if len(items) >= 8:
                break
        if items:
            sources = ("\n<h2>Материалы по теме</h2>\n<ul class=\"small\">%s</ul>"
                       % "".join(items))

    lead = ("%d секций и %d докладов программы ECOM Expo’26 по этой теме — "
            "о чём именно будут говорить." % (facts["sections"], facts["talks"]))
    doc = """<!--meta
title: %s
lead: %s
tag: %s
-->
<h1>%s</h1>

<p class="lead">%s</p>

%s%s

<p class="small muted">Черновик статьи сгенерирован бесплатной моделью OpenRouter
по фактуре программы выставки и материалам поисковой выдачи, затем проверен
вручную. Названия докладов и спикеров — из официальной программы,
<a href="../program.html">полный список с фильтрами</a>.</p>
""" % (meta["title"], lead, meta["tag"], meta["title"], lead, html.strip(), sources)

    os.makedirs(ARTICLES, exist_ok=True)
    path = os.path.join(ARTICLES, "topic-%s.html" % key)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="", help="ключ одной темы")
    ap.add_argument("--no-serp", action="store_true", help="без запросов к XMLRiver")
    a = ap.parse_args()

    keys = [a.topic] if a.topic else list(TOPICS)
    for key in keys:
        if key not in TOPICS:
            print("нет такой темы: %s" % key)
            continue
        print("=== %s" % TOPICS[key]["title"])
        facts = program_facts(key)
        print("    программа: %d секций, %d докладов" % (facts["sections"], facts["talks"]))
        if not facts["talks"]:
            print("    пропускаю: нет докладов")
            continue

        serp_text, hits = serp_facts(key, use_serp=not a.no_serp)
        print("    материалов из выдачи: %d" % len(hits))

        user = ("ТЕМА СТАТЬИ: %s\n\nПРОГРАММА (только эти доклады и спикеры реальны):\n%s\n\n"
                "ИСТОЧНИКИ (заголовки и сниппеты отраслевых материалов):\n%s\n\n"
                "Напиши статью по требованиям из системного сообщения."
                % (TOPICS[key]["title"], facts["text"][:14000], serp_text[:6000]))

        html = chat(SYSTEM, user, max_tokens=3000, temperature=0.4)
        if not html or len(html) < 400:
            print("    модель вернула пусто — тема пропущена")
            continue
        html = re.sub(r"^```(?:html)?|```$", "", html.strip(), flags=re.M).strip()
        html = re.sub(r"</?(html|body|h1)[^>]*>", "", html)

        path = write_article(key, html, facts, hits)
        print("    записано: %s (%d символов)" % (os.path.basename(path), len(html)))


if __name__ == "__main__":
    main()
