# -*- coding: utf-8 -*-
"""Скачивание материалов с Google Drive (ссылки из постов канала) через Playwright.
Аккуратно, с задержками. Сохраняет в export_marketguru_gifts/materials/ + manifest.

Запуск: <parent_venv>/python download_drive.py
Читает export_marketguru_gifts/posts.jsonl, пишет materials/manifest.json."""
import os, sys, json, re, time
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "export_marketguru_gifts")
MAT = os.path.join(EXPORT, "materials")
os.makedirs(MAT, exist_ok=True)
SLEEP = 2.5

def collect():
    rows = [json.loads(l) for l in open(os.path.join(EXPORT, "posts.jsonl"), encoding="utf-8")]
    items = []
    seen = set()
    for r in rows:
        for m in re.finditer(r"https://drive\.google\.com/file/d/([\w-]+)", r["text"]):
            fid = m.group(1)
            if fid in seen: continue
            seen.add(fid)
            first = (r["text"].splitlines()[0] if r["text"] else "").strip()
            num = (re.match(r"(\d+)\.", first) or [None, "00"])[1]
            items.append({"fid": fid, "title": first, "num": int(num) if str(num).isdigit() else 0,
                          "post_id": r["id"], "post_link": r["link"]})
    items.sort(key=lambda x: x["num"])
    return items

def safe(s): return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)[:80]

def download_one(page, fid, dest_base):
    url = f"https://drive.google.com/uc?export=download&id={fid}"
    # попытка 1: прямое скачивание (навигация превращается в download -> ERR_ABORTED)
    try:
        with page.expect_download(timeout=25000) as di:
            try: page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception: pass
        dl = di.value
        return finalize(dl, dest_base)
    except PWTimeout:
        pass
    # попытка 2: страница-подтверждение вируса -> жмём кнопку/сабмитим форму
    try:
        with page.expect_download(timeout=25000) as di:
            clicked = False
            for sel in ["#uc-download-link", "form#download-form [type=submit]",
                        "#download-form button", "a#uc-download-link"]:
                el = page.query_selector(sel)
                if el:
                    el.click(); clicked = True; break
            if not clicked:
                # форма с confirm-токеном
                form = page.query_selector("form#download-form")
                if form:
                    page.evaluate("document.getElementById('download-form').submit()")
        dl = di.value
        return finalize(dl, dest_base)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:80]}"}

def finalize(dl, dest_base):
    suggested = dl.suggested_filename or "file"
    ext = os.path.splitext(suggested)[1] or ".bin"
    fname = safe(dest_base) + ext
    path = os.path.join(MAT, fname)
    dl.save_as(path)
    return {"file": f"materials/{fname}", "orig_name": suggested,
            "size": os.path.getsize(path) if os.path.exists(path) else 0}

def main():
    items = collect()
    print(f"К скачиванию с Google Drive: {len(items)}")
    manifest = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
        page = ctx.new_page()
        for i, it in enumerate(items, 1):
            base = f"{it['num']:02d}_{safe(re.sub(r'^\d+\.\s*','',it['title']))}"
            res = download_one(page, it["fid"], base)
            rec = {**it, **res}
            manifest.append(rec)
            ok = "OK " + res.get("file", "") + f" ({res.get('size',0)//1024} КБ)" if "file" in res else "ERR " + res.get("error", "")
            print(f"[{i}/{len(items)}] #{it['num']} {it['title'][:45]} -> {ok}")
            time.sleep(SLEEP)
        browser.close()
    json.dump(manifest, open(os.path.join(MAT, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    okn = sum(1 for m in manifest if m.get("file"))
    print(f"Готово: {okn}/{len(manifest)} скачано -> {MAT}")

main()
