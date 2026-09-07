# -*- coding: utf-8 -*-
"""Проверка всей цепочки: страница по http://localhost -> клик -> запрос /tg на сервер.
Сервер в режиме TG_TEST=1 не запускает приложение, только подтверждает приём.
Цель: убедиться, что клик НАДЁЖНО доходит до локального сервера (который на деле
зовёт Telegram Desktop через os.startfile)."""
import sys, os, threading, socketserver
# РЕАЛЬНЫЙ режим: реально откроет Telegram Desktop на тестовом посте (финальная проверка).
from serve_report import Handler, TELEGRAM  # он сам настраивает utf-8 stdout
print("Telegram.exe:", TELEGRAM)
from playwright.sync_api import sync_playwright

PORT = 8755
hits = []

import urllib.parse as _u
class H(Handler):
    def do_GET(self):
        if _u.urlparse(self.path).path == "/tg":
            hits.append(self.path)
        return super().do_GET()

httpd = socketserver.TCPServer(("127.0.0.1", PORT), H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    responses = []
    page.on("response", lambda r: responses.append((r.status, r.url)) if "/tg" in r.url else None)
    resp = page.goto(f"http://127.0.0.1:{PORT}/tg_report.html", wait_until="load")
    print("goto статус:", resp.status if resp else "?", "| title:", page.title(),
          "| длина html:", len(page.content()), "| a.ch на странице:", page.locator("a.ch").count())

    # 1) ссылка канала в шапке
    chan = page.eval_on_selector("a.ch", "el=>el.href")
    print("ссылка канала (href, веб-фолбэк):", chan)
    # 2) кликаем ссылку на КОНКРЕТНЫЙ ПОСТ (href вида .../<число>) — проверяем форму &post=
    sel = "a[onclick^='return tgopen']"
    target = page.eval_on_selector(
        "a[onclick^='return tgopen']",
        "el=>{let a=[...document.querySelectorAll(\"a[onclick^='return tgopen']\")].find(x=>/t\\.me\\/[^/]+\\/\\d+/.test(x.href)); return a?a.href:el.href;}")
    print("кликаю ссылку на пост:", target)
    page.evaluate("""(href)=>{let a=[...document.querySelectorAll("a[onclick^='return tgopen']")].find(x=>x.href===href)||document.querySelector("a[onclick^='return tgopen']"); a.click();}""", target)
    page.wait_for_timeout(1200)
    print("URL после клика (должен остаться на отчёте):", page.url)
    print("ответы /tg, что увидел браузер:", responses[-3:] if responses else "—")
    print("запросы /tg, что принял сервер:", hits[-3:] if hits else "—")
    ok = bool(hits) and any(s == 204 for s, _ in responses)
    print("РЕЗУЛЬТАТ:", "✅ клик надёжно дошёл до сервера, сервер открыл бы Telegram Desktop" if ok
          else "❌ запрос не дошёл")
    b.close()
httpd.shutdown()
