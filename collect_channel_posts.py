# -*- coding: utf-8 -*-
"""Последние посты Telegram-каналов участников выставки — через веб-превью.

Берём t.me/s/<username>: публичная HTML-версия канала, без Telegram API,
без авторизации и без FloodWait. Отсюда же приезжают дата с временем
и счётчик просмотров, которых нет в старом tg_results.jsonl (там только
классификация постов и ссылки).

Каналы берём из tg_channels.json, но только те, чья компания есть среди
участников 2026 — лента должна быть про тех, кто стоит на выставке.

Запуск: python collect_channel_posts.py             # все каналы участников
        python collect_channel_posts.py --limit 10  # пилот
        python collect_channel_posts.py --refresh   # перекачать уже собранные
Выход:  data/raw/channel_posts.json (resume: собранные каналы пропускаются)
"""
import argparse
import io
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Импорт строго до подмены stdout: expo_adapter сам оборачивает sys.stdout,
# и наша обёртка, сделанная раньше, оказалась бы закрытой.
from expo_adapter import norm_name  # noqa: E402  (общая нормализация имён компаний)

if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "raw", "channel_posts.json")
EXHIBITORS = os.path.join(HERE, "data", "site", "exhibitors.json")
CHANNELS = os.path.join(HERE, "tg_channels.json")

POSTS_PER_CHANNEL = 10
PAUSE = 1.0
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_views(raw):
    """«1.2K» / «3.4M» -> число. Telegram округляет — точность не нужна."""
    raw = (raw or "").strip().upper().replace(",", ".")
    m = re.match(r"^([\d.]+)([KM]?)$", raw)
    if not m:
        return None
    val = float(m.group(1))
    return int(val * {"": 1, "K": 1000, "M": 1000000}[m.group(2)])


def fetch_posts(username, session):
    """Последние посты канала, новые первыми. Возвращает (posts, error)."""
    r = session.get("https://t.me/s/%s" % username, timeout=40)
    if r.status_code != 200:
        return [], "HTTP %s" % r.status_code
    soup = BeautifulSoup(r.text, "html.parser")
    blocks = soup.select("div.tgme_widget_message")
    if not blocks:
        # приватный канал, только чат, или превью отключено
        return [], "no_preview"

    posts = []
    for b in blocks:
        post_id = b.get("data-post", "")
        mid = post_id.split("/")[-1] if "/" in post_id else ""
        tx = b.select_one("div.tgme_widget_message_text")
        text = tx.get_text("\n", strip=True) if tx else ""
        t = b.select_one("a.tgme_widget_message_date time")
        views = b.select_one("span.tgme_widget_message_views")
        posts.append({
            "id": mid,
            "datetime": t.get("datetime", "") if t else "",
            "text": text,
            "views": parse_views(views.get_text() if views else ""),
            "url": "https://t.me/%s/%s" % (username, mid) if mid else "https://t.me/%s" % username,
            "has_media": bool(b.select_one(".tgme_widget_message_photo, "
                                           ".tgme_widget_message_video, "
                                           ".tgme_widget_message_document")),
        })
    # превью отдаёт хвост ленты по возрастанию — берём последние и переворачиваем
    posts = posts[-POSTS_PER_CHANNEL:][::-1]
    return posts, None


def target_channels():
    """Каналы компаний, которые есть среди участников 2026."""
    exhibitors = load_json(EXHIBITORS, []) or []
    by_name = {norm_name(x["name"]): x for x in exhibitors}
    out, seen = [], set()
    for ch in load_json(CHANNELS, []) or []:
        key = norm_name(ch.get("company"))
        x = by_name.get(key)
        user = (ch.get("username") or "").strip()
        if not x or not user or user.lower() in seen:
            continue
        seen.add(user.lower())
        out.append({"username": user, "company": x["name"],
                    "group": x.get("group", ""), "stands": x.get("stands") or []})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="перекачать уже собранные")
    a = ap.parse_args()

    channels = target_channels()
    done = load_json(OUT, {}) or {}
    todo = channels if a.refresh else [c for c in channels if c["username"] not in done]
    if a.limit:
        todo = todo[:a.limit]

    print("каналов участников: %d, собрано: %d, к загрузке: %d"
          % (len(channels), len(done), len(todo)))
    if not todo:
        return

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    ok = 0
    for i, c in enumerate(todo, 1):
        try:
            posts, err = fetch_posts(c["username"], session)
        except Exception as e:
            posts, err = [], str(e)[:120]
        rec = dict(c)
        rec["posts"] = posts
        rec["error"] = err or ""
        done[c["username"]] = rec
        if posts:
            ok += 1
        print("[%d/%d] @%-24s %s" % (i, len(todo), c["username"][:24],
                                     ("%d постов" % len(posts)) if posts else "— %s" % err))
        if i % 20 == 0:
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(done, f, ensure_ascii=False, indent=1)
        time.sleep(PAUSE)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)

    total = sum(len(v.get("posts") or []) for v in done.values())
    print("готово: каналов с постами %d, постов всего %d"
          % (sum(1 for v in done.values() if v.get("posts")), total))


if __name__ == "__main__":
    main()
