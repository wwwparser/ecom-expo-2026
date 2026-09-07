# -*- coding: utf-8 -*-
"""Обновление уже собранных expo-каналов через ВЕБ-превью t.me/s/ (без Telegram API, без FloodWait).
Перетягивает свежие посты (live-дни выставки) и переклассифицирует через DeepSeek,
ОБНОВЛЯЯ существующие записи в tg_results.jsonl на месте.
По умолчанию обновляет каналы, которые звали на ECOM Expo ИЛИ имеют розыгрыш.
Запуск: python refresh_expo.py            # обновить expo+give каналы
        python refresh_expo.py --all      # обновить все веб-доступные каналы
Файл переписывается целиком (предварительно делает бэкап)."""
import os, io, sys, json, time, argparse, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
load_dotenv(r"C:\Users\Yuri\PycharmProjects\PythonProject\tg-analysis\.env")
DS_KEY = os.environ["DEEPSEEK_API_KEY"]
POSTS = 10
SLEEP = 1.0
RESULTS = "tg_results.jsonl"
PROXY = "socks5h://127.0.0.1:10808"
PROXIES = {"http": PROXY, "https": PROXY}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

SCHEMA_HINT = (
    'Верни ТОЛЬКО JSON: {"invites_ecom_expo": true/false, "expo_quote": "цитата или \\"\\"", '
    '"expo_post": номер поста с приглашением (целое) или 0, '
    '"giveaway": true/false, "giveaway_what": "что разыгрывают/мерч/призы или \\"\\"", '
    '"giveaway_conditions": "условия/дедлайн или \\"\\"", '
    '"giveaway_post": номер поста с розыгрышем/мерчем/призами (целое) или 0, '
    '"summary": "1 фраза о канале"}')


def classify(company, username, posts):
    numbered = "\n\n".join(f"#{i+1} [{p['date']}] {p['text']}" for i, p in enumerate(posts) if p.get("text"))[:7000]
    if not numbered.strip():
        return {"invites_ecom_expo": False, "expo_quote": "", "expo_post": 0, "giveaway": False,
                "giveaway_what": "", "giveaway_conditions": "", "giveaway_post": 0, "summary": "нет текстовых постов"}
    prompt = (f"Компания: {company or username}. Ниже последние посты её Telegram-канала @{username}, "
              "каждый помечен номером #N.\n"
              "Определи: (1) приглашают ли посетить выставку ECOM Expo (ЭКОМ Экспо, ecom expo) — "
              "если да, дай короткую цитату, стенд/дату при наличии и НОМЕР поста; "
              "(2) проводят ли розыгрыш/конкурс/giveaway/раздачу мерча или призов — что именно разыгрывают "
              "(мерч, подарки, призы), условия, дедлайн и НОМЕР поста.\n"
              + SCHEMA_HINT + "\n\nПОСТЫ:\n" + numbered)
    try:
        r = requests.post("https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DS_KEY}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0, "max_tokens": 400, "response_format": {"type": "json_object"}},
            timeout=60)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        return {"_classify_error": str(e)[:120]}


def fetch_posts(username):
    url = f"https://t.me/s/{username}"
    r = requests.get(url, headers={"User-Agent": UA}, proxies=PROXIES, timeout=40)
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"
    soup = BeautifulSoup(r.text, "html.parser")
    blocks = soup.select("div.tgme_widget_message")
    if not blocks:
        return [], "no_preview"
    posts = []
    for b in blocks:
        post_id = b.get("data-post", "")
        mid = post_id.split("/")[-1] if "/" in post_id else ""
        tx = b.select_one("div.tgme_widget_message_text")
        text = tx.get_text("\n", strip=True) if tx else ""
        t = b.select_one("a.tgme_widget_message_date time")
        date = (t.get("datetime", "")[:10] if t else "")
        link = f"https://t.me/{username}/{mid}" if mid else f"https://t.me/{username}"
        posts.append({"id": mid, "date": date, "text": text, "link": link})
    posts = posts[-POSTS:][::-1]
    return posts, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="обновить все веб-доступные, а не только expo/give")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]
    by_user = {r["username"].lower(): r for r in rows}

    if args.all:
        targets = [r for r in rows if not r.get("error")]
    else:
        targets = [r for r in rows if (r.get("invites_ecom_expo") or r.get("giveaway")) and not r.get("error")]
    if args.limit:
        targets = targets[:args.limit]
    print(f"Записей: {len(rows)} | к обновлению через веб: {len(targets)}")

    shutil.copy(RESULTS, RESULTS.replace(".jsonl", "_before_refresh.jsonl"))

    updated = found_new = 0
    for i, old in enumerate(targets, 1):
        u = old["username"]
        try:
            posts, err = fetch_posts(u)
            if err:
                print(f"[{i}/{len(targets)}] @{u} -> {err} (оставляю прежние данные)")
                time.sleep(SLEEP); continue
            cls = classify(old.get("company", ""), u, posts)
            if "_classify_error" in cls:
                print(f"[{i}/{len(targets)}] @{u} classify err: {cls['_classify_error']} (оставляю прежние)")
                time.sleep(SLEEP); continue
            new_last = posts[0]["date"] if posts else ""
            prev_last = old.get("last_date", "")
            rec = by_user[u.lower()]
            rec["company"] = old.get("company", "")
            rec["source"] = "web-refresh"
            rec["posts_count"] = len(posts)
            rec["last_date"] = new_last
            rec.update(cls)
            rec["post_links"] = [p["link"] for p in posts]

            def post_for(n):
                try: n = int(n)
                except Exception: return None
                return posts[n-1] if 1 <= n <= len(posts) else None
            ep = post_for(cls.get("expo_post", 0)); gp = post_for(cls.get("giveaway_post", 0))
            rec["expo_link"] = ep["link"] if ep else ""
            rec["expo_post_text"] = ep["text"] if ep else ""
            rec["giveaway_link"] = gp["link"] if gp else ""
            rec["giveaway_post_text"] = gp["text"] if gp else ""
            rec.pop("error", None)
            updated += 1
            fresh = " 🆕СВЕЖЕЕ" if new_last > prev_last else ""
            flag = ("EXPO" if rec.get("invites_ecom_expo") else "") + ("+GIVE" if rec.get("giveaway") else "")
            if fresh: found_new += 1
            print(f"[{i}/{len(targets)}] @{u} {flag} {prev_last}->{new_last}{fresh}")
        except Exception as e:
            print(f"[{i}/{len(targets)}] @{u} EXC {type(e).__name__}: {str(e)[:80]} (оставляю прежние)")
        time.sleep(SLEEP)

    with open(RESULTS, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Готово. Обновлено: {updated} | со свежими постами: {found_new}")


main()
