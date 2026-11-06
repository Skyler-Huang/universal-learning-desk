"use strict";
/* CPA 知识台 · 检索型前端（单文件离线，无 CDN）
   与母版 CSS / DOM 完全兼容；模块：章节卡片 / 核心框架 / 覆盖记录 / 规范语句 / 术语 / 数据体检 / 本地笔记 */

var DATA = JSON.parse(document.getElementById('APP_DATA').textContent);
var MODS = [
  ['cards', '章节卡片', '按章排列的全部知识卡片'],
  ['framework', '核心框架', '章节骨架与页码范围'],
  ['guide', '覆盖记录', '逐章抽取数量与状态'],
  ['actions', '规范语句', '原文中的应当/不得/可以条款'],
  ['glossary', '术语索引', '从卡片正文派生的名词解释'],
  ['stats', '数据体检', '数量、待核、重复与导出'],
  ['notes', '本地笔记', '浏览器本地保存的批注']
];

/* ---------- 数据防呆 ---------- */
function guard() {
  var errs = [];
  if (!DATA || typeof DATA !== 'object') errs.push('APP_DATA 缺失');
  if (!Array.isArray(DATA.cards) || !DATA.cards.length) errs.push('cards 为空');
  if (!Array.isArray(DATA.chapters) || !DATA.chapters.length) errs.push('chapters 为空');
  if (errs.length) {
    document.body.innerHTML = '<div style="padding:40px;font:16px/1.8 system-ui">' +
      '<b>数据载入失败</b><br>' + errs.join('<br>') +
      '<br><br>请重新生成 HTML，或检查 APP_DATA 是否为合法 JSON。</div>';
    throw new Error('data guard: ' + errs.join(','));
  }
}
guard();

var CARDS = DATA.cards.filter(function (c) { return c && c.id && c.ruleText; });
var CHAPTERS = DATA.chapters;
var COVERAGE = DATA.coverage || [];
var SUBJECTS = (DATA.meta.subjects && DATA.meta.subjects.length) ? DATA.meta.subjects : ['资料'];
var BAD_TERM = /[\d，。、；：？！“”‘’"'\/\\|_=+*<>\[\]{}·@#$^&~`]/;
var GLOSSARY = (DATA.glossary || []).filter(function (g) {
  return g && g.term && g.def && g.term.length >= 2 && g.term.length <= 12 && !BAD_TERM.test(g.term);
});
var NOTES_KEY = 'cpa-knowledge-desk-notes-v1';
var notes = {};
try { notes = JSON.parse(localStorage.getItem(NOTES_KEY) || '{}'); } catch (e) { notes = {}; }

var state = { view: 'cards', q: '', f: { subject: new Set(), need: false, chapter: '' } };

function $(s) { return document.querySelector(s); }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function escRe(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function toast(msg) { var t = $('#toast'); t.textContent = msg; t.classList.add('on'); setTimeout(function () { t.classList.remove('on'); }, 1700); }
function saveNotes() { try { localStorage.setItem(NOTES_KEY, JSON.stringify(notes)); } catch (e) { } }

/* ---------- 归一化：全角→半角、去空白、小写 ---------- */
function nf(s) {
  return String(s == null ? '' : s)
    .replace(/[\uFF01-\uFF5E]/g, function (ch) { return String.fromCharCode(ch.charCodeAt(0) - 0xFEE0); })
    .replace(/\u3000/g, ' ').toLowerCase();
}
function flat(s) { return nf(s).replace(/[\s,，。；：、.·\-_/()（）\[\]【】]+/g, ''); }

/* ---------- 拼音（构建期注入 meta.pyMap，仅覆盖标题/术语用字） ---------- */
var PYM = DATA.meta.pyMap || {};
function pyOf(s) {
  var out = '', str = String(s || ''), ch;
  for (var i = 0; i < str.length; i++) { ch = str.charAt(i); out += PYM[ch] || (/[a-z0-9]/i.test(ch) ? ch : ''); }
  return out;
}
function initials(s) {
  var out = '', str = String(s || '');
  for (var i = 0; i < str.length; i++) { var p = PYM[str.charAt(i)]; if (p) out += p.charAt(0); }
  return out;
}

/* ---------- 索引（构建一次，检索不再拼接大字符串） ---------- */
var IDX = [], PYI = [], PYS = [];
CARDS.forEach(function (c) {
  var ids = (c.numbers || []).join(' ');
  IDX.push(flat([c.id, c.title, c.ruleText, c.source, c.chapterName, (c.section || ''), ids].join(' ')));
  var head = (c.title || '') + (c.chapterName || '');
  PYI.push(initials(head));
  PYS.push(pyOf(head));
});
GLOSSARY.forEach(function (g) {
  IDX.push(flat(g.term + g.def + '术语'));
  PYI.push(initials(g.term));
  PYS.push(pyOf(g.term));
});

function bigrams(s) {
  var out = {};
  for (var i = 0; i < s.length - 1; i++) out[s.substr(i, 2)] = 1;
  return out;
}
function fuzzyHit(hay, tok) {
  if (tok.length < 2) return false;
  var bg = bigrams(tok), keys = Object.keys(bg), hit = 0;
  if (!keys.length) return false;
  for (var i = 0; i < keys.length; i++) if (hay.indexOf(keys[i]) >= 0) hit++;
  return hit / keys.length >= 0.8;
}
function tokens(q) { return nf(q).split(/\s+/).filter(Boolean); }

function matches(c, q, i) {
  if (!q) return true;
  var toks = tokens(q), hay = IDX[i], k;
  for (var t = 0; t < toks.length; t++) {
    var tok = flat(toks[t]);
    if (!tok) continue;
    if (hay.indexOf(tok) >= 0) continue;
    /* 编号精确检索：id:税-2.143 */
    if (tok.indexOf('id:') === 0 && flat(c.id).indexOf(tok.slice(3)) >= 0) continue;
    /* 拼音：全拼 / 首字母 */
    if (/^[a-z]+$/.test(tok) && (PYS[i].indexOf(tok) >= 0 || PYI[i].indexOf(tok) >= 0)) continue;
    /* 容错：二元组覆盖率 */
    if (fuzzyHit(hay, tok)) continue;
    return false;
  }
  return true;
}
function passes(c) {
  var f = state.f;
  if (f.subject.size && !f.subject.has(c.subject)) return false;
  if (f.need && !c.needs_review) return false;
  if (f.chapter && (c.subject + '|' + c.chapter) !== f.chapter) return false;
  return true;
}
function filtered() {
  var out = [];
  for (var i = 0; i < CARDS.length; i++) if (passes(CARDS[i]) && matches(CARDS[i], state.q, i)) out.push(CARDS[i]);
  return out;
}
function hitCount(q) {
  var n = 0;
  for (var i = 0; i < CARDS.length; i++) if (passes(CARDS[i]) && matches(CARDS[i], q, i)) n++;
  return n;
}

/* ---------- 术语高亮：只标注「专名级」术语，单卡最多 3 处 ---------- */
var TERMS = GLOSSARY.filter(function (g) {
  return g.term.length >= 3 && (g.freq == null || g.freq <= 40);
}).map(function (g) { return g.term; })
  .filter(function (t, i, a) { return a.indexOf(t) === i; })
  .sort(function (a, b) { return b.length - a.length; }).slice(0, 200);
var TERM_RE = TERMS.length ? new RegExp('(' + TERMS.map(escRe).join('|') + ')', 'g') : null;
var TERM_MAP = {};
GLOSSARY.forEach(function (g) { if (!TERM_MAP[g.term]) TERM_MAP[g.term] = g; });

function markQuery(h, q) {
  if (!q) return h;
  var toks = tokens(q).filter(Boolean).sort(function (a, b) { return b.length - a.length; });
  var re = new RegExp('(' + toks.map(escRe).join('|') + ')', 'gi');
  return h.split(/(<[^>]+>)/g).map(function (p) {
    return p.charAt(0) === '<' ? p : p.replace(re, function (m) { return '<mark>' + m + '</mark>'; });
  }).join('');
}
function richText(text, q, termLimit) {
  var h = esc(text);
  var cap = termLimit == null ? 2 : termLimit;
  if (TERM_RE && cap > 0) {
    var n = 0;
    h = h.replace(TERM_RE, function (m) {
      if (n >= cap) return m;
      n++;
      return '<span class="term" tabindex="0" role="button" data-t="' + m + '">' + m + '</span>';
    });
  }
  return markQuery(h, q);
}
function anchorOfId(id) { return 'e-' + id.replace(/\./g, '-'); }
function refOf(c) {
  return (c.subject || '') + ' 第' + c.chapter + '章 ' + (c.chapterName || '') + ' · 第' + c.page + '页';
}

/* ---------- 侧栏 ---------- */
function renderMods() {
  $('#mods').innerHTML = MODS.map(function (m) {
    return '<button class="mod-btn' + (state.view === m[0] ? ' active' : '') + '" data-view="' + m[0] + '" title="' + esc(m[2]) + '">' + m[1] + '</button>';
  }).join('');
  Array.prototype.forEach.call(document.querySelectorAll('.mod-btn'), function (b) {
    b.onclick = function () { state.view = b.dataset.view; renderMods(); render(); closeDrawer(); window.scrollTo(0, 0); };
  });
}
function renderTree() {
  var counts = {};
  CARDS.forEach(function (c) { var k = c.subject + '|' + c.chapter; counts[k] = (counts[k] || 0) + 1; });
  var html = '';
  SUBJECTS.forEach(function (sub) {
    var chs = CHAPTERS.filter(function (c) { return c.subject === sub; });
    html += '<details class="subj" open><summary>' + esc(sub) + '（' + chs.length + '章）</summary>';
    chs.forEach(function (ch) {
      html += '<div class="chap-link" data-anchor="ch-' + esc(sub) + '-' + ch.no + '"><span>' + ch.no + '. ' + esc(ch.name) + '</span><span class="cnt">' + (counts[sub + '|' + ch.no] || 0) + '条</span></div>';
    });
    html += '</details>';
  });
  $('#tree').innerHTML = html;
  Array.prototype.forEach.call(document.querySelectorAll('.chap-link'), function (el) {
    el.onclick = function () {
      state.view = 'cards'; state.f.chapter = state.f.chapter || ''; renderMods(); render();
      var t = document.getElementById(el.dataset.anchor);
      if (t) setTimeout(function () { t.scrollIntoView({ behavior: 'smooth' }); }, 60);
      closeDrawer();
    };
  });
}
function closeDrawer() { $('#sidebar').classList.remove('open'); $('#overlay').classList.remove('on'); }

/* ---------- 筛选条 ---------- */
function renderFilters() {
  var html = '<div class="fgroup"><span class="lbl">科目</span>';
  SUBJECTS.forEach(function (s) {
    html += '<button class="chip' + (state.f.subject.has(s) ? ' on' : '') + '" data-f="subject" data-v="' + esc(s) + '">' + esc(s) + '</button>';
  });
  html += '</div>';
  html += '<div class="fgroup"><span class="lbl">章节</span><select id="chSel" class="chip" style="max-width:230px">' +
    '<option value="">全部章节</option>' + CHAPTERS.map(function (ch) {
      var v = esc(ch.subject + '|' + ch.no);
      return '<option value="' + v + '"' + (state.f.chapter === ch.subject + '|' + ch.no ? ' selected' : '') + '>' +
        esc(ch.subject + ' 第' + ch.no + '章 ' + ch.name) + '</option>';
    }).join('') + '</select></div>';
  html += '<div class="fgroup"><span class="lbl">质量</span><button class="chip' + (state.f.need ? ' on' : '') +
    '" data-f="need" data-v="1">仅看待核 ' + CARDS.filter(function (c) { return c.needs_review; }).length + '</button></div>';
  html += '<span class="filter-note">当前 ' + filtered().length + ' / ' + CARDS.length + ' 张卡片</span>';
  $('#filters').innerHTML = html;
  Array.prototype.forEach.call(document.querySelectorAll('.chip[data-f]'), function (b) {
    b.onclick = function () {
      if (b.dataset.f === 'need') { state.f.need = !state.f.need; }
      else { var s = state.f[b.dataset.f]; if (s.has(b.dataset.v)) s.delete(b.dataset.v); else s.add(b.dataset.v); }
      render();
    };
  });
  var sel = $('#chSel');
  if (sel) sel.onchange = function () { state.f.chapter = sel.value; render(); };
}

/* ---------- 卡片 ---------- */
function cardHTML(c) {
  var layer = c.layer || 'fact';
  var q = state.q;
  var numHtml = (c.numbers || []).length ? '<div class="nums">数字与门槛（原样）：<b>' + esc(c.numbers.join(' ｜ ')) + '</b></div>' : '';
  var tableHtml = c.table ? '<div class="table-wrap">' + mdTable(c.table) + '</div>' : '';
  var note = notes[c.id] || '';
  return '<article class="card ev-' + layer + '" id="' + anchorOfId(c.id) + '">' +
    '<div class="card-head"><span class="cid">' + esc(c.id) + '</span>' +
    (c.needs_review ? '<span class="layer-badge" style="--ec:var(--danger);--ebg:#fde8e8">待核对</span>' : '') +
    '<button class="src-btn" tabindex="0" aria-label="出处">出处</button>' +
    '<button class="copy-btn" data-cite="' + esc(c.id) + '">复制引用</button>' +
    '<button class="note-btn" data-note="' + esc(c.id) + '">笔记</button></div>' +
    '<h3>' + richText(c.title, q, 1) + '</h3>' +
    '<div class="src-line">' + esc(refOf(c)) + ' ｜ PDF 第 ' + c.pdfPage + ' 页</div>' +
    '<div class="rule' + (layer === 'skeleton' ? ' void' : '') + '">' + richText(c.ruleText, q) + '</div>' +
    numHtml + tableHtml +
    '<div class="src-pop" role="note"><b>出处明细</b><br>科目：' + esc(c.subject) +
    '<br>章节：第' + c.chapter + '章 ' + esc(c.chapterName) +
    '<br>教材页码：第 ' + c.page + ' 页<br>PDF 物理页：' + c.pdfPage +
    '<br>证据类型：资料原文（OCR 识别，已清洗）' +
    '<br>回溯锚点：<code>' + esc(c.mdAnchor || '') + '</code></div>' +
    '<div class="note-area hidden" id="note-' + esc(c.id) + '"><textarea placeholder="本地笔记，仅保存在此浏览器">' + esc(note) + '</textarea>' +
    '<button class="topbtn" data-save="' + esc(c.id) + '">保存笔记</button></div>' +
    '</article>';
}
function mdTable(md) {
  var lines = md.split('\n').filter(function (l) { return l.trim().indexOf('|') === 0; });
  var rows = lines.filter(function (l) { return !/^\|[\s\-|]+\|$/.test(l.trim()); });
  var out = '<table>';
  rows.forEach(function (l, i) {
    var cells = l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (x) { return x.trim(); });
    out += '<tr>' + cells.map(function (x) { return i === 0 ? '<th>' + esc(x) + '</th>' : '<td>' + esc(x) + '</td>'; }).join('') + '</tr>';
  });
  return out + '</table>';
}
function bindCards(root) {
  Array.prototype.forEach.call(root.querySelectorAll('.src-btn'), function (b) {
    b.onclick = function () { var p = b.parentNode.parentNode.querySelector('.src-pop'); if (p) p.classList.toggle('on'); };
  });
  Array.prototype.forEach.call(root.querySelectorAll('[data-cite]'), function (b) {
    b.onclick = function () {
      var c = byId(b.dataset.cite); if (!c) return;
      var url = location.href.split('#')[0] + '#' + anchorOfId(c.id);
      var text = '【' + c.title + '】\n' + c.ruleText + '\n出处：' + refOf(c) + '（PDF 第 ' + c.pdfPage + ' 页）\n' + url;
      copyText(text);
    };
  });
  Array.prototype.forEach.call(root.querySelectorAll('[data-note]'), function (b) {
    b.onclick = function () { var el = document.getElementById('note-' + b.dataset.note); if (el) el.classList.toggle('hidden'); };
  });
  Array.prototype.forEach.call(root.querySelectorAll('[data-save]'), function (b) {
    b.onclick = function () {
      var el = document.getElementById('note-' + b.dataset.save);
      var val = el.querySelector('textarea').value;
      if (val.trim()) notes[b.dataset.save] = val; else delete notes[b.dataset.save];
      saveNotes(); toast('笔记已保存到本地'); if (state.view === 'notes') render();
    };
  });
}
function byId(id) { for (var i = 0; i < CARDS.length; i++) if (CARDS[i].id === id) return CARDS[i]; return null; }
function copyText(t) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t).then(function () { toast('已复制：标题 + 原文 + 出处'); }, function () { fallbackCopy(t); });
  } else fallbackCopy(t);
}
function fallbackCopy(t) {
  var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); toast('已复制'); } catch (e) { toast('复制失败'); }
  document.body.removeChild(ta);
}

/* ---------- 视图 ---------- */
function renderCardsView() {
  var list = filtered(), html = '';
  if (!list.length) {
    return '<div class="panel empty"><b>未命中</b><br>当前搜索或筛选条件没有匹配卡片。<br><span style="font-size:12px">试试更短的关键词、拼音（如 zengzhishui），或清空章节筛选。</span></div>';
  }
  var groups = {};
  list.forEach(function (c) { var k = c.subject + '|' + c.chapter; (groups[k] = groups[k] || []).push(c); });
  SUBJECTS.forEach(function (sub) {
    CHAPTERS.filter(function (ch) { return ch.subject === sub; }).forEach(function (ch) {
      var arr = groups[sub + '|' + ch.no]; if (!arr || !arr.length) return;
      var cov = COVERAGE.filter(function (x) { return x.subject === sub && x.no === ch.no; })[0] || {};
      html += '<section class="chapter" id="ch-' + esc(sub) + '-' + ch.no + '">' +
        '<h2>' + esc(sub) + ' · 第' + ch.no + '章 ' + esc(ch.name) + '</h2>' +
        '<div class="covbar"><span>教材页 ' + cov.pageStart + '–' + cov.pageEnd + '</span><span>原文 ' + cov.sourcePages + ' 页</span>' +
        '<span>卡片 ' + cov.cards + '</span><span>数字 ' + cov.numbers + '</span></div>' +
        '<div class="cards">' + arr.map(cardHTML).join('') + '</div></section>';
    });
  });
  return html;
}
function renderFramework() {
  var html = '<div class="panel"><h3>核心框架 · 章节骨架</h3><p style="font-size:13px;color:var(--muted)">' +
    SUBJECTS.map(function (s) { return esc(s) + ' ' + CHAPTERS.filter(function (c) { return c.subject === s; }).length + ' 章'; }).join(' / ') +
    '；页码为教材页码，PDF 页为物理页。</p></div>';
  SUBJECTS.forEach(function (sub) {
    html += '<div class="panel"><h3>' + esc(sub) + '</h3>';
    CHAPTERS.filter(function (c) { return c.subject === sub; }).forEach(function (ch) {
      var cov = COVERAGE.filter(function (x) { return x.subject === sub && x.no === ch.no; })[0] || {};
      html += '<div class="tree-row"><a href="#ch-' + esc(sub) + '-' + ch.no + '">第' + ch.no + '章 ' + esc(ch.name) + '</a>' +
        '<span class="sec">' + (ch.sections && ch.sections.length ? ch.sections.map(esc).join(' · ') : '按原章节展开') + '</span>' +
        '<span class="tag">第 ' + cov.pageStart + '–' + cov.pageEnd + ' 页</span></div>';
    });
    html += '</div>';
  });
  return html;
}
function renderGuide() {
  var html = '<div class="panel"><h3>覆盖记录 · 逐章抽取</h3><p style="font-size:13px;color:var(--muted)">每章列出页码范围、原文页数、卡片与数字数量；未覆盖页不会被静默省略。</p></div>';
  SUBJECTS.forEach(function (sub) {
    html += '<div class="panel"><h3>' + esc(sub) + '</h3>';
    COVERAGE.filter(function (c) { return c.subject === sub; }).forEach(function (c) {
      var warn = String(c.status).indexOf('未') >= 0;
      html += '<div class="tree-row"><b>第' + c.no + '章 ' + esc(c.name) + '</b><span class="sec">教材第 ' + c.pageStart + '–' + c.pageEnd +
        ' 页（PDF ' + c.pdfStart + '–' + c.pdfEnd + '）｜原文 ' + c.sourcePages + ' 页｜卡片 ' + c.cards + '｜数字 ' + c.numbers + '</span>' +
        '<span class="tag' + (warn ? ' warn' : '') + '">' + esc(c.status) + '</span></div>';
    });
    html += '</div>';
  });
  return html;
}
function renderActions() {
  var list = filtered().filter(function (c) { return /应当|不得|可以|必须|适用|免征|征收|缴纳|扣除|准予/.test(c.ruleText); });
  return '<div class="panel"><h3>规范语句 · 原文中的权利义务条款（' + list.length + ' 条）</h3><p style="font-size:13px;color:var(--muted)">只做原文筛选，不作改写。</p></div>' +
    (list.length ? '<div class="cards">' + list.slice(0, 120).map(cardHTML).join('') + '</div>' : '<div class="panel empty">未命中</div>');
}
function renderGlossary() {
  var q = state.q;
  var list = GLOSSARY.filter(function (g) { return !q || nf(g.term + g.def).indexOf(nf(q)) >= 0; });
  return '<div class="panel"><h3>术语索引 · 从卡片正文派生（' + list.length + ' 条）</h3><p style="font-size:13px;color:var(--muted)">定义均来自卡片原文；术语已通过乱码/残句闸门。</p></div>' +
    (list.length ? '<div class="gloss-grid">' + list.map(function (g) {
      return '<div class="gloss-item"><b>' + markQuery(esc(g.term), q) + '</b><div class="gd">' +
        markQuery(esc(g.def), q) + '</div><div class="gd">出处：' + esc(g.subject) + ' 第' + g.chapter + ' 章 第' + g.page + ' 页</div></div>';
    }).join('') + '</div>' : '<div class="panel empty">未命中</div>');
}
function renderStats() {
  var bySub = {};
  CARDS.forEach(function (c) { bySub[c.subject] = (bySub[c.subject] || 0) + 1; });
  var need = CARDS.filter(function (c) { return c.needs_review; });
  var lens = 0; CARDS.forEach(function (c) { lens += c.ruleText.length; });
  var dupTitles = CARDS.length - new Set(CARDS.map(function (c) { return c.title; })).size;
  var pages = new Set(CARDS.map(function (c) { return c.subject + '|' + c.page; })).size;
  return '<div class="panel"><h3>数据体检</h3>' +
    '<div class="tree-row"><b>卡片</b><span class="sec">' + CARDS.length + ' 张（' + Object.keys(bySub).map(function (k) { return k + ' ' + bySub[k]; }).join(' / ') + '）</span></div>' +
    '<div class="tree-row"><b>覆盖页</b><span class="sec">' + pages + ' 页 / 平均每页 ' + (CARDS.length / pages).toFixed(1) + ' 张</span></div>' +
    '<div class="tree-row"><b>正文</b><span class="sec">平均 ' + Math.round(lens / CARDS.length) + ' 字 / 张</span></div>' +
    '<div class="tree-row"><b>术语</b><span class="sec">' + GLOSSARY.length + ' 条（乱码闸门已生效）</span></div>' +
    '<div class="tree-row"><b>待核对</b><span class="sec">' + need.length + ' 张' + (need.length ? '：' + need.slice(0, 12).map(function (c) { return '<a href="#' + anchorOfId(c.id) + '">' + esc(c.id) + '</a>'; }).join(' ') : '') + '</span></div>' +
    '<div class="tree-row"><b>重复标题</b><span class="sec">' + dupTitles + ' 组（同名不同页，属正常）</span></div>' +
    '<div class="tree-row"><b>生成</b><span class="sec">' + esc(DATA.meta.generated || '') + '</span></div></div>' +
    '<div class="panel"><h3>导出</h3><p style="font-size:13px;color:var(--muted)">导出为纯文本语料，可直接投喂任意 AI；笔记单独导出便于备份。</p>' +
    '<div class="quiz-nav"><button class="topbtn" data-export="json">导出卡片 JSON</button>' +
    '<button class="topbtn" data-export="md">导出 Markdown</button>' +
    '<button class="topbtn" data-export="glossary">导出术语表</button>' +
    '<button class="topbtn" data-export="notes">导出笔记</button></div></div>';
}
function renderNotes() {
  var ids = Object.keys(notes);
  if (!ids.length) return '<div class="panel empty">暂无本地笔记。在任意卡片点「笔记」即可写入，仅保存在当前浏览器。</div>';
  var html = '<div class="panel"><h3>本地笔记 · ' + ids.length + ' 条</h3><p style="font-size:12px;color:var(--muted)">保存在浏览器 localStorage；建议用「导出笔记」备份。</p></div>';
  ids.forEach(function (id) {
    var c = byId(id);
    html += '<div class="panel"><b>' + esc(id) + '</b> ' + (c ? '<a href="#' + anchorOfId(id) + '">' + esc(c.title) + '</a>' : '') +
      '<div style="white-space:pre-wrap;margin-top:8px">' + esc(notes[id]) + '</div>' +
      '<button class="topbtn" data-del="' + esc(id) + '" style="margin-top:8px">删除</button></div>';
  });
  return html;
}
function render() {
  var v = $('#view'), html = '';
  switch (state.view) {
    case 'framework': html = renderFramework(); break;
    case 'guide': html = renderGuide(); break;
    case 'actions': html = renderActions(); break;
    case 'glossary': html = renderGlossary(); break;
    case 'stats': html = renderStats(); break;
    case 'notes': html = renderNotes(); break;
    default: html = renderCardsView();
  }
  v.innerHTML = html;
  bindCards(v);
  bindExtras();
  renderResults();
  renderFilters();
  $('#footnote').innerHTML = esc(DATA.meta.footnote || '') +
    '<br>本页为单文件离线知识库：无 CDN、无服务器、无账号；笔记仅存本地浏览器。';
}
function bindExtras() {
  Array.prototype.forEach.call(document.querySelectorAll('[data-del]'), function (b) {
    b.onclick = function () { delete notes[b.dataset.del]; saveNotes(); render(); };
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-export]'), function (b) {
    b.onclick = function () { doExport(b.dataset.export); };
  });
}
function renderResults() {
  var box = $('#results');
  if (!state.q) { box.classList.add('hidden'); box.innerHTML = ''; return; }
  var hits = filtered();
  box.classList.remove('hidden');
  if (!hits.length) {
    box.innerHTML = '<div class="rhead">搜索「' + esc(state.q) + '」</div><div class="empty"><b>未命中</b><br>未检索到该内容；本知识台不补写、不编造。</div>';
    return;
  }
  box.innerHTML = '<div class="rhead">搜索「' + esc(state.q) + '」命中 ' + hits.length + ' 张（点击直达）</div>' +
    hits.slice(0, 50).map(function (c) {
      return '<button class="res-item" data-go="' + esc(c.id) + '"><span class="rid">' + esc(c.id) + '</span>' +
        esc(c.title) + '<span class="rsub">' + esc(refOf(c)) + '</span></button>';
    }).join('');
  Array.prototype.forEach.call(box.querySelectorAll('[data-go]'), function (b) {
    b.onclick = function () {
      state.view = 'cards'; renderMods(); render();
      var el = document.getElementById(anchorOfId(b.dataset.go));
      if (el) { el.scrollIntoView({ behavior: 'smooth' }); history.replaceState(null, '', '#' + anchorOfId(b.dataset.go)); }
      closeDrawer();
    };
  });
}

/* ---------- 导出 ---------- */
function download(name, text, type) {
  var blob = new Blob([text], { type: type || 'text/plain;charset=utf-8' });
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  toast('已导出 ' + name);
}
function exportMarkdown() {
  var lines = ['# ' + (DATA.meta.title || '知识台'), '', '> ' + (DATA.meta.footnote || ''), ''];
  SUBJECTS.forEach(function (sub) {
    lines.push('# ' + sub, '');
    CHAPTERS.filter(function (c) { return c.subject === sub; }).forEach(function (ch) {
      lines.push('## 第' + ch.no + '章 ' + ch.name, '');
      CARDS.filter(function (c) { return c.subject === sub && c.chapter === ch.no; }).forEach(function (c) {
        lines.push('### ' + c.title, '', c.ruleText, '', '> 出处：' + refOf(c) + '（PDF 第 ' + c.pdfPage + ' 页）', '');
      });
    });
  });
  download('知识台.md', lines.join('\n'), 'text/markdown;charset=utf-8');
}
function doExport(kind) {
  var base = (DATA.meta.title || 'knowledge').replace(/[\\/:*?"<>|\s]/g, '_');
  if (kind === 'json') download(base + '_cards.json', JSON.stringify({ meta: DATA.meta, chapters: CHAPTERS, cards: CARDS, glossary: GLOSSARY }, null, 1), 'application/json;charset=utf-8');
  else if (kind === 'md') exportMarkdown();
  else if (kind === 'glossary') download(base + '_glossary.md', GLOSSARY.map(function (g) { return '- **' + g.term + '**：' + g.def + '（' + g.subject + ' 第' + g.chapter + ' 章 第' + g.page + ' 页）'; }).join('\n'), 'text/markdown;charset=utf-8');
  else if (kind === 'notes') {
    var ids = Object.keys(notes);
    download(base + '_notes.md', ids.length ? ids.map(function (id) { var c = byId(id); return '## ' + id + (c ? ' ' + c.title : '') + '\n\n' + notes[id] + '\n'; }).join('\n') : '（无笔记）', 'text/markdown;charset=utf-8');
  }
}

/* ---------- 顶栏：导出菜单 ---------- */
(function () {
  var btn = document.createElement('button');
  btn.className = 'topbtn'; btn.id = 'exportBtn'; btn.textContent = '导出';
  btn.setAttribute('aria-label', '导出数据');
  var theme = $('#themeBtn');
  theme.parentNode.insertBefore(btn, theme);
  var menu = null;
  btn.onclick = function (e) {
    e.stopPropagation();
    if (menu) { menu.remove(); menu = null; return; }
    menu = document.createElement('div');
    menu.style.cssText = 'position:fixed;top:64px;right:14px;z-index:95;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);padding:6px;min-width:170px';
    ['md|导出 Markdown','json|导出卡片 JSON','glossary|导出术语表','notes|导出笔记','print|打印当前视图'].forEach(function (x) {
      var k = x.split('|')[0], label = x.split('|')[1];
      var b = document.createElement('button');
      b.className = 'topbtn'; b.textContent = label;
      b.style.cssText = 'display:block;width:100%;margin:3px 0;justify-content:flex-start';
      b.onclick = function () { if (k === 'print') window.print(); else doExport(k); menu.remove(); menu = null; };
      menu.appendChild(b);
    });
    document.body.appendChild(menu);
  };
  document.addEventListener('click', function () { if (menu) { menu.remove(); menu = null; } });
})();

/* ---------- 全局交互 ---------- */
var searchTimer = null;
$('#q').addEventListener('input', function (e) {
  state.q = e.target.value.trim();
  clearTimeout(searchTimer); searchTimer = setTimeout(render, 130);
});
$('#q').addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { e.target.value = ''; state.q = ''; render(); }
});
document.addEventListener('keydown', function (e) {
  var tag = (e.target.tagName || '').toLowerCase();
  if (e.key === '/' && tag !== 'input' && tag !== 'textarea') { e.preventDefault(); $('#q').focus(); }
});
$('#themeBtn').onclick = function () {
  var d = document.documentElement;
  var dark = d.getAttribute('data-theme') === 'dark';
  d.setAttribute('data-theme', dark ? 'light' : 'dark');
  this.textContent = dark ? '🌙 深色' : '☀️ 浅色';
  try { localStorage.setItem('cpa-knowledge-desk-theme', dark ? 'light' : 'dark'); } catch (e) { }
};
try {
  var th = localStorage.getItem('cpa-knowledge-desk-theme');
  if (th === 'dark') { document.documentElement.setAttribute('data-theme', 'dark'); $('#themeBtn').textContent = '☀️ 浅色'; }
} catch (e) { }
$('#burger').onclick = function () { $('#sidebar').classList.toggle('open'); $('#overlay').classList.toggle('on'); };
$('#overlay').onclick = closeDrawer;

/* ---------- 移动端抽屉手势（保留右滑关闭 / 左缘右滑打开） ---------- */
(function () {
  var x0 = null, y0 = null, wasOpen = false;
  document.addEventListener('touchstart', function (e) {
    if (!e.touches || e.touches.length !== 1) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
    wasOpen = $('#sidebar').classList.contains('open');
  }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (x0 == null || !e.changedTouches || !e.changedTouches.length) return;
    var t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0, sx = x0;
    x0 = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.3) return;
    if (wasOpen) closeDrawer();
    else if (sx < 40 && dx > 0) { $('#sidebar').classList.add('open'); $('#overlay').classList.add('on'); }
  }, { passive: true });
})();

/* ---------- 术语弹层 ---------- */
document.addEventListener('click', function (e) {
  var t = e.target.closest ? e.target.closest('.term') : null;
  var pop = $('#termPop');
  if (t) {
    e.stopPropagation();
    var g = TERM_MAP[t.dataset.t];
    if (g) {
      pop.innerHTML = '<b>' + esc(g.term) + '</b><div>' + esc(g.def) + '</div><span class="ts">出处：' + esc(g.subject) + ' 第' + g.chapter + ' 章 第' + g.page + ' 页</span>';
      var r = t.getBoundingClientRect();
      pop.style.left = Math.max(8, Math.min(window.innerWidth - 350, r.left)) + 'px';
      pop.style.top = Math.max(64, Math.min(window.innerHeight - 180, r.bottom + 8)) + 'px';
      pop.style.display = 'block';
    }
  } else pop.style.display = 'none';
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { $('#termPop').style.display = 'none'; closeDrawer(); }
  var t = e.target.closest ? e.target.closest('.term') : null;
  if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); t.click(); }
});
window.addEventListener('hashchange', function () {
  var id = location.hash.slice(1);
  if (id && id.indexOf('e-') === 0) {
    var el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }
});

renderMods(); renderTree(); render();
