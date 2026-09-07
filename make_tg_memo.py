# -*- coding: utf-8 -*-
"""Памятка для Telegram: куда подойти на ECOM Expo за розыгрышами/мерчем + навигация по стендам.
Читает tg_results.jsonl, вытаскивает номер стенда из текста, формирует готовый к копипасту текст.
Запуск: python make_tg_memo.py
Выход: tg_memo.txt (вставляй в Telegram)"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

SRC = "tg_results.jsonl"
rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]

# --- извлечение номера стенда ---
# стенды ECOM Expo: буква(ы РУС/ЛАТ) СЛИТНО с цифрами, опц. ".цифры": P6.1, М5.1, B2.30, R2-17
# буква не должна быть приклеена к другой букве (иначе ловим обрывки слов вроде «течениЕ 2»)
CODE = r"(?<![A-Za-zА-Яа-я])[A-ZА-Яa-zа-я]{1,2}\d{1,2}(?:[.\-]\d{1,3})?"
# код после «стенд …» (с возможным названием/№ между) или сразу после «№»
STAND_NEAR = re.compile(r"(?:стенд[еа]?|павильон[а-я]*)[^\n]{0,30}?[№:]?\s*(" + CODE + r")", re.IGNORECASE)
STAND_NUM  = re.compile(r"№\s*(" + CODE + r")", re.IGNORECASE)
STAND_BEFORE = re.compile(r"(" + CODE + r")\s*[—\-–]?\s*наш\s+стенд", re.IGNORECASE)
PAVILION = re.compile(r"(павильон[а-я]*\s*\d+|зал\s*\d+|hall\s*\d+)", re.IGNORECASE)

def find_stand(*texts):
    for t in texts:
        if not t: continue
        m = STAND_NEAR.search(t) or STAND_NUM.search(t) or STAND_BEFORE.search(t)
        if m:
            s = re.sub(r"\s+", "", m.group(1)).upper()
            # отсечь явный мусор вроде «24», «10:00» уже исключены требованием буквы в CODE
            return s
    return ""

def find_pavilion(*texts):
    for t in texts:
        if not t: continue
        m = PAVILION.search(t)
        if m: return m.group(1).strip()
    return ""

def short(t, n=160):
    t = re.sub(r"\s+", " ", (t or "").strip())
    return t if len(t) <= n else t[:n].rstrip() + "…"

expo = [r for r in rows if r.get("invites_ecom_expo") and not r.get("error")]
give = [r for r in expo if r.get("giveaway")]

for r in expo:
    r["_stand"] = find_stand(r.get("expo_quote"), r.get("expo_post_text"),
                             r.get("giveaway_conditions"), r.get("giveaway_post_text"))
    r["_pav"] = find_pavilion(r.get("expo_quote"), r.get("expo_post_text"),
                              r.get("giveaway_conditions"), r.get("giveaway_post_text"))

def line_co(r):
    co = r.get("company") or ("@" + r["username"])
    return co

# сортировка: сначала у кого есть распознанный стенд, потом по компании
def by_stand(items):
    return sorted(items, key=lambda r: (0 if r["_stand"] else 1, r["_stand"], line_co(r).lower()))

L = []
L.append("🎯 ECOM Expo’26 — куда подойти за розыгрышами и мерчем")
L.append("🔴 Идёт 2-й день, 25 июня. Памятка по стендам (по Telegram-каналам участников, обновлено сегодня).")
L.append("")
L.append(f"🎁 РОЗЫГРЫШИ / МЕРЧ / ПРИЗЫ ({len(give)})")
L.append("")
for r in by_stand(give):
    stand = r["_stand"] or r["_pav"] or "стенд уточняется"
    co = line_co(r)
    what = short(r.get("giveaway_what"), 100)
    cond = short(r.get("giveaway_conditions"), 120)
    link = r.get("giveaway_link") or r.get("expo_link") or f"https://t.me/{r['username']}"
    head = f"📍 {stand} — {co}"
    L.append(head)
    if what: L.append(f"   🎁 {what}")
    if cond: L.append(f"   ✅ {cond}")
    L.append(f"   🔗 {link}")
    L.append("")

# навигация: все, кто зовёт на выставку (без обязательного розыгрыша)
no_give = [r for r in expo if not r.get("giveaway")]
L.append("―――――――――――――")
L.append(f"🧭 ОСТАЛЬНЫЕ УЧАСТНИКИ, ЗОВУЩИЕ НА ВЫСТАВКУ ({len(no_give)})")
L.append("")
for r in by_stand(no_give):
    stand = r["_stand"] or r["_pav"] or "стенд уточняется"
    co = line_co(r)
    link = r.get("expo_link") or f"https://t.me/{r['username']}"
    L.append(f"📍 {stand} — {co}  🔗 {link}")
L.append("")
L.append(f"Всего зовут на ECOM Expo: {len(expo)} • из них с розыгрышами: {len(give)}")

txt = "\n".join(L)
open("tg_memo.txt", "w", encoding="utf-8").write(txt)
with_stand = sum(1 for r in give if r["_stand"])
print(f"OK -> tg_memo.txt | приглашений={len(expo)} розыгрышей={len(give)} (стенд распознан у {with_stand} из розыгрышей)")
