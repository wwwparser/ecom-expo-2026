# -*- coding: utf-8 -*-
"""
Сбор последних N постов Telegram-каналов + классификация через DeepSeek:
  - приглашают ли на выставку ECOM Expo;
  - какие розыгрыши/конкурсы проводят.
Запускается НА СЕРВЕРЕ, где открыт Telegram. Telethon + авторизованная сессия.

ENV: TELEGRAM_API_ID, TELEGRAM_API_HASH, DEEPSEEK_API_KEY
Файлы рядом: telegram_session.session, tg_channels.json
Запуск: python3 tg_collect.py --limit 25         # пилот
        python3 tg_collect.py                     # все каналы (resume)
Выход: tg_results.jsonl (по записи на канал, дозапись/resume)
"""
import os, io, sys, json, time, argparse, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
load_dotenv(r"C:\Users\Yuri\PycharmProjects\PythonProject\tg-analysis\.env")  # DeepSeek key
API_ID = int(os.environ["TELEGRAM_API_ID"]); API_HASH = os.environ["TELEGRAM_API_HASH"]
DS_KEY = os.environ["DEEPSEEK_API_KEY"]
SESSION = "sf_session"
PROXY = ('socks5', '127.0.0.1', 10808)
POSTS = 10
SLEEP = 4.0            # пауза между каналами (резолв юзернеймов чувствителен к флуду)
FLOOD_WAIT_OK = 120   # короткий FloodWait — подождать и продолжить; больше — остановиться
RESULTS = "tg_results.jsonl"

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


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="сколько каналов (0 = все)")
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    chans = json.load(open("tg_channels.json", encoding="utf-8"))
    done = set()
    if os.path.exists(RESULTS):
        for l in open(RESULTS, encoding="utf-8"):
            try: done.add(json.loads(l)["username"].lower())
            except Exception: pass
    todo = [c for c in chans[args.offset:] if c["username"].lower() not in done]
    if args.limit: todo = todo[:args.limit]
    print(f"Каналов всего: {len(chans)} | уже готово: {len(done)} | к обработке: {len(todo)}")

    client = TelegramClient(SESSION, API_ID, API_HASH, proxy=PROXY)
    await client.connect()
    if not await client.is_user_authorized():
        print("СЕССИЯ НЕ АВТОРИЗОВАНА"); return
    print("Telegram OK:", (await client.get_me()).first_name)

    out = open(RESULTS, "a", encoding="utf-8")
    i = 0
    while i < len(todo):
        c = todo[i]; i += 1
        u = c["username"]; rec = {"username": u, "company": c.get("company", "")}
        try:
            msgs = await client.get_messages(u, limit=POSTS)
            posts = [{"id": m.id, "date": f"{m.date:%Y-%m-%d}",
                      "text": (m.message or "").strip(),
                      "link": f"https://t.me/{u}/{m.id}"} for m in msgs]
            rec["posts_count"] = len(posts)
            rec["last_date"] = posts[0]["date"] if posts else ""
            cls = classify(c.get("company", ""), u, posts)
            rec.update(cls)
            rec["post_links"] = [p["link"] for p in posts]
            # прямые ссылки на конкретные посты (приглашение / розыгрыш-мерч-призы)
            def post_for(n):
                try: n = int(n)
                except Exception: return None
                return posts[n-1] if 1 <= n <= len(posts) else None
            ep = post_for(cls.get("expo_post", 0)); gp = post_for(cls.get("giveaway_post", 0))
            rec["expo_link"] = ep["link"] if ep else ""
            rec["expo_post_text"] = ep["text"] if ep else ""
            rec["giveaway_link"] = gp["link"] if gp else ""
            rec["giveaway_post_text"] = gp["text"] if gp else ""
        except FloodWaitError as e:
            if e.seconds <= FLOOD_WAIT_OK:
                print(f"[{i}/{len(todo)}] @{u} FloodWait {e.seconds}s — ждём и повторяем…")
                time.sleep(e.seconds + 2); i -= 1; continue   # повторить тот же канал
            # большой FloodWait — НЕ пишем ошибку в результаты, аккуратно останавливаемся
            print(f"\n⛔ FloodWait {e.seconds}s (~{e.seconds//3600} ч) на @{u}. "
                  f"Обработано {i-1}/{len(todo)} из этого запуска. "
                  f"Запусти снова через ~{e.seconds//3600+1} ч — resume докачает остаток.")
            break
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        flag = ("EXPO" if rec.get("invites_ecom_expo") else "") + ("+GIVE" if rec.get("giveaway") else "")
        print(f"[{i}/{len(todo)}] @{u} {flag} {rec.get('error','')}")
        time.sleep(SLEEP)
    out.close()
    await client.disconnect()
    print("Готово.")

asyncio.run(main())
