# -*- coding: utf-8 -*-
"""Отчёт по tg_results.jsonl: кликабельный HTML + Excel.
Разделы: приглашения на ECOM Expo (со стендами/цитатами) и розыгрыши.
Запуск: python build_tg_report.py
Выход: tg_report.html, tg_report.xlsx"""
import io, sys, json, html, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

SRC = "tg_results.jsonl"
rows = []
for l in open(SRC, encoding="utf-8"):
    l = l.strip()
    if l:
        rows.append(json.loads(l))

TODAY = "2026-06-25"   # 2-й день выставки
expo = [r for r in rows if r.get("invites_ecom_expo")]
give = [r for r in rows if r.get("giveaway")]
errs = [r for r in rows if r.get("error")]
ok = [r for r in rows if not r.get("error")]
fresh_today = [r for r in rows if r.get("last_date") == TODAY and not r.get("error")]

def ch_url(u): return f"https://t.me/{u}"          # веб-ссылка канала (для Excel/копирования)

def chan_web(u): return f"https://t.me/{u}"

def to_tg(u):
    """https://t.me/<канал>/<пост> -> tg://resolve?domain=...&post=... (открывает приложение).
    Схема tg:// зарегистрирована корректно — ссылки в Excel откроют Telegram Desktop."""
    u = str(u or "")
    m = re.match(r"https?://t\.me/([^/?#]+)/(\d+)", u)
    if m: return f"tg://resolve?domain={m.group(1)}&post={m.group(2)}"
    m = re.match(r"https?://t\.me/([^/?#]+)/?$", u)
    if m: return f"tg://resolve?domain={m.group(1)}"
    return u

# В HTML href всегда веб (https://t.me/...), а JS на клике сначала пробует приложение
# (tg://...), и только если оно не перехватило фокус — открывает веб-версию поста.

# ---------- HTML ----------
def esc(s): return html.escape(str(s or ""))

def A(web, label, cls=""):
    """Анкор: href=веб-ссылка, на клике JS пробует приложение Telegram, затем веб."""
    web = str(web or "")
    if not web: return label
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{esc(web)}" onclick="return tgopen(event,this)">{label}</a>'

def card(r):
    u = r["username"]; links = r.get("post_links", [])
    posts = " ".join(A(pl, f"#{i+1}") for i, pl in enumerate(links))
    badges = ""
    if r.get("invites_ecom_expo"): badges += '<span class="b expo">ECOM Expo</span>'
    if r.get("giveaway"): badges += '<span class="b give">Розыгрыш</span>'
    parts = [f'<div class="card">',
             f'<div class="head">{A(chan_web(u), "@"+esc(u), cls="ch")} {badges}'
             f'<span class="co">{esc(r.get("company",""))}</span>'
             + ('<span class="b today">🔴 сегодня</span>' if r.get("last_date") == TODAY else '')
             + f'<span class="date">посл.: {esc(r.get("last_date",""))}</span></div>']
    if r.get("summary"): parts.append(f'<div class="sum">{esc(r["summary"])}</div>')
    if r.get("giveaway_what"):
        gl = r.get("giveaway_link", "")
        cond = " — " + esc(r["giveaway_conditions"]) if r.get("giveaway_conditions") else ""
        body = f'🎁 <b>{esc(r["giveaway_what"])}</b>{cond}'
        if gl: body += " " + A(gl, "→ открыть пост ↗")
        parts.append(f'<div class="g">{body}</div>')
    # полный текст поста-приглашения (лента)
    et = r.get("expo_post_text") or r.get("expo_quote") or ""
    if et:
        el = r.get("expo_link", "")
        head = A(el, "📣 Открыть приглашение ↗") if el else '📣 Приглашение'
        parts.append(f'<div class="q"><div class="qh">{head}</div>'
                     f'<div class="qtext">{esc(et).replace(chr(10),"<br>")}</div></div>')
    # полный текст поста-розыгрыша, если отличается
    gt = r.get("giveaway_post_text") or ""
    if gt and gt != et:
        gl = r.get("giveaway_link", "")
        head = A(gl, "🎁 Открыть пост розыгрыша ↗") if gl else '🎁 Розыгрыш'
        parts.append(f'<div class="g"><div class="qh">{head}</div>'
                     f'<div class="qtext">{esc(gt).replace(chr(10),"<br>")}</div></div>')
    parts.append(f'<div class="posts">Все посты: {posts}</div></div>')
    return "".join(parts)

# сортировка: сначала с мерчем/призами, внутри группы — свежие выше
def order(items):
    by_date = sorted(items, key=lambda r: r.get("last_date", ""), reverse=True)  # свежие выше
    return sorted(by_date, key=lambda r: 0 if r.get("giveaway") else 1)          # мерч наверх (стабильно)

css = """
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f5f6f8;color:#1a1a1a;margin:0;padding:24px;}
h1{font-size:24px;margin:0 0 4px;} h2{margin:28px 0 12px;font-size:19px;border-left:4px solid #1f7a3d;padding-left:10px;}
.sub{color:#666;margin-bottom:18px;}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.ch{font-weight:700;color:#0088cc;text-decoration:none;font-size:16px;} .ch:hover{text-decoration:underline;}
.co{color:#444;font-size:14px;} .date{color:#999;font-size:12px;margin-left:auto;}
.b{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;color:#fff;}
.b.expo{background:#1f7a3d;} .b.give{background:#d9822b;} .b.today{background:#e02424;}
.live{background:#e02424;color:#fff;border-radius:10px;padding:12px 18px;margin:0 0 16px;font-size:15px;font-weight:600;display:flex;align-items:center;gap:10px;}
.live .dot{width:11px;height:11px;border-radius:50%;background:#fff;box-shadow:0 0 0 0 rgba(255,255,255,.7);animation:pulse 1.4s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.7);}70%{box-shadow:0 0 0 9px rgba(255,255,255,0);}100%{box-shadow:0 0 0 0 rgba(255,255,255,0);}}
.sum{color:#555;font-size:13px;margin:8px 0;}
.q{background:#eef7f0;border-left:3px solid #1f7a3d;padding:8px 10px;border-radius:4px;margin:6px 0;font-size:14px;}
.g{background:#fdf3e7;border-left:3px solid #d9822b;padding:8px 10px;border-radius:4px;margin:6px 0;font-size:14px;}
.qh{font-weight:700;margin-bottom:5px;} .qh a{color:#0088cc;text-decoration:none;} .qh a:hover{text-decoration:underline;}
.qtext{white-space:normal;color:#222;max-height:220px;overflow:auto;line-height:1.45;}
.feed{max-width:760px;}
.posts{font-size:12px;color:#777;margin-top:8px;} .posts a{margin-right:6px;color:#0088cc;}
.stats{display:flex;gap:20px;flex-wrap:wrap;margin:14px 0;}
.stat{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:12px 20px;text-align:center;}
.stat .n{font-size:26px;font-weight:800;color:#1f7a3d;} .stat .l{font-size:12px;color:#777;}
"""
H = [f'<!doctype html><html lang="ru"><head><meta charset="utf-8">',
     '<meta name="viewport" content="width=device-width,initial-scale=1">',
     '<title>ECOM Expo’26 — мониторинг Telegram-каналов участников</title>',
     f'<style>{css}</style></head><body>',
     '<h1>Мониторинг Telegram-каналов участников ECOM Expo’26</h1>',
     '<div class="live"><span class="dot"></span>Выставка идёт — 2-й день, 25 июня 2026. '
     f'Свежих постов за сегодня: {len(fresh_today)}. Карточки с пометкой 🔴 сегодня — обновились прямо сейчас.</div>',
     '<div class="sub">Последние 10 постов каждого канала, классификация через DeepSeek. '
     'Каналы с мерчем/призами — вверху, свежие — выше. Кликай на @канал или ссылки на посты.</div>',
     '<div class="stats">'
     f'<div class="stat"><div class="n">{len(rows)}</div><div class="l">каналов проверено</div></div>'
     f'<div class="stat"><div class="n">{len(expo)}</div><div class="l">зовут на ECOM Expo</div></div>'
     f'<div class="stat"><div class="n">{len(give)}</div><div class="l">с розыгрышами</div></div>'
     f'<div class="stat"><div class="n">{len(fresh_today)}</div><div class="l">постов сегодня</div></div>'
     f'<div class="stat"><div class="n">{len(errs)}</div><div class="l">недоступны</div></div>'
     '</div>']
H.append(f'<h2>📣 Лента приглашений на ECOM Expo ({len(expo)}) — с мерчем/призами вверху</h2>')
H.append('<div class="feed">')
H += [card(r) for r in order(expo)] or ['<p>—</p>']
H.append('</div>')
H.append(f'<h2>🎁 Только розыгрыши / мерч / призы ({len(give)})</h2>')
H.append('<div class="feed">')
H += [card(r) for r in order(give)] or ['<p>—</p>']
H.append('</div>')
H.append("""<script>
function toTg(u){
  var m=u.match(/^https?:\\/\\/t\\.me\\/([^\\/?#]+)\\/(\\d+)/);
  if(m) return 'tg://resolve?domain='+m[1]+'&post='+m[2];
  m=u.match(/^https?:\\/\\/t\\.me\\/([^\\/?#]+)/);
  if(m) return 'tg://resolve?domain='+m[1];
  return u;
}
function tgopen(e,a){
  if(e.ctrlKey||e.metaKey||e.shiftKey||e.button===1) return true; // ctrl/средняя — веб в новой вкладке
  e.preventDefault();
  var web=a.href;
  // НАДЁЖНЫЙ путь (отчёт открыт через serve_report.py на http://localhost):
  // локальный сервер сам зовёт системный обработчик tg:// -> Telegram Desktop.
  // Браузер не блокирует (обычный http-запрос) и со страницы не уходит.
  if(location.protocol==='http:'||location.protocol==='https:'){
    fetch('/tg?u='+encodeURIComponent(web)).catch(function(){window.open(web,'_blank');});
    return false;
  }
  // запасной путь (открыт как file://): пробуем приложение, через 1.5 c — веб.
  var tg=toTg(web), left=false;
  function mark(){left=true;}
  window.addEventListener('blur',mark,{once:true});
  document.addEventListener('visibilitychange',mark,{once:true});
  setTimeout(function(){ window.removeEventListener('blur',mark); if(!left) window.open(web,'_blank'); },1500);
  try{ window.location.href=tg; }catch(_){ window.open(web,'_blank'); }
  return false;
}
</script>""")
H.append('</body></html>')
open("tg_report.html", "w", encoding="utf-8").write("\n".join(H))

# ---------- Excel ----------
wb = Workbook()
hdr_fill = PatternFill("solid", fgColor="1F7A3D"); hdr_font = Font(color="FFFFFF", bold=True)
LINKCOLS = {"channel", "expo_link", "giveaway_link"}
def sheet(name, data, cols):
    ws = wb.create_sheet(name)
    ws.append([c[0] for c in cols])
    for cell in ws[1]: cell.fill = hdr_fill; cell.font = hdr_font; cell.alignment = Alignment(vertical="center")
    for r in data:
        ws.append([ch_url(r["username"]) if c[1] == "channel" else r.get(c[1], "") for c in cols])
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = c[2]
        # текстовые колонки с постами — перенос строк
        if c[1] in ("expo_post_text", "giveaway_post_text", "giveaway_conditions", "expo_quote"):
            for row in range(2, ws.max_row+1):
                ws.cell(row=row, column=i).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    # кликабельные ссылки
    for row in range(2, ws.max_row+1):
        for i, c in enumerate(cols, 1):
            if c[1] in LINKCOLS:
                cell = ws.cell(row=row, column=i)
                if cell.value:
                    # переход открывает приложение (tg://), текст в ячейке оставляем читаемым (https://t.me/...)
                    cell.hyperlink = to_tg(cell.value); cell.font = Font(color="0088CC", underline="single")
    return ws

wb.remove(wb.active)
# В таблице приглашений: мерч/призы — вверху, есть полный текст постов
EXPO_COLS = [("Мерч/приз","give_mark",10),("Канал","channel",30),("Компания","company",22),
             ("Текст приглашения","expo_post_text",70),("Пост-приглашение","expo_link",28),
             ("Что разыгрывают","giveaway_what",26),("Текст поста розыгрыша","giveaway_post_text",60),
             ("Пост розыгрыша","giveaway_link",28),("Посл. пост","last_date",12)]
GIVE_COLS = [("Канал","channel",30),("Компания","company",22),("Что разыгрывают (мерч/призы)","giveaway_what",30),
             ("Условия","giveaway_conditions",40),("Текст поста","giveaway_post_text",70),
             ("Пост розыгрыша","giveaway_link",28),("Зовут на Expo","invites_ecom_expo",13),("Посл. пост","last_date",12)]
ALL_COLS = [("Канал","channel",30),("Компания","company",22),("О канале","summary",55),
            ("Expo","invites_ecom_expo",8),("Розыгрыш","giveaway",10),("Посл. пост","last_date",12),("Ошибка","error",30)]
for r in rows:
    r["give_mark"] = "🎁 ДА" if r.get("giveaway") else ""
sheet("ECOM Expo", order(expo), EXPO_COLS)
sheet("Розыгрыши", order(give), GIVE_COLS)
sheet("Все каналы", rows, ALL_COLS)
import os as _os
_out = "tg_report.xlsx"
try:
    wb.save(_out)
except PermissionError:
    _out = "tg_report_new.xlsx"; wb.save(_out)
    print("⚠ tg_report.xlsx был открыт — сохранил в", _out)
print(f"OK | каналов={len(rows)} expo={len(expo)} give={len(give)} errors={len(errs)}")
print(f"-> tg_report.html, {_out}")
