# -*- coding: utf-8 -*-
"""
Собирает Chrome-расширение (MV3) для полуавтоматической вставки статьи
в редактор vc.ru. Картинки из vc_article/*.png зашиваются в расширение
как data:URL, текст — как структура блоков.

Выход: vc_article/vc_extension/  (manifest.json, content.js, article_data.js, README)
Установка: chrome://extensions → «Режим разработчика» → «Загрузить распакованное».
"""
import base64, json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).parent
ART = ROOT / "vc_article"
EXT = ART / "vc_extension"
EXT.mkdir(parents=True, exist_ok=True)

# ---- структура статьи: блоки в порядке вставки ----
# type: h2|h3|text|list|quote|image
BLOCKS = [
    {"type": "image", "file": "00_cover.png"},   # обложка статьи (первая картинка = превью в ленте vc.ru)
    {"type": "text", "text": "ECOM Expo — крупнейшая в России выставка технологий для онлайн-торговли: сервисы для маркетплейсов и собственных интернет-магазинов, логистика и фулфилмент, платежи, маркетинг, CRM и аналитика. Аудитория — селлеры, интернет-магазины, ритейл и B2C-компании, бренды."},
    {"type": "h2", "text": "Когда, где и как попасть"},
    {"type": "list", "items": [
        "Даты: 24–25 июня 2026, с 10:00 до 18:00.",
        "Место: Москва, ВЦ «Тимирязев Центр», Верхняя аллея, 6с1 (павильоны «Вавилов» и «Немчинов»).",
        "Метро: Петровско-Разумовская, выход №5 — около 5 минут пешком. От выхода прямо до первого перекрёстка, затем налево и вдоль улицы; вход у флагов ECOM Expo.",
        "Вход бесплатный по обязательной регистрации (для селлеров, сотрудников интернет-магазинов, ритейла и B2C-компаний).",
        "Парковка: своей у ВЦ нет. Вокруг есть городские парковки — встречаются бесплатные места, платные стоят примерно от 40 ₽/час. Удобнее приезжать на метро или к открытию в 10:00.",
    ]},
    {"type": "text", "text": "А теперь к данным. Я выгрузил всех участников выставки ECOM Expo с сайта организаторов за все доступные годы (2015–2026), свёл их в единую базу, определил тематику каждой компании и собрал контакты. Получилось 1222 уникальные компании и несколько неожиданных закономерностей: кто-то держит стенд десятилетие подряд, а целые поколения сервисов исчезают за пару лет."},

    {"type": "h2", "text": "Сколько компаний участвует и как это менялось"},
    {"type": "image", "file": "01_participants_by_year.png"},
    {"type": "text", "text": "Число экспонентов выросло со ~170 в середине 2010-х до 200+ в современных выпусках. По 2018–2019 в открытом доступе списков нет — поэтому на графике провал, это пропуск данных, а не отсутствие выставки."},

    {"type": "h2", "text": "Кто приезжает каждый год — «старожилы»"},
    {"type": "image", "file": "03_top_companies.png"},
    {"type": "text", "text": "Абсолютные рекордсмены по числу участий — MANGO OFFICE, Sendsay и МойСклад (по 10 разных лет). Следом плотная группа с 9 участиями: СДЭК, LOGSIS, Retail Rocket, retailCRM, ROBOKASSA, InSales, Телфин, Mindbox. Это, по сути, костяк рынка инструментов для интернет-торговли."},
    {"type": "image", "file": "07_top25_table.png"},

    {"type": "h2", "text": "Приток новых игроков"},
    {"type": "image", "file": "02_new_companies_by_year.png"},
    {"type": "text", "text": "Каждый год выставка обновляется — видно, сколько компаний пришло впервые. Большая доля «одноразовых» участников говорит о высокой текучке сервисного рынка."},

    {"type": "h2", "text": "Как устроен рынок по тематикам"},
    {"type": "image", "file": "04_topics.png"},
    {"type": "text", "text": "Я классифицировал все 1222 компании по роду деятельности. Крупнейшие сегменты — доставка и логистика (262), маркетинг/реклама/SEO (203) и разработка сайтов и IT-интеграции (172). Дальше — платежи, маркетплейс-сервисы, CRM и аналитика."},

    {"type": "h2", "text": "Telegram стал стандартом, MAX только начинает"},
    {"type": "image", "file": "05_messengers_by_year.png"},
    {"type": "text", "text": "Среди участников разных лет доля тех, у кого сегодня на сайте есть Telegram-канал, выросла с ~25% до ~60%. Новый мессенджер MAX уже засветился у части компаний — небольшая, но заметная доля."},

    {"type": "h2", "text": "Сколько раз компании возвращаются"},
    {"type": "image", "file": "06_tenure.png"},
    {"type": "text", "text": "Большинство компаний участвовали 1–2 раза, и лишь десятки — почти каждый год. Отдельная категория — «возвращенцы» (133 компании), которые уходили и появлялись снова через несколько лет."},

    {"type": "h2", "text": "Как это собрано"},
    {"type": "list", "items": [
        "Участники выгружены со страниц expo.oborot.ru/archive/<год>/ и …/plan.html (старые годы).",
        "Контакты (email, телефон, Telegram, MAX, соцсети) собраны обходом сайтов компаний.",
        "Описание деятельности и тематика — автоматически по содержимому главной страницы.",
    ]},
    {"type": "quote", "text": "Ядро рынка e-commerce-сервисов в России стабильно: десяток компаний держит стенды почти десятилетие, но вокруг них постоянно сменяются поколения новых игроков."},
    {"type": "text", "text": "Если интересно — могу выложить полную таблицу участников по годам и разбивку по тематикам. Напишите в комментариях, какие ещё срезы посчитать."},
]

TITLE = "11 лет ECOM Expo: кто приезжает каждый год, кого вымывает и куда ушёл рынок e-commerce-сервисов"


def img_data_url(fn):
    b = (ART / fn).read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


# встроить картинки
blocks_out = []
for b in BLOCKS:
    if b["type"] == "image":
        blocks_out.append({"type": "image", "file": b["file"], "dataUrl": img_data_url(b["file"])})
    else:
        blocks_out.append(b)

data_js = "window.VC_ARTICLE = " + json.dumps(
    {"title": TITLE, "blocks": blocks_out}, ensure_ascii=False) + ";\n"
(EXT / "article_data.js").write_text(data_js, encoding="utf-8")

# ---- manifest ----
manifest = {
    "manifest_version": 3,
    "name": "ECOM Expo → vc.ru вставка статьи",
    "version": "1.9",
    "description": "Вставка статьи (текст + графики) в редактор Editor.js на vc.ru через нативный paste, с самодиагностикой.",
    "content_scripts": [{
        "matches": ["https://vc.ru/*", "https://*.vc.ru/*"],
        "js": ["article_data.js", "content.js"],
        "run_at": "document_idle"
    }]
}
(EXT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# ---- content.js ----
content_js = r"""
// Плавающая панель + вставка через нативный paste редактора Osnova (vc.ru)
// + отладочный слой: трассировка шагов, перехват ошибок, снимки DOM, скачивание логов.
(function () {
  const A = window.VC_ARTICLE;
  if (!A) return;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // ================= ОТЛАДКА =================
  const DBG = { started: new Date().toISOString(), log: [], errors: [], steps: [] };
  function nowISO(){ return new Date().toISOString(); }
  function log(level, msg, data) {
    const rec = { t: nowISO(), level, msg };
    if (data !== undefined) { try { rec.data = JSON.parse(JSON.stringify(data)); } catch(e){ rec.data = String(data); } }
    DBG.log.push(rec);
    const c = level === 'error' ? 'color:#e74c3c' : level === 'warn' ? 'color:#e0a020' : 'color:#27ae60';
    console.log('%c[vc-ext] ' + level.toUpperCase() + ': ' + msg, c, data !== undefined ? data : '');
  }
  // перехват ошибок страницы
  window.addEventListener('error', (e) => {
    DBG.errors.push({ t: nowISO(), kind: 'window.error', message: e.message,
      source: e.filename, line: e.lineno, col: e.colno, stack: e.error && e.error.stack });
    log('error', 'window.error: ' + e.message);
  });
  window.addEventListener('unhandledrejection', (e) => {
    DBG.errors.push({ t: nowISO(), kind: 'unhandledrejection', reason: String(e.reason),
      stack: e.reason && e.reason.stack });
    log('error', 'unhandledrejection: ' + String(e.reason));
  });

  function cssPath(el) {
    const parts = [];
    let n = el, depth = 0;
    while (n && n.nodeType === 1 && depth < 7) {
      let s = n.tagName.toLowerCase();
      if (n.id) s += '#' + n.id;
      if (n.className && typeof n.className === 'string')
        s += '.' + n.className.trim().split(/\s+/).slice(0, 3).join('.');
      parts.unshift(s); n = n.parentElement; depth++;
    }
    return parts.join(' > ');
  }
  function attrsOf(el) {
    const o = {};
    for (const a of el.attributes || []) {
      let v = a.value || '';
      if (v.startsWith('data:')) v = 'data:[' + v.length + ' chars]';
      if (v.length > 120) v = v.slice(0, 120) + '…[' + v.length + ']';
      o[a.name] = v;
    }
    return o;
  }
  function describe(el) {
    const r = el.getBoundingClientRect();
    return {
      path: cssPath(el), tag: el.tagName.toLowerCase(),
      id: el.id || null, class: (typeof el.className === 'string' ? el.className : null),
      attrs: attrsOf(el), role: el.getAttribute && el.getAttribute('role'),
      contentEditable: el.getAttribute && el.getAttribute('contenteditable'),
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      visible: el.offsetParent !== null, childElementCount: el.childElementCount,
      textLen: (el.innerText || '').length, textHead: (el.innerText || '').slice(0, 80)
    };
  }
  // обрезанный снимок дерева (для понимания структуры блоков)
  function snapshotTree(el, depth, maxDepth, maxChildren) {
    if (!el || el.nodeType !== 1 || depth > maxDepth) return null;
    const r = el.getBoundingClientRect();
    const node = {
      tag: el.tagName.toLowerCase(),
      id: el.id || undefined,
      class: (typeof el.className === 'string' && el.className) ? el.className : undefined,
      data: Object.fromEntries(Object.entries(attrsOf(el)).filter(([k]) => k.startsWith('data-') || k === 'role' || k === 'contenteditable')),
      rect: { w: Math.round(r.width), h: Math.round(r.height) },
      textLen: (el.innerText || '').length
    };
    const kids = [...el.children].slice(0, maxChildren);
    if (kids.length) node.children = kids.map(k => snapshotTree(k, depth + 1, maxDepth, maxChildren)).filter(Boolean);
    if (el.children.length > maxChildren) node.truncatedChildren = el.children.length - maxChildren;
    return node;
  }

  function download(filename, content, mime) {
    try {
      const blob = new Blob([content], { type: mime || 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      log('info', 'Скачан файл: ' + filename);
    } catch (e) { log('error', 'Не смог скачать ' + filename + ': ' + e.message); }
  }

  function collectEditorCandidates() {
    const sel = '[contenteditable="true"], [contenteditable=""], [role="textbox"]';
    return [...document.querySelectorAll(sel)].map(describe);
  }

  function findCodex() {
    return document.querySelector('.codex-editor') || document.querySelector('.ce-redactor') || null;
  }
  function ceBlocksInfo() {
    const codex = findCodex();
    if (!codex) return [];
    return [...codex.querySelectorAll('.ce-block')].map(b => {
      const ed = b.querySelector('[contenteditable]');
      const tool = b.querySelector('.ce-block__content > *');
      return {
        blockClass: b.className,
        dataId: b.getAttribute('data-id'),
        toolWrapperClass: tool ? tool.className : null,
        editableClass: ed ? ed.className : null,
        placeholder: ed ? ed.getAttribute('data-placeholder') : null,
        contenteditable: ed ? ed.getAttribute('contenteditable') : null,
        textHead: (b.innerText || '').slice(0, 50)
      };
    });
  }
  function diagnostics(reason) {
    const ed = findEditor();
    const codex = findCodex() || document.body;
    const report = {
      reason: reason || 'manual', generatedAt: nowISO(),
      url: location.href, userAgent: navigator.userAgent,
      viewport: { w: innerWidth, h: innerHeight },
      editorType: findCodex() ? 'editor.js (codex)' : 'unknown',
      titleField: (function(){ const t = findTitle(); return t ? describe(t) : null; })(),
      bodyEditables: bodyEditables().map(describe),
      editorChosen: ed ? describe(ed) : null,
      editorCandidates: collectEditorCandidates(),
      ceBlocks: ceBlocksInfo(),
      codexRoot: codex !== document.body ? describe(codex) : null,
      domTree: snapshotTree(codex, 0, 8, 30),
      run: { steps: DBG.steps, log: DBG.log, errors: DBG.errors }
    };
    const stamp = nowISO().replace(/[:.]/g, '-');
    download('vc-diagnostics-' + stamp + '.json', JSON.stringify(report, null, 2), 'application/json');
    let html = codex.outerHTML.replace(/(src|href)="data:[^"]*"/g, '$1="data:[stripped]"');
    if (html.length > 900000) html = html.slice(0, 900000) + '\n<!-- truncated -->';
    download('vc-editor-snapshot-' + stamp + '.html', html, 'text/html');
    return report;
  }

  function isTitle(el) {
    return el.getAttribute('data-placeholder') === 'Заголовок' ||
           el.classList.contains('editor-tool-input--text-lg');
  }
  function findTitle() {
    const c = [...document.querySelectorAll('[contenteditable="true"]')].filter(isTitle);
    return c[0] || null;
  }
  function isCaption(el) {
    return el.getAttribute('data-placeholder') === 'Описание';  // подпись под картинкой
  }
  function bodyEditables() {
    const red = document.querySelector('.ce-redactor') || findCodex() || document.body;
    return [...red.querySelectorAll('[contenteditable="true"]')]
      .filter(e => e.offsetParent !== null && !isTitle(e) && !isCaption(e));
  }
  function lastTextPara() {
    const red = document.querySelector('.ce-redactor') || findCodex() || document.body;
    const eds = [...red.querySelectorAll('.editor-text-tool[contenteditable="true"]')]
      .filter(e => e.offsetParent !== null);
    return eds.length ? eds[eds.length - 1] : null;
  }
  function setCaretEnd(el) {
    try { const r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); } catch (e) {}
  }
  // настоящий клик мышью по блоку: Editor.js так переключает «текущий блок»,
  // иначе вставка картинки уходит в конец (внутренний currentBlockIndex не меняется от .focus()).
  function clickFocus(el) {
    try { el.scrollIntoView({ block: 'center' }); } catch (e) {}
    const r = el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, view: window,
      clientX: Math.round(r.left + Math.min(20, r.width / 2)), clientY: Math.round(r.top + r.height / 2) };
    for (const t of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
      try { el.dispatchEvent(new MouseEvent(t, opts)); } catch (e) {}
    }
    el.focus();
    setCaretEnd(el);
  }
  // тело статьи (Editor.js) — contenteditable, не являющийся заголовком.
  // Если его ещё нет, создаём: фокус заголовка + Enter, либо клик по редактору.
  async function ensureBody() {
    let b = bodyEditables();
    if (b.length) return b[b.length - 1];
    const t = findTitle();
    if (t) { t.focus(); setCaretEnd(t); pressEnter(t); await sleep(350); }
    b = bodyEditables();
    if (b.length) return b[b.length - 1];
    const red = document.querySelector('.ce-redactor');
    if (red) { red.click(); await sleep(350); }
    b = bodyEditables();
    return b.length ? b[b.length - 1] : null;
  }
  // для диагностики: «выбранный редактор» = тело, иначе заголовок
  function findEditor() {
    const b = bodyEditables();
    if (b.length) return b[b.length - 1];
    return findTitle();
  }
  function editorBlockCount() {
    const red = document.querySelector('.ce-redactor') || findCodex();
    return red ? red.querySelectorAll('.ce-block').length : -1;
  }

  function escapeHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

  function blockHtml(b) {
    switch (b.type) {
      case 'h2': return '<h2>' + escapeHtml(b.text) + '</h2>';
      case 'h3': return '<h3>' + escapeHtml(b.text) + '</h3>';
      case 'quote': return '<blockquote>' + escapeHtml(b.text) + '</blockquote>';
      case 'list': return '<ul>' + b.items.map(i => '<li>' + escapeHtml(i) + '</li>').join('') + '</ul>';
      default: return '<p>' + escapeHtml(b.text) + '</p>';
    }
  }

  async function pasteHTML(el, html, text) {
    el.focus();
    const dt = new DataTransfer();
    dt.setData('text/html', html);
    dt.setData('text/plain', text || html.replace(/<[^>]+>/g, ''));
    const ev = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
    const dispatched = el.dispatchEvent(ev);
    log('info', 'pasteHTML', { htmlLen: html.length, defaultPrevented: ev.defaultPrevented, dispatched });
    await sleep(450);
  }

  async function pasteImage(el, dataUrl) {
    el.focus();
    const blob = await (await fetch(dataUrl)).blob();
    const file = new File([blob], 'chart.png', { type: 'image/png' });
    const dt = new DataTransfer();
    dt.items.add(file);
    const ev = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
    const dispatched = el.dispatchEvent(ev);
    log('info', 'pasteImage', { bytes: blob.size, defaultPrevented: ev.defaultPrevented, dispatched, itemsInDT: dt.items.length });
    await sleep(2200); // время на загрузку картинки
  }

  function pressEnter(el) {
    el.focus();
    for (const type of ['keydown', 'keyup']) {
      el.dispatchEvent(new KeyboardEvent(type, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
    }
  }

  function focusBodyEnd() {
    const b = bodyEditables();
    const el = b.length ? b[b.length - 1] : null;
    if (el) { el.focus(); setCaretEnd(el); }
    return el;
  }

  async function fillTitle() {
    const t = findTitle();
    if (!t) { log('warn', 'Поле заголовка не найдено'); return false; }
    t.focus(); setCaretEnd(t);
    await pasteHTML(t, escapeHtml(A.title), A.title);
    log('info', 'Заголовок вставлен');
    return true;
  }

  async function insertAll(status) {
    DBG.steps = []; DBG.log = []; DBG.errors = [];
    log('info', 'Старт вставки. Блоков: ' + A.blocks.length);
    if (!findCodex()) {
      log('error', 'Editor.js (.codex-editor) не найден');
      status('❌ Редактор не найден. Жму диагностику…'); diagnostics('codex-not-found'); return;
    }
    await fillTitle();
    let body = await ensureBody();
    if (!body) {
      log('error', 'Не удалось получить тело статьи');
      status('❌ Тело редактора не найдено. Кликни в область текста и повтори. Жму диагностику…');
      diagnostics('body-not-found'); return;
    }
    log('info', 'Тело статьи готово', describe(body));

    // === 1) ВЕСЬ ТЕКСТ одним paste; картинки — строками-маркерами на их местах ===
    status('Вставляю текст…');
    let html = '', plain = '', ii = 0; const markers = [];
    for (const b of A.blocks) {
      if (b.type === 'image') {
        ii++; const m = 'IMGSLOT' + ii;   // маркер-параграф (простой текст: выживает + принимает картинку)
        markers.push({ marker: m, dataUrl: b.dataUrl, file: b.file });
        html += '<p>' + m + '</p>'; plain += m + '\n\n';
      } else {
        html += blockHtml(b);
        plain += (b.text || (b.items ? b.items.join('\n') : '')) + '\n\n';
      }
    }
    {
      const target = focusBodyEnd() || body;
      const before = editorBlockCount();
      try {
        await pasteHTML(target, html, plain);
        await sleep(1000);
        const after = editorBlockCount();
        DBG.steps.push({ phase: 'text', blocksBefore: before, blocksAfter: after, changed: after > before, ok: true });
        log('info', 'Текст+маркеры вставлены: блоков ' + before + ' → ' + after);
      } catch (e) {
        DBG.errors.push({ t: nowISO(), kind: 'text', message: e.message, stack: e.stack });
        log('error', 'Текст не вставился: ' + e.message);
      }
    }

    // === 2) КАРТИНКИ на места маркеров (находим блок [[IMG-k]], очищаем, вставляем) ===
    function findBlockByText(txt) {
      const red = document.querySelector('.ce-redactor') || findCodex();
      if (!red) return null;
      const blocks = [...red.querySelectorAll('.ce-block')];
      return blocks.find(b => ((b.innerText || '').replace(/​/g, '').trim()) === txt)
          || blocks.find(b => (b.innerText || '').includes(txt)) || null;
    }
    const imgs = markers;
    for (let k = 0; k < markers.length; k++) {
      const m = markers[k];
      status('Картинка ' + (k + 1) + '/' + markers.length + '…');
      const blk = findBlockByText(m.marker);
      let ed = blk ? blk.querySelector('[contenteditable="true"]') : null;
      let target;
      if (ed) {
        clickFocus(ed);   // переключаем «текущий блок» Editor.js на маркер
        try { document.execCommand('selectAll', false, null); document.execCommand('delete', false, null); } catch (e) {}
        setCaretEnd(ed); target = ed;
      } else { target = lastTextPara() || focusBodyEnd() || body; if (target) clickFocus(target); }  // никогда не подпись «Описание»
      const step = { phase: 'image', k, file: m.file, markerFound: !!blk,
        targetPh: target && target.getAttribute && target.getAttribute('data-placeholder'),
        targetClass: target && target.className };
      const before = editorBlockCount();
      try {
        await pasteImage(target, m.dataUrl);
        await sleep(2600);
        const after = editorBlockCount();
        step.blocksBefore = before; step.blocksAfter = after; step.changed = after > before; step.ok = true;
        if (step.changed) log('info', 'Картинка ' + (k + 1) + ' вставлена (' + before + ' → ' + after + '), маркер найден: ' + !!blk);
        else log('warn', 'Картинка ' + (k + 1) + ' не дала нового блока', step);
      } catch (e) {
        step.ok = false; step.error = e.message; step.stack = e.stack;
        DBG.errors.push({ t: nowISO(), kind: 'image', k, message: e.message, stack: e.stack });
        log('error', 'Ошибка картинки ' + (k + 1) + ': ' + e.message);
      }
      DBG.steps.push(step);
    }

    DBG.finished = nowISO();
    const textOk = DBG.steps.some(s => s.phase === 'text' && s.changed);
    const imagesOk = DBG.steps.filter(s => s.phase === 'image' && s.changed).length;
    DBG.summary = { textOk, images: imgs.length, imagesOk, errors: DBG.errors.length };
    log('info', 'Готово', DBG.summary);
    diagnostics('after-run');
    status((textOk && imagesOk === imgs.length ? '✅' : '⚠️') +
      ' Текст: ' + (textOk ? 'ок' : 'НЕ ок') + ', картинок: ' + imagesOk + '/' + imgs.length +
      '. Скачан отчёт — пришли мне.');
  }

  async function copyText(s) {
    const html = A.blocks.map(blockHtml).join('');
    const blob = new Blob([html], { type: 'text/html' });
    const txt = new Blob([A.blocks.map(b => b.text || (b.items ? b.items.join('\n') : '')).join('\n\n')], { type: 'text/plain' });
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': blob, 'text/plain': txt })]);
      s('📋 Текст статьи скопирован — кликни в редактор и Ctrl+V.');
    } catch (e) { s('Не вышло скопировать: ' + e.message); }
  }

  async function copyImage(idx, s) {
    const imgs = A.blocks.filter(b => b.type === 'image');
    const b = imgs[idx];
    const blob = await (await fetch(b.dataUrl)).blob();
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      s('🖼 Картинка «' + b.file + '» в буфере — Ctrl+V в редактор.');
    } catch (e) { s('Не вышло: ' + e.message); }
  }

  // ---- UI ----
  const panel = document.createElement('div');
  panel.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;width:300px;background:#11151b;color:#e6ebf1;border:1px solid #2b3340;border-radius:12px;padding:12px;font:13px/1.4 -apple-system,Segoe UI,Roboto,Arial;box-shadow:0 8px 30px rgba(0,0,0,.4)';
  panel.innerHTML =
    '<div style="font-weight:700;margin-bottom:8px">ECOM Expo → vc.ru</div>' +
    '<button id="vc-all" style="width:100%;padding:9px;margin-bottom:6px;border:0;border-radius:8px;background:#27ae60;color:#fff;font-weight:700;cursor:pointer">▶ Вставить статью целиком</button>' +
    '<button id="vc-diag" style="width:100%;padding:7px;margin-bottom:6px;border:1px solid #2b7aa0;border-radius:8px;background:#13202b;color:#bfe6ff;cursor:pointer">🩺 Снять диагностику (скачать)</button>' +
    '<button id="vc-diag2" style="width:100%;padding:7px;margin-bottom:6px;border:1px solid #7d4fb0;border-radius:8px;background:#1c1330;color:#e7d4ff;cursor:pointer">🔬 Глубокая диагностика (создаст блок тела)</button>' +
    '<button id="vc-txt" style="width:100%;padding:7px;margin-bottom:6px;border:1px solid #2f3a48;border-radius:8px;background:#1a1f27;color:#dbe4ee;cursor:pointer">📋 Скопировать только текст</button>' +
    '<div id="vc-imgs" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px"></div>' +
    '<div id="vc-status" style="font-size:12px;color:#8b97a7;min-height:32px"></div>' +
    '<div style="font-size:11px;color:#5f6b7a">Заголовок вставь вручную в поле «Заголовок»:</div>' +
    '<button id="vc-title" style="width:100%;padding:6px;margin-top:4px;border:1px solid #2f3a48;border-radius:8px;background:#1a1f27;color:#dbe4ee;cursor:pointer">📋 Скопировать заголовок</button>';
  document.body.appendChild(panel);
  const status = (m) => { panel.querySelector('#vc-status').textContent = m; };

  panel.querySelector('#vc-all').onclick = () => insertAll(status).catch(e => {
    log('error', 'insertAll упал: ' + e.message); DBG.errors.push({ t: nowISO(), kind: 'insertAll', message: e.message, stack: e.stack });
    diagnostics('insertAll-crash'); status('❌ Сбой — скачан отчёт диагностики, пришли его мне.');
  });
  panel.querySelector('#vc-diag').onclick = () => { diagnostics('manual'); status('🩺 Диагностика скачана (JSON + HTML). Пришли файлы мне.'); };
  panel.querySelector('#vc-diag2').onclick = async () => {
    status('Создаю блок тела и снимаю структуру…');
    try { await ensureBody(); await sleep(300); } catch (e) { log('error', 'ensureBody: ' + e.message); }
    diagnostics('deep'); status('🔬 Глубокая диагностика скачана. Пришли файлы мне.');
  };
  panel.querySelector('#vc-txt').onclick = () => copyText(status);
  panel.querySelector('#vc-title').onclick = async () => {
    try { await navigator.clipboard.writeText(A.title); status('📋 Заголовок скопирован.'); }
    catch (e) { status('Ошибка: ' + e.message); }
  };
  const imgsWrap = panel.querySelector('#vc-imgs');
  A.blocks.filter(b => b.type === 'image').forEach((b, i) => {
    const btn = document.createElement('button');
    btn.textContent = '🖼' + (i + 1);
    btn.title = b.file;
    btn.style.cssText = 'padding:5px 8px;border:1px solid #2f3a48;border-radius:7px;background:#1a1f27;color:#bfe6ff;cursor:pointer';
    btn.onclick = () => copyImage(i, status);
    imgsWrap.appendChild(btn);
  });
})();
"""
(EXT / "content.js").write_text(content_js, encoding="utf-8")

# ---- README ----
readme = """# Расширение «ECOM Expo → vc.ru»

Полуавтоматическая вставка статьи (текст + графики) в редактор vc.ru.

## Установка
1. Открой `chrome://extensions`
2. Включи «Режим разработчика» (справа сверху)
3. «Загрузить распакованное» → выбери эту папку `vc_extension`

## Использование
1. На vc.ru нажми «Написать» → откроется окно создания статьи.
2. **Кликни мышью в поле текста** статьи (важно — поставить курсор).
3. Справа снизу появится панель. Жми **«▶ Вставить статью целиком»**.
   Не трогай мышь/клавиатуру, пока идёт вставка (~30–40 сек из-за загрузки картинок).
4. Заголовок: кнопка «📋 Скопировать заголовок» → клик в поле «Заголовок» → Ctrl+V.

## Если что-то не вставилось
Редактор vc.ru со временем меняется — на этот случай есть ручные кнопки-фолбэки:
- «📋 Скопировать только текст» → клик в редактор → Ctrl+V (вставит весь текст блоками).
- «🖼1…🖼7» → копирует нужную картинку в буфер → Ctrl+V в редактор в нужном месте.

Так в самом плохом случае остаётся: 1 раз вставить текст + 7 раз Ctrl+V для картинок.

## Самодиагностика (чтобы автор мог отладить вслепую)
Расширение логирует каждый шаг и умеет скачивать отчёты:
- Кнопка **«🩺 Снять диагностику»** — в любой момент (даже до вставки) скачивает:
  - `vc-diagnostics-<время>.json` — URL, все кандидаты-редакторы (contenteditable / role=textbox)
    с их CSS-путями, классами, data-атрибутами, размерами; выбранный редактор; обрезанное
    дерево DOM окна редактора (до 6 уровней); весь лог и пойманные ошибки;
  - `vc-editor-snapshot-<время>.html` — «сырой» HTML контейнера редактора (data:URL вырезаны).
- Кнопка **«▶ Вставить статью целиком»** по завершении (и при сбое) **сама скачивает**
  `vc-diagnostics-*.json` с потактовой трассировкой: для каждого блока — сработал ли paste
  (изменилось ли число блоков `blocksBefore/blocksAfter`, `defaultPrevented`), время, ошибки.
- Перехватываются `window.error` и `unhandledrejection` страницы.

**Что делать:** запусти один раз, затем пришли автору скачанные файлы
`vc-diagnostics-*.json` (и при наличии `vc-editor-snapshot-*.html`).
По ним он точно определит реальные селекторы блоков и поправит вставку.
Лучше всего: сначала открой окно статьи, кликни в текст, нажми «🩺 Снять диагностику»
и пришли файл — это даст структуру редактора ещё до первой вставки.

## Обновить контент
Запусти `python build_extension.py` в корне проекта — пересоберёт `article_data.js`
с актуальным текстом и картинками из `vc_article/*.png`.
"""
(EXT / "README.md").write_text(readme, encoding="utf-8")

size = sum(f.stat().st_size for f in EXT.glob("*")) / 1024
print(f"Расширение собрано: {EXT}")
print(f"Файлы: {[f.name for f in EXT.glob('*')]}")
print(f"Размер: {size:.0f} КБ (картинки встроены)")
