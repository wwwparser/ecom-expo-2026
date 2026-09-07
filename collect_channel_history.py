# -*- coding: utf-8 -*-
"""История Telegram-каналов участников за 2026 год — для книги «Ecom 2026».

Веб-превью t.me/s/<username> отдаёт около двадцати постов на страницу, а глубже
листается параметром ?before=<id>. Идём назад по ленте, пока не дойдём до постов
старше 2026 года или пока страницы не кончатся.

Отличие от collect_channel_posts.py: тот берёт последние 10 постов для ленты
сайта, этот — весь 2026 год как материал для книги.

Запуск: python collect_channel_history.py              # все каналы с превью
        python collect_channel_history.py --limit 5    # пилот
        python collect_channel_history.py --since 2026-01-01
Выход:  data/raw/channel_history.json (resume по каналам)
"""
import argparse
import io
import json
import os
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_channel_posts import parse_views, UA  # noqa: E402

if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "raw", "channel_history.json")
SEED = os.path.join(HERE, "data", "raw", "channel_posts.json")

PAUSE = 0.8
MAX_PAGES = 40  # страховка от бесконечного листания больших каналов


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_page(html, username):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for b in soup.select("div.tgme_widget_message"):
        post_id = b.get("data-post", "")
        mid = post_id.split("/")[-1] if "/" in post_id else ""
        tx = b.select_one("div.tgme_widget_message_text")
        t = b.select_one("a.tgme_widget_message_date time")
        views = b.select_one("span.tgme_widget_message_views")
        if not mid:
            continue
        posts.append({
            "id": int(mid) if mid.isdigit() else mid,
            "datetime": t.get("datetime", "") if t else "",
            "text": tx.get_text("\n", strip=True) if tx else "",
            "views": parse_views(views.get_text() if views else ""),
            "url": "https://t.me/%s/%s" % (username, mid),
        })
    return posts


def fetch_history(username, session, since):
    """Все посты канала не старше since. Листаем назад через ?before=<id>."""
    collected, before, pages = {}, None, 0
    while pages < MAX_PAGES:
        url = "https://t.me/s/%s" % username
        params = {"before": before} if before else None
        try:
            r = session.get(url, params=params, timeout=40)
        except Exception as e:
            return list(collected.values()), str(e)[:100]
        if r.status_code != 200:
            return list(collected.values()), "HTTP %s" % r.status_code

        page = parse_page(r.text, username)
        if not page:
            break
        pages += 1

        ids = [p["id"] for p in page if isinstance(p["id"], int)]
        fresh = 0
        for p in page:
            if p["datetime"][:10] >= since:
                collected[p["id"]] = p
                fresh += 1
        oldest = min((p["datetime"][:10] for p in page if p["datetime"]), default="")

        # дошли до постов старше нужной даты — дальше только глубже в прошлое
        if oldest and oldest < since:
            break
        if not ids:
            break
        nxt = min(ids)
        if before is not None and nxt >= before:
            break  # лента не двигается — выходим, чтобы не крутиться вечно
        before = nxt
        time.sleep(PAUSE)

    posts = sorted(collected.values(), key=lambda p: p["datetime"], reverse=True)
    return posts, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    seed = load_json(SEED, {}) or {}
    live = [v for v in seed.values() if v.get("posts")]  # только каналы с превью
    done = load_json(OUT, {}) or {}
    todo = live if a.refresh else [c for c in live if c["username"] not in done]
    if a.limit:
        todo = todo[:a.limit]

    print("каналов с превью: %d, собрано: %d, к загрузке: %d (посты с %s)"
          % (len(live), len(done), len(todo), a.since))
    if not todo:
        return

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    for i, c in enumerate(todo, 1):
        posts, err = fetch_history(c["username"], session, a.since)
        done[c["username"]] = {
            "username": c["username"], "company": c.get("company", ""),
            "group": c.get("group", ""), "stands": c.get("stands") or [],
            "posts": posts, "error": err,
        }
        print("[%d/%d] @%-24s %4d постов%s"
              % (i, len(todo), c["username"][:24], len(posts),
                 (" (%s)" % err) if err else ""))
        if i % 10 == 0:
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(done, f, ensure_ascii=False, indent=1)
        time.sleep(PAUSE)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)

    total = sum(len(v["posts"]) for v in done.values())
    print("готово: каналов %d, постов за период %d" % (len(done), total))


if __name__ == "__main__":
    main()
