# -*- coding: utf-8 -*-
"""Добор каналов через ВЕБ-превью t.me/s/<username> (без Telegram API, без FloodWait).
Тянет HTML публичного канала через SOCKS5-прокси, парсит последние посты,
классифицирует через DeepSeek. Дописывает в тот же tg_results.jsonl (resume).
Запуск: python web_collect.py            # все недостающие
        python web_collect.py --limit 20 # пилот
Поля совпадают с tg_collect.py."""
import os, io, sys, json, time, argparse, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
load_dotenv(r"C:\Users\Yuri\PycharmProjects\PythonProject\tg-analysis\.env")  # DeepSeek key
DS_KEY = os.environ["DEEPSEEK_API_KEY"]
POSTS = 10
SLEEP = 1.0
RESULTS = "tg_results.jsonl"
PROXY = "socks5h://127.0.0.1:10808"          # тот же локальный прокси (Global)
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
        return {"error": str(e)[:120], "invites_ecom_expo": False, "giveaway": False}


def fetch_posts(username):
    """Возвращает (posts, err). posts отсортированы новые-первыми."""
    url = f"https://t.me/s/{username}"
    r = requests.get(url, headers={"User-Agent": UA}, proxies=PROXIES, timeout=40)
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"
    soup = BeautifulSoup(r.text, "html.parser")
    blocks = soup.select("div.tgme_widget_message")
    if not blocks:
        # нет публичного превью (приватный/закрыт/нет постов)
        return [], "no_preview"
    posts = []
    for b in blocks:
        post_id = b.get("data-post", "")  # "username/123"
        mid = post_id.split("/")[-1] if "/" in post_id else ""
        tx = b.select_one("div.tgme_widget_message_text")
        text = tx.get_text("\n", strip=True) if tx else ""
        t = b.select_one("a.tgme_widget_message_date time")
        date = (t.get("datetime", "")[:10] if t else "")
        link = f"https://t.me/{username}/{mid}" if mid else f"https://t.me/{username}"
        posts.append({"id": mid, "date": date, "text": text, "link": link})
    posts = posts[-POSTS:][::-1]  # последние POSTS, новые первыми
    return posts, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    chans = json.load(open("tg_channels.json", encoding="utf-8"))
    done = set()
    if os.path.exists(RESULTS):
        for l in open(RESULTS, encoding="utf-8"):
            try: done.add(json.loads(l)["username"].lower())
            except Exception: pass
    todo = [c for c in chans if c["username"].lower() not in done]
    if args.limit: todo = todo[:args.limit]
    print(f"Всего: {len(chans)} | готово: {len(done)} | к добору (веб): {len(todo)}")

    out = open(RESULTS, "a", encoding="utf-8")
    for i, c in enumerate(todo, 1):
        u = c["username"]; rec = {"username": u, "company": c.get("company", ""), "source": "web"}
        try:
            posts, err = fetch_posts(u)
            if err:
                rec["error"] = err
            else:
                rec["posts_count"] = len(posts)
                rec["last_date"] = posts[0]["date"] if posts else ""
                cls = classify(c.get("company", ""), u, posts)
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
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        flag = ("EXPO" if rec.get("invites_ecom_expo") else "") + ("+GIVE" if rec.get("giveaway") else "")
        print(f"[{i}/{len(todo)}] @{u} {flag} {rec.get('error','')}")
        time.sleep(SLEEP)
    out.close()
    print("Готово.")

main()
