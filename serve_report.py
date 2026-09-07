# -*- coding: utf-8 -*-
"""Надёжный просмотр tg_report.html с открытием постов в Telegram DESKTOP.

Почему так: браузер из страницы блокирует/глушит переход по схеме tg://
(особенно из file://). Здесь страница открывается через http://localhost, а клик
по ссылке шлёт запрос на этот локальный сервер — и сервер сам вызывает системный
обработчик tg:// (то же, что `start tg://...`, что на этой машине работает),
открывая Telegram Desktop. Браузер при этом не уходит со страницы.

Запуск: python serve_report.py   (откроет отчёт в браузере по адресу localhost)
Остановить: Ctrl+C."""
import os, io, sys, re, webbrowser, urllib.parse, subprocess
import http.server, socketserver
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
REPORT = "tg_report.html"


def find_telegram():
    """Путь к Telegram.exe. Схема tg:// в реестре сломана ("" -- "%1"),
    поэтому открываем приложение напрямую: Telegram.exe -- "tg://...".
    Берём запущенный экземпляр (AppData\\Roaming), затем прочие места и портативную копию."""
    cands = []
    appdata = os.environ.get("APPDATA", ""); local = os.environ.get("LOCALAPPDATA", "")
    cands += [os.path.join(appdata, "Telegram Desktop", "Telegram.exe"),
              os.path.join(local, "Programs", "Telegram Desktop", "Telegram.exe"),
              os.path.join(local, "Telegram Desktop", "Telegram.exe")]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\tonsite\shell\open\command") as k:
            v = winreg.QueryValueEx(k, "")[0]
            m = re.search(r'([A-Za-z]:\\[^"]*?Telegram\.exe)', v)
            if m: cands.append(m.group(1).strip())
    except Exception:
        pass
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


TELEGRAM = find_telegram()


def to_tg(u):
    """https://t.me/<канал>/<пост> -> tg://resolve?domain=<канал>&post=<пост>."""
    u = str(u or "")
    m = re.match(r"https?://t\.me/([^/?#]+)/(\d+)", u)
    if m:
        return f"tg://resolve?domain={m.group(1)}&post={m.group(2)}"
    m = re.match(r"https?://t\.me/([^/?#]+)/?$", u)
    if m:
        return f"tg://resolve?domain={m.group(1)}"
    if u.startswith("tg://"):
        return u
    return ""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # тихий лог
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/tg":
            web = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
            tg = to_tg(web)
            ok = False
            if tg:
                try:
                    if os.environ.get("TG_TEST") == "1":
                        ok = True; print("[TEST] получил, НЕ запускаю приложение:", tg)
                    elif TELEGRAM:
                        subprocess.Popen([TELEGRAM, "--", tg])  # прямой запуск приложения
                        ok = True
                        print("→ Telegram Desktop:", tg)
                    else:
                        import ctypes
                        ctypes.windll.shell32.ShellExecuteW(None, "open", tg, None, None, 1)
                        ok = True
                        print("→ через ОС (Telegram.exe не найден):", tg)
                except Exception as e:
                    print("✗ не смог открыть:", tg, "|", e)
            self.send_response(204 if ok else 502)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        return super().do_GET()


def main():
    if not os.path.exists(REPORT):
        print("Нет", REPORT, "— сначала: python build_tg_report.py"); return
    port = 8731
    for p in range(8731, 8760):
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", p), Handler); port = p; break
        except OSError:
            continue
    else:
        print("Не нашёл свободный порт 8731-8759"); return
    url = f"http://127.0.0.1:{port}/{REPORT}"
    print(f"Отчёт: {url}")
    print("Telegram.exe:", TELEGRAM or "НЕ НАЙДЕН (буду пробовать через ОС)")
    print("Клик по ссылке открывает пост в Telegram Desktop. Ctrl+C — выход.")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
