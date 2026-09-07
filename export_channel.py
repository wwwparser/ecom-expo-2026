# -*- coding: utf-8 -*-
"""Экспорт Telegram-канала в HTML-справку: все посты + картинки + файлы.
Аккуратно, с задержками. Использует рабочую сессию sf_session через SOCKS5-прокси.

Запуск: python export_channel.py marketguru_gifts
        python export_channel.py marketguru_gifts --limit 50   # пилот
Выход:  папка export_<username>/  с index.html, media/, posts.jsonl
Resume: уже скачанные медиа не качаются повторно (по имени файла)."""
import os, io, sys, json, time, html, argparse, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import (MessageMediaPhoto, MessageMediaDocument,
                               DocumentAttributeFilename, MessageMediaWebPage)

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
API_ID = int(os.environ["TELEGRAM_API_ID"]); API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = "sf_session"
PROXY = ('socks5', '127.0.0.1', 10808)
SLEEP_DL = 1.2      # пауза после скачивания каждого медиа
SLEEP_MSG = 0.25    # пауза между постами


def safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)[:120]


def doc_filename(doc):
    for a in getattr(doc, "attributes", []):
        if isinstance(a, DocumentAttributeFilename):
            return a.file_name
    return ""


def linkify(text):
    text = html.escape(text or "")
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank">\1</a>', text)
    return text.replace("\n", "<br>")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    uname = args.username.lstrip("@")

    outdir = os.path.join(HERE, f"export_{safe_name(uname)}")
    media_dir = os.path.join(outdir, "media")
    os.makedirs(media_dir, exist_ok=True)
    posts_path = os.path.join(outdir, "posts.jsonl")

    client = TelegramClient(SESSION, API_ID, API_HASH, proxy=PROXY)
    await client.connect()
    if not await client.is_user_authorized():
        print("СЕССИЯ НЕ АВТОРИЗОВАНА"); return
    me = await client.get_me(); print("Telegram OK:", me.first_name)

    ent = await client.get_entity(uname)
    title = getattr(ent, "title", uname)
    print(f"Канал: {title} (@{uname}) id={ent.id}")

    posts = []
    posts_out = open(posts_path, "w", encoding="utf-8")
    i = 0
    async for m in client.iter_messages(ent, limit=(args.limit or None)):
        i += 1
        rec = {"id": m.id, "date": m.date.strftime("%Y-%m-%d %H:%M") if m.date else "",
               "text": (m.message or ""), "link": f"https://t.me/{uname}/{m.id}",
               "grouped_id": getattr(m, "grouped_id", None), "media": []}
        try:
            if m.media and not isinstance(m.media, MessageMediaWebPage):
                if isinstance(m.media, MessageMediaPhoto):
                    fn = f"{m.id}.jpg"; path = os.path.join(media_dir, fn)
                    if not os.path.exists(path):
                        await m.download_media(file=path); time.sleep(SLEEP_DL)
                    rec["media"].append({"type": "photo", "file": f"media/{fn}"})
                elif isinstance(m.media, MessageMediaDocument):
                    doc = m.media.document
                    orig = doc_filename(doc) or f"{m.id}.bin"
                    fn = f"{m.id}_{safe_name(orig)}"; path = os.path.join(media_dir, fn)
                    mime = getattr(doc, "mime_type", "") or ""
                    if not os.path.exists(path):
                        await m.download_media(file=path); time.sleep(SLEEP_DL)
                    kind = "image" if mime.startswith("image/") else (
                           "video" if mime.startswith("video/") else "file")
                    rec["media"].append({"type": kind, "file": f"media/{fn}",
                                         "name": orig, "mime": mime,
                                         "size": getattr(doc, "size", 0)})
        except FloodWaitError as e:
            print(f"FloodWait {e.seconds}s — жду…"); time.sleep(e.seconds + 2)
        except Exception as e:
            rec["media_error"] = f"{type(e).__name__}: {str(e)[:80]}"
        posts.append(rec)
        posts_out.write(json.dumps(rec, ensure_ascii=False) + "\n"); posts_out.flush()
        mflag = "".join("🖼" if x["type"] in ("photo", "image") else "📎" for x in rec["media"])
        print(f"[{i}] #{m.id} {rec['date']} {mflag} {rec['text'][:50].strip()!r}")
        time.sleep(SLEEP_MSG)
    posts_out.close()
    await client.disconnect()
    print(f"Скачано постов: {len(posts)}. Собираю HTML…")
    build_html(outdir, uname, title, posts)
    print(f"Готово -> {os.path.join(outdir, 'index.html')}")


def fmt_size(n):
    n = n or 0
    for u in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024: return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} ТБ"


def build_html(outdir, uname, title, posts):
    # сгруппировать альбомы (одинаковый grouped_id) в одну карточку
    groups = []; idx = {}
    for p in posts:
        g = p["grouped_id"]
        if g and g in idx:
            grp = idx[g]
            grp["media"] += p["media"]
            if p["text"] and not grp["text"]: grp["text"] = p["text"]
        else:
            grp = {"id": p["id"], "date": p["date"], "text": p["text"],
                   "link": p["link"], "media": list(p["media"])}
            groups.append(grp)
            if g: idx[g] = grp
    n_media = sum(len(g["media"]) for g in groups)
    n_files = sum(1 for g in groups for x in g["media"] if x["type"] == "file")

    css = """
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f5f6f8;color:#1a1a1a;margin:0;padding:24px;}
h1{font-size:24px;margin:0 0 4px;} .sub{color:#666;margin-bottom:16px;}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0;}
.stat{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:10px 18px;text-align:center;}
.stat .n{font-size:22px;font-weight:800;color:#0088cc;} .stat .l{font-size:12px;color:#777;}
.feed{max-width:760px;}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:14px 16px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
.head{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
.date{color:#999;font-size:12px;} .open{margin-left:auto;font-size:13px;color:#0088cc;text-decoration:none;}
.text{font-size:14px;line-height:1.5;color:#222;white-space:normal;}
.imgs{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}
.imgs img,.imgs video{max-width:240px;max-height:240px;border-radius:8px;border:1px solid #e3e6ea;object-fit:cover;}
.files{margin-top:10px;}
.file{display:inline-flex;align-items:center;gap:8px;background:#eef4fb;border:1px solid #d7e6f5;border-radius:8px;
      padding:8px 12px;margin:4px 6px 0 0;text-decoration:none;color:#0a558c;font-size:13px;}
"""
    H = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>Архив канала {html.escape(title)}</title><style>{css}</style></head><body>',
         f'<h1>Архив Telegram-канала: {html.escape(title)}</h1>',
         f'<div class="sub">@{html.escape(uname)} • <a href="https://t.me/{html.escape(uname)}" target="_blank">открыть в Telegram</a> • '
         'посты от новых к старым. Картинки и файлы сохранены локально в папке media/.</div>',
         '<div class="stats">'
         f'<div class="stat"><div class="n">{len(groups)}</div><div class="l">постов</div></div>'
         f'<div class="stat"><div class="n">{n_media}</div><div class="l">медиа</div></div>'
         f'<div class="stat"><div class="n">{n_files}</div><div class="l">файлов</div></div>'
         '</div>', '<div class="feed">']
    for g in groups:
        H.append('<div class="card">')
        H.append(f'<div class="head"><span class="date">{html.escape(g["date"])}</span>'
                 f'<a class="open" href="{html.escape(g["link"])}" target="_blank">↗ в Telegram</a></div>')
        if g["text"]:
            H.append(f'<div class="text">{linkify(g["text"])}</div>')
        imgs = [x for x in g["media"] if x["type"] in ("photo", "image", "video")]
        files = [x for x in g["media"] if x["type"] == "file"]
        if imgs:
            H.append('<div class="imgs">')
            for x in imgs:
                if x["type"] == "video":
                    H.append(f'<video src="{html.escape(x["file"])}" controls preload="none"></video>')
                else:
                    H.append(f'<a href="{html.escape(x["file"])}" target="_blank">'
                             f'<img loading="lazy" src="{html.escape(x["file"])}"></a>')
            H.append('</div>')
        if files:
            H.append('<div class="files">')
            for x in files:
                nm = html.escape(x.get("name", "файл")); sz = fmt_size(x.get("size"))
                H.append(f'<a class="file" href="{html.escape(x["file"])}" download>📎 {nm} <span style="color:#888">({sz})</span></a>')
            H.append('</div>')
        H.append('</div>')
    H.append('</div></body></html>')
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(H))


asyncio.run(main())
