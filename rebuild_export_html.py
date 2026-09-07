# -*- coding: utf-8 -*-
"""Пересборка index.html справки канала: посты канала (текст+картинки+файлы из ТГ)
+ скачанные с Google Drive PDF (materials/manifest.json), привязанные к постам.
Запуск: python rebuild_export_html.py"""
import os, sys, json, re, html
sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "export_marketguru_gifts")
UNAME = "marketguru_gifts"; TITLE = "Ништяки от MarketGuru"

posts = [json.loads(l) for l in open(os.path.join(EXPORT, "posts.jsonl"), encoding="utf-8")]
mpath = os.path.join(EXPORT, "materials", "manifest.json")
manifest = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else []
by_post = {}
for m in manifest:
    if m.get("file"):
        by_post.setdefault(m["post_id"], []).append(m)


def fmt_size(n):
    n = n or 0
    for u in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024: return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} ТБ"


def linkify(text):
    text = html.escape(text or "")
    text = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank">\1</a>', text)
    return text.replace("\n", "<br>")


# группировка альбомов
groups = []; idx = {}
for p in posts:
    g = p.get("grouped_id")
    if g and g in idx:
        grp = idx[g]; grp["media"] += p["media"]
        if p["text"] and not grp["text"]: grp["text"] = p["text"]
        grp["ids"].append(p["id"])
    else:
        grp = {"id": p["id"], "ids": [p["id"]], "date": p["date"], "text": p["text"],
               "link": p["link"], "media": list(p["media"])}
        groups.append(grp)
        if g: idx[g] = grp

n_media = sum(len(g["media"]) for g in groups)
n_pdf = sum(1 for m in manifest if m.get("file"))
mats_sorted = sorted([m for m in manifest if m.get("file")], key=lambda x: x.get("num", 0))

css = """
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f5f6f8;color:#1a1a1a;margin:0;padding:24px;}
h1{font-size:24px;margin:0 0 4px;} h2{font-size:18px;margin:24px 0 10px;border-left:4px solid #7b1fa2;padding-left:10px;}
.sub{color:#666;margin-bottom:16px;}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0;}
.stat{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:10px 18px;text-align:center;}
.stat .n{font-size:22px;font-weight:800;color:#7b1fa2;} .stat .l{font-size:12px;color:#777;}
.wrap{max-width:820px;}
.mats{display:grid;grid-template-columns:1fr;gap:8px;margin-bottom:8px;}
.mat{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 14px;text-decoration:none;color:#1a1a1a;}
.mat:hover{border-color:#7b1fa2;} .mat .ic{font-size:20px;} .mat .nm{font-weight:600;font-size:14px;} .mat .sz{color:#888;font-size:12px;margin-left:auto;}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:14px 16px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
.head{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
.date{color:#999;font-size:12px;} .open{margin-left:auto;font-size:13px;color:#0088cc;text-decoration:none;}
.text{font-size:14px;line-height:1.5;color:#222;}
.imgs{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}
.imgs img{max-width:220px;max-height:220px;border-radius:8px;border:1px solid #e3e6ea;object-fit:cover;}
.dl{display:inline-flex;align-items:center;gap:8px;background:#f3e5f5;border:1px solid #e1bee7;border-radius:8px;
    padding:9px 13px;margin-top:10px;text-decoration:none;color:#6a1b9a;font-size:13px;font-weight:600;}
"""
H = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">',
     '<meta name="viewport" content="width=device-width,initial-scale=1">',
     f'<title>Архив канала {html.escape(TITLE)}</title><style>{css}</style></head><body>',
     f'<h1>Архив Telegram-канала: {html.escape(TITLE)}</h1>',
     f'<div class="sub">@{UNAME} • <a href="https://t.me/{UNAME}" target="_blank">открыть в Telegram</a> • '
     'посты, картинки и файлы сохранены локально. PDF-материалы скачаны с Google Drive в папку materials/.</div>',
     '<div class="stats">'
     f'<div class="stat"><div class="n">{len(groups)}</div><div class="l">постов</div></div>'
     f'<div class="stat"><div class="n">{n_media}</div><div class="l">картинок</div></div>'
     f'<div class="stat"><div class="n">{n_pdf}</div><div class="l">PDF-материалов</div></div>'
     '</div>', '<div class="wrap">']

# раздел: все скачанные материалы
H.append('<h2>📚 Скачанные материалы (PDF) — база знаний по WB/Ozon</h2>')
H.append('<div class="mats">')
for m in mats_sorted:
    nm = html.escape(re.sub(r"^\d+\.\s*", "", m["title"]))
    H.append(f'<a class="mat" href="{html.escape(m["file"])}" target="_blank">'
             f'<span class="ic">📄</span><span class="nm">{m["num"]}. {nm}</span>'
             f'<span class="sz">{fmt_size(m.get("size"))}</span></a>')
H.append('</div>')

# лента постов
H.append('<h2>📨 Посты канала</h2>')
for g in groups:
    H.append('<div class="card">')
    H.append(f'<div class="head"><span class="date">{html.escape(g["date"])}</span>'
             f'<a class="open" href="{html.escape(g["link"])}" target="_blank">↗ в Telegram</a></div>')
    if g["text"]:
        H.append(f'<div class="text">{linkify(g["text"])}</div>')
    imgs = [x for x in g["media"] if x["type"] in ("photo", "image")]
    if imgs:
        H.append('<div class="imgs">')
        for x in imgs:
            H.append(f'<a href="{html.escape(x["file"])}" target="_blank"><img loading="lazy" src="{html.escape(x["file"])}"></a>')
        H.append('</div>')
    # скачанные PDF, относящиеся к постам этой группы
    mats = []
    for pid in g["ids"]:
        mats += by_post.get(pid, [])
    for m in mats:
        nm = html.escape(re.sub(r"^\d+\.\s*", "", m["title"]))
        H.append(f'<a class="dl" href="{html.escape(m["file"])}" target="_blank">📄 Скачанный материал: {nm} ({fmt_size(m.get("size"))})</a>')
    H.append('</div>')
H.append('</div></body></html>')

with open(os.path.join(EXPORT, "index.html"), "w", encoding="utf-8") as f:
    f.write("\n".join(H))
print("OK ->", os.path.join(EXPORT, "index.html"))
print(f"постов: {len(groups)} | картинок: {n_media} | PDF: {n_pdf}")
