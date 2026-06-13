const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

// 提示詞開頭的共用提醒：請 AI 先查最新資料再回答（適用所有科目，非僅法規）。
const SEARCH_HINT = '請先上網搜尋最新的相關資訊，確認內容仍為正確且現行有效後再回答。';

function isMultiAnswer(q) {
  return Array.isArray(q.answer);
}

function multiAnswerCorrect(userAns, answer) {
  if (!Array.isArray(userAns) || !Array.isArray(answer)) return false;
  if (userAns.length !== answer.length) return false;
  const a = [...userAns].sort();
  const b = [...answer].sort();
  return a.every((v, i) => v === b[i]);
}

// 判定單題作答結果（單選/複選/送分共用）：answered 是否有作答、ok 是否得分
function evaluateAnswer(q, ua) {
  const multi = isMultiAnswer(q);
  const answered = multi
    ? (Array.isArray(ua) && ua.length > 0)
    : (ua !== null && ua !== undefined);
  const ok = answered && (q.freeScore ? true : (multi ? multiAnswerCorrect(ua, q.answer) : ua === q.answer));
  return { answered, ok };
}

function formatAnswerLetters(ans) {
  if (Array.isArray(ans)) return ans.map(i => LETTERS[i]).filter(Boolean).join(',');
  return LETTERS[ans] || '未設定';
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// 把值安全地塞進 HTML 屬性裡的 inline handler 參數（onclick="fn(${jsArg(v)})"）
function jsArg(value) {
  return JSON.stringify(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

const THEME_KEY = 'exam_bank_theme';

function getStoredTheme() {
  try {
    const theme = localStorage.getItem(THEME_KEY);
    return theme === 'dark' || theme === 'light' ? theme : '';
  } catch {
    return '';
  }
}

function getPreferredTheme() {
  const stored = getStoredTheme();
  if (stored) return stored;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function updateThemeToggle(theme) {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const isDark = theme === 'dark';
  btn.textContent = isDark ? '☀️ 淺色' : '🌙 深色';
  btn.setAttribute('aria-label', isDark ? '切換成淺色模式' : '切換成深色模式');
}

function applyTheme(theme) {
  const next = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  updateThemeToggle(next);
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem(THEME_KEY, next); } catch { }
  applyTheme(next);
}

function installThemeToggle() {
  if (document.getElementById('themeToggle')) return;
  const btn = document.createElement('button');
  btn.id = 'themeToggle';
  btn.type = 'button';
  btn.className = 'theme-toggle';
  btn.onclick = toggleTheme;
  document.body.appendChild(btn);
  updateThemeToggle(document.documentElement.dataset.theme || getPreferredTheme());
}

applyTheme(getPreferredTheme());
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installThemeToggle);
} else {
  installThemeToggle();
}

let _toastEl = null;
let _toastTimer = null;

function showToast(msg, ms = 1800) {
  if (!_toastEl) {
    _toastEl = document.createElement('div');
    _toastEl.className = 'toast';
    document.body.appendChild(_toastEl);
  }
  clearTimeout(_toastTimer);
  _toastEl.textContent = msg;
  _toastEl.classList.add('show');
  _toastTimer = setTimeout(() => _toastEl.classList.remove('show'), ms);
}

async function copyText(text, btnEl) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }

  if (btnEl) {
    const orig = btnEl.innerHTML;
    btnEl.innerHTML = '已複製';
    btnEl.classList.add('copied');
    setTimeout(() => {
      btnEl.innerHTML = orig;
      btnEl.classList.remove('copied');
    }, 2000);
  }

  showToast('文字已複製到剪貼簿');
}

function normalizeMaterials(materials) {
  return Array.isArray(materials) ? materials.filter(Boolean) : [];
}

function buildMaterialText(materials) {
  return normalizeMaterials(materials).map((material) => {
    const title = material.title ? `${material.title}\n` : '';
    if (material.type === 'table') {
      const headers = Array.isArray(material.headers) ? material.headers : [];
      const rows = Array.isArray(material.rows) ? material.rows : [];
      const tableRows = [];

      if (headers.length) {
        tableRows.push(`| ${headers.join(' | ')} |`);
        tableRows.push(`| ${headers.map(() => '---').join(' | ')} |`);
      }

      rows.forEach((row) => {
        const cells = Array.isArray(row) ? row : Object.values(row || {});
        tableRows.push(`| ${cells.join(' | ')} |`);
      });

      const notes = material.notes ? `\n${material.notes}` : '';
      return `${title}${tableRows.join('\n')}${notes}`.trim();
    }

    if (material.type === 'image') {
      const src = material.src ? `圖片路徑：${material.src}` : '圖片材料';
      const alt = material.alt ? `\n圖片說明：${material.alt}` : '';
      const notes = material.notes ? `\n${material.notes}` : '';
      return `${title}${src}${alt}${notes}`.trim();
    }

    const body = material.content || material.markdown || '';
    return `${title}${body}`.trim();
  }).filter(Boolean).join('\n\n');
}

function renderMaterialsHTML(materials) {
  const html = normalizeMaterials(materials).map((material) => {
    const title = material.title ? `<div class="material-title">${esc(material.title)}</div>` : '';

    if (material.type === 'table') {
      const headers = Array.isArray(material.headers) ? material.headers : [];
      const rows = Array.isArray(material.rows) ? material.rows : [];
      const headerHtml = headers.length
        ? `<thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>`
        : '';
      const bodyHtml = rows.map((row) => {
        const cells = Array.isArray(row) ? row : Object.values(row || {});
        return `<tr>${cells.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`;
      }).join('');
      const notes = material.notes ? `<div class="material-notes">${esc(material.notes)}</div>` : '';

      return `<div class="material-block">${title}<div class="material-table-wrap"><table class="material-table">${headerHtml}<tbody>${bodyHtml}</tbody></table></div>${notes}</div>`;
    }

    if (material.type === 'image') {
      const src = material.src ? toAssetUrl(material.src) : '';
      const alt = material.alt || material.title || '題目附圖';
      const notes = material.notes ? `<div class="material-notes">${esc(material.notes)}</div>` : '';
      const imageHtml = src
        ? `<img class="material-image" src="${esc(src)}" alt="${esc(alt)}" loading="lazy">`
        : `<div class="material-text">${esc(alt)}</div>`;
      return `<div class="material-block">${title}<div class="material-image-wrap">${imageHtml}</div>${notes}</div>`;
    }

    const body = material.content || material.markdown || '';
    return `<div class="material-block">${title}<div class="material-text">${esc(body)}</div></div>`;
  }).join('');

  return html ? `<div class="q-materials">${html}</div>` : '';
}

function buildPrompt(q, userAns, { searchHint = true } = {}) {
  let userLetter;
  if (isMultiAnswer(q)) {
    userLetter = Array.isArray(userAns) && userAns.length > 0 ? formatAnswerLetters(userAns) : '未作答';
  } else {
    userLetter = userAns !== undefined && userAns !== null ? LETTERS[userAns] : '未作答';
  }
  const correctLetter = q.freeScore ? '送分' : formatAnswerLetters(q.answer);
  const materialsText = buildMaterialText(q.materials);
  let t = '';
  if (searchHint) t += `${SEARCH_HINT}\n`;
  t += `請說明這題為什麼正確答案是 ${correctLetter}，並分析我選的答案 ${userLetter}。\n`;
  t += `請用簡潔、易懂的方式說明，先講解題意，再比較各選項，最後指出判斷關鍵。\n\n`;
  t += `題目：${q.question}\n`;
  if (materialsText) {
    t += `\n附表/資料：\n${materialsText}\n`;
  }
  q.options.forEach((opt, i) => {
    t += `(${LETTERS[i]}) ${opt}\n`;
  });
  t += `\n我的答案：${userLetter}\n正確答案：${correctLetter}\n`;
  return t;
}

function buildBrowsePrompt(q, { searchHint = true } = {}) {
  const correctLetter = q.freeScore ? '送分' : formatAnswerLetters(q.answer);
  const materialsText = buildMaterialText(q.materials);
  let t = '';
  if (searchHint) t += `${SEARCH_HINT}\n`;
  t += `請說明這題為什麼正確答案是 ${correctLetter}。\n`;
  t += `請用簡潔、易懂的方式說明，先講解題意，再比較各選項，最後指出判斷關鍵。\n\n`;
  t += `題目：${q.question}\n`;
  if (materialsText) {
    t += `\n附表/資料：\n${materialsText}\n`;
  }
  q.options.forEach((opt, i) => {
    t += `(${LETTERS[i]}) ${opt}\n`;
  });
  t += `\n正確答案：${correctLetter}\n`;
  return t;
}

function buildReviewItemHTML(q, opts) {
  applyQuestionOverrides(q);
  const { idx, userAns, mode } = opts;
  const isResult = mode === 'result';
  const isFreeScore = !!q.freeScore;
  const multi = isMultiAnswer(q);

  const { answered, ok } = evaluateAnswer(q, userAns);
  const isSkipped = isResult && !answered;
  const isCorrect = isResult && ok;
  const isWrong = isResult && !isCorrect;

  let cls = 'ri-neutral';
  let badgeCls = 'badge-neutral';
  let badgeText = isFreeScore ? '送分' : (multi ? '複選' : '');

  if (isResult) {
    cls = isWrong ? 'ri-wrong' : 'ri-correct';
    badgeCls = isWrong ? 'badge-wrong' : 'badge-correct';
    badgeText = isSkipped ? '未作答' : (isFreeScore ? '送分' : (isCorrect ? '答對' : '答錯'));
    if (multi && !isSkipped) badgeText += '（複選）';
  }

  const correctSet = multi ? new Set(q.answer) : null;
  const userSet = multi && Array.isArray(userAns) ? new Set(userAns) : null;

  const optsHtml = q.options.map((opt, oi) => {
    let c = '';
    if (multi) {
      if (!isFreeScore && correctSet.has(oi)) {
        c = 'opt-correct';
      }
      if (isResult && !isCorrect && userSet && userSet.has(oi) && !correctSet.has(oi)) {
        c = 'opt-wrong';
      }
    } else {
      if (!isFreeScore && oi === q.answer) {
        c = 'opt-correct';
      }
      if (isResult && userAns === oi && !isCorrect) {
        c = 'opt-wrong';
      }
    }
    return `<div class="${c}">(${LETTERS[oi]}) ${esc(opt)}</div>`;
  }).join('');

  const copyFn = isResult ? `copyReview(${idx})` : `copyBrowse(${idx})`;
  const copyLabel = '複製解析提示';

  const meta = getQuestionMetadata(q._bank || '', q.id);
  const hasNotes = !!meta.notes;
  const metaHtml = `
    <div class="q-meta-panel" data-bank="${q._bank || ''}" data-qid="${q.id}">
      <div class="q-meta-tags">
        <span style="font-size:0.85rem;color:var(--text-dim);font-weight:700;margin-right:4px">題目標記：</span>
        <div class="tag-pill tag-key ${meta.tag === 'key' ? 'active' : ''}" onclick="toggleQuestionTag('${q._bank || ''}', ${q.id}, 'key', this)">⭐ 重點</div>
        <div class="tag-pill tag-exclude ${meta.tag === 'exclude' ? 'active' : ''}" onclick="toggleQuestionTag('${q._bank || ''}', ${q.id}, 'exclude', this)">🚫 排除</div>
        <div class="tag-pill tag-notes-toggle active ${hasNotes ? 'has-notes' : ''}" onclick="toggleNotesCollapse(this)">📝 筆記</div>
      </div>
      <div class="q-meta-notes-wrapper" style="display: block; margin-top: 8px;">
        <textarea class="q-notes-input" placeholder="對此題撰寫筆記心得..." oninput="saveQuestionNotes('${q._bank || ''}', ${q.id}, this.value, this)">${esc(meta.notes)}</textarea>
      </div>
    </div>`;

  const repeatsHtml = q._repeats && q._repeats.length > 1
    ? `<span class="repeat-badge" style="margin-left:8px" title="重複考過年份：${q._repeats.join('、')}">🔄 ${q._repeats.map(r => r.split(' ')[0]).join('、')} 年</span>`
    : '';
  const amendLinkHtml = q._amendmentUrl
    ? ` <a href="${esc(q._amendmentUrl)}" target="_blank" rel="noopener" class="amendment-link" title="查看現行法條">📜 查看異動法條</a>`
    : '';
  const warningHtml = q._warning
    ? `<div class="amendment-warning">${esc(q._warning)}${amendLinkHtml}</div>`
    : '';

  const attemptHtml = q._bank
    ? ` · ${questionAttemptLabel(q._bank, q.id)}`
    : '';
  const sourceHtml = q._bank
    ? `<div class="ri-source" style="font-size:0.8rem;color:var(--text-dim);margin-bottom:8px">📄 來源：${esc(bankLabel(q._bank))} · 原試卷第 ${q.id} 題${attemptHtml}</div>`
    : '';

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span style="font-weight:700;color:var(--text-dim)">第 ${idx + 1} 題 ${repeatsHtml}</span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
    ${sourceHtml}
    <div class="ri-q">${esc(q.question)}</div>
    ${warningHtml}
    ${renderMaterialsHTML(q.materials)}
    <div class="ri-opts">${optsHtml}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;gap:12px;flex-wrap:wrap">
      <button class="copy-btn" id="cpbtn-${idx}" onclick="${copyFn}">${copyLabel}</button>
    </div>
    ${metaHtml}
  </div>`;
}

function navigateTo(page) {
  window.location.href = page;
}

const DB_KEY = 'quiz_history';

function toAssetUrl(path) {
  const url = new URL(encodeURI(path), document.baseURI);
  const version = new URLSearchParams(window.location.search).get('v');
  if (version && !url.searchParams.has('v')) {
    url.searchParams.set('v', version);
  }
  return url.toString();
}

async function fetchJson(path) {
  // 交給瀏覽器 HTTP 快取（GitHub Pages 為 max-age=600 + ETag），
  // 題庫更新最多延遲 10 分鐘可見，換來重複開測驗不必整包重新下載。
  const res = await fetch(toAssetUrl(path));
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status}`);
  }
  return res.json();
}

// 題庫索引快取（file -> 顯示名稱、file -> 是否屬交通部分流）。
// 由 loadBankLabels() 或頁面自行載入 banks.json 後呼叫 registerBankIndex() 填入。
let _bankLabelMap = null;
let _bankTrackMap = null;

function registerBankIndex(banks) {
  _bankLabelMap = _bankLabelMap || {};
  _bankTrackMap = _bankTrackMap || {};
  (banks || []).forEach(b => {
    if (!b || !b.file) return;
    _bankLabelMap[b.file] = b.displayName || b.name || b.file;
    _bankTrackMap[b.file] = TRACKS.traffic.sources.includes(b.source || '');
  });
  invalidateHistoryCaches();
}

async function loadBankLabels() {
  if (_bankLabelMap) return _bankLabelMap;
  _bankLabelMap = {};
  try {
    registerBankIndex(await fetchJson('data/banks.json'));
  } catch (e) {
    console.error('Failed to load bank labels', e);
  }
  return _bankLabelMap;
}

function bankLabel(bankPath) {
  if (!bankPath) return '未知來源';
  if (_bankLabelMap && _bankLabelMap[bankPath]) return _bankLabelMap[bankPath];
  // 後備：直接從檔名推導
  return bankPath.replace(/^.*\//, '').replace(/\.json$/, '');
}

function loadLocalHistory() {
  try {
    const raw = localStorage.getItem(DB_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error('Failed to load history from localStorage', e);
    return [];
  }
}

function saveLocalHistory(record) {
  const history = loadLocalHistory();
  history.push(record);
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(history));
  } catch (e) {
    console.error('Failed to save history to localStorage', e);
  }
  invalidateHistoryCaches();
}

function deleteLocalHistory(idx) {
  const history = loadLocalHistory();
  if (idx >= 0 && idx < history.length) {
    history.splice(idx, 1);
    localStorage.setItem(DB_KEY, JSON.stringify(history));
    invalidateHistoryCaches();
  }
}

function clearLocalHistory() {
  localStorage.setItem(DB_KEY, JSON.stringify([]));
  invalidateHistoryCaches();
}

function getWrongPool() {
  const history = loadLocalHistory();
  const today = new Date().toISOString().split('T')[0];
  const lastResult = {};
  const everWrong = new Set();
  const todayWrong = new Set();

  for (const session of history) {
    const sessionBank = session.bank || 'questions/questions.json';
    for (const item of session.answers || []) {
      const bank = item.bank || sessionBank;
      
      // Filter dynamically: only count questions from banks that belong to the active track
      if (!isBankFileInActiveTrack(bank)) continue;
      
      const qid = item.qid;
      const key = `${bank}|${qid}`;
      const ok = item.correct;
      lastResult[key] = ok;
      if (!ok) {
        everWrong.add(key);
        if (session.date_iso && session.date_iso.split('T')[0] === today) {
          todayWrong.add(key);
        }
      }
    }
  }

  const stillWrong = Object.keys(lastResult).filter((key) => !lastResult[key]);
  const pastWrong = [...everWrong].filter((key) => !todayWrong.has(key));

  const toList = (keys) => keys.map((key) => {
    const [bank, qid] = key.split('|');
    return { bank, qid: parseInt(qid, 10) };
  }).sort((a, b) => a.bank.localeCompare(b.bank) || a.qid - b.qid);

  return {
    ever_wrong: toList([...everWrong]),
    still_wrong: toList(stillWrong),
    today_wrong: toList([...todayWrong]),
    past_wrong: toList(pastWrong),
  };
}

// 將 ISO 時間轉成 M/D（本地時區）；無效時回空字串
function formatMonthDay(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// 練習統計（僅計目前作答類別）：
//   attemptedCount 不重複已作答題數（跳過不算、重複不加）
//   attemptCount   累計作答次數（含重複，跳過不算）
//   perBank        每個題庫的 { lastIso 最後練習時間, attempted 已練過的題號集合 }
// 結果會快取（搜尋框每個按鍵都會重繪題庫清單，不能每次全掃歷程），
// 紀錄或分流變動時由 invalidateHistoryCaches() 失效。
function getPracticeStats() {
  if (_practiceStatsCache) return _practiceStatsCache;
  const history = loadLocalHistory();
  const attempted = new Set();
  let attemptCount = 0;
  const perBank = {};

  for (const session of history) {
    const sessionBank = session.bank || 'questions/questions.json';
    const iso = session.date_iso || '';
    for (const item of session.answers || []) {
      const bank = item.bank || sessionBank;
      if (!isBankFileInActiveTrack(bank)) continue;

      // 該題庫只要出現在這次測驗就算「練習過」一次（用於最後練習日期）
      if (!perBank[bank]) perBank[bank] = { lastIso: '', attempted: new Set() };
      if (iso > perBank[bank].lastIso) perBank[bank].lastIso = iso;

      // 跳過（未作答）不計入已練題數
      const answered = item.userAnswer !== null && item.userAnswer !== undefined;
      if (!answered) continue;

      attemptCount++;
      attempted.add(`${bank}|${item.qid}`);
      perBank[bank].attempted.add(item.qid);
    }
  }

  _practiceStatsCache = { attemptedCount: attempted.size, attemptCount, perBank };
  return _practiceStatsCache;
}

// 各題歷史作答統計（跳過不計）：{ total, correct, wrong }。建立一次並快取，紀錄變動時失效。
let _attemptCountMap = null;
let _practiceStatsCache = null;

function invalidateHistoryCaches() {
  _attemptCountMap = null;
  _practiceStatsCache = null;
}

function getAttemptCountMap() {
  if (_attemptCountMap) return _attemptCountMap;
  const map = {};
  for (const session of loadLocalHistory()) {
    const sessionBank = session.bank || 'questions/questions.json';
    for (const item of session.answers || []) {
      if (item.userAnswer === null || item.userAnswer === undefined) continue;
      const bank = item.bank || sessionBank;
      const key = `${bank}|${item.qid}`;
      const e = map[key] || (map[key] = { total: 0, correct: 0, wrong: 0 });
      e.total++;
      if (item.correct) e.correct++; else e.wrong++;
    }
  }
  _attemptCountMap = map;
  return map;
}

function getQuestionStats(bank, qid) {
  return getAttemptCountMap()[`${bank}|${qid}`] || { total: 0, correct: 0, wrong: 0 };
}

function getQuestionAttemptCount(bank, qid) {
  return getQuestionStats(bank, qid).total;
}

// 單題作答標籤：作答次數 + 對/錯；答 2 次以上且正確率 < 50% 標為「常錯」
function questionAttemptLabel(bank, qid) {
  const s = getQuestionStats(bank, qid);
  if (!s.total) return '✍️ 尚未作答';
  const often = s.total >= 2 && s.correct / s.total < 0.5;
  return `✍️ 作答 ${s.total} 次 · 對 ${s.correct}／錯 ${s.wrong}${often ? ' · 🔴 常錯' : ''}`;
}

// 單題統計是否通過門檻（口徑同上方標籤：跳過不計、歷史累計，後來答對過仍計入錯誤次數）。
//   minWrong   累計答錯次數下限（0 表示不限）
//   maxAccPct  正確率須「低於」此百分比；null 表示不限（沒作答過的題視為不限定正確率）
function matchesStatFilter(s, minWrong, maxAccPct) {
  if (!s || s.wrong < minWrong) return false;
  if (maxAccPct !== null && s.total > 0 && (s.correct / s.total) * 100 >= maxAccPct) return false;
  return true;
}

// 依作答統計挑題：只回傳目前分流內、作答過且通過門檻的題目，
// 依錯誤次數多→少排序，元素為 { bank, qid, stats }。
function getStatFilteredItems(minWrong, maxAccPct = null) {
  const items = [];
  for (const [key, s] of Object.entries(getAttemptCountMap())) {
    const sep = key.indexOf('|');
    const bankFile = key.slice(0, sep);
    if (!isBankFileInActiveTrack(bankFile)) continue;
    if (!matchesStatFilter(s, minWrong, maxAccPct)) continue;
    items.push({ bank: bankFile, qid: parseInt(key.slice(sep + 1), 10), stats: s });
  }
  return items.sort((a, b) => b.stats.wrong - a.stats.wrong || a.bank.localeCompare(b.bank) || a.qid - b.qid);
}

// 統計篩選的門檻輸入框共用解析（錯題本/瀏覽頁/首頁皆用同一組規則）：
// minWrong 空值或非法視為 0；maxAccPct 空值視為不限（null），限制在 1~100。
function parseStatFilterInputs(minWrongRaw, maxAccRaw) {
  const mw = parseInt(minWrongRaw, 10);
  const acc = parseInt(maxAccRaw, 10);
  return {
    minWrong: Number.isFinite(mw) && mw > 0 ? mw : 0,
    maxAccPct: Number.isFinite(acc) ? Math.min(Math.max(acc, 1), 100) : null,
  };
}

/* ===== 進度備份（匯出/還原所有本機資料） ===== */
// 要備份的固定鍵與前綴：歷程、題目標記/筆記、選取類別、主題、法條備註
const BACKUP_KEYS = ['quiz_history', 'quiz_question_metadata', 'quiz_selected_track', 'exam_bank_theme'];
const BACKUP_PREFIXES = ['law_notes:v1:'];

function isBackupKey(key) {
  return BACKUP_KEYS.includes(key) || BACKUP_PREFIXES.some(p => key.startsWith(p));
}

function collectBackupData() {
  const data = {};
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && isBackupKey(key)) data[key] = localStorage.getItem(key);
  }
  return data;
}

function exportAllProgress() {
  const payload = {
    app: 'exam-bank-lab',
    type: 'progress-backup',
    version: 1,
    exportedAt: new Date().toISOString(),
    data: collectBackupData(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  link.download = `exam-bank-progress-${stamp}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// 以備份檔還原（覆蓋同名鍵）。回傳成功寫入的鍵數。
async function importAllProgress(file) {
  const payload = JSON.parse(await file.text());
  const data = payload && payload.data ? payload.data : payload;
  if (!data || typeof data !== 'object') throw new Error('invalid backup');
  let count = 0;
  Object.entries(data).forEach(([key, value]) => {
    if (!isBackupKey(key)) return;
    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
    count++;
  });
  invalidateHistoryCaches();
  return count;
}

/* ===== Persona / Track Selection Utilities ===== */
const TRACKS = {
  irrigation: {
    name: '農田水利招考',
    sources: ['農田水利', '農田水利署', '統測專二', '統測農概']
  },
  traffic: {
    name: '交通部考驗員',
    sources: ['交通部']
  }
};

function getSelectedTrack() {
  try {
    return localStorage.getItem('quiz_selected_track') || '';
  } catch {
    return '';
  }
}

function setSelectedTrack(track) {
  try {
    localStorage.setItem('quiz_selected_track', track);
    // Clear the active quiz session to avoid cross-contamination of questions
    localStorage.removeItem('quiz_session');
  } catch {}
  // 練習統計依分流過濾，分流變動後必須重算
  invalidateHistoryCaches();
}

function isBankFileInActiveTrack(file) {
  const track = getSelectedTrack();
  if (!track) return true; // Default to allow all if none selected
  // 優先用 banks.json 的 source 欄位（registerBankIndex 填入）；索引尚未載入時退回檔名判斷
  const isTrafficFile = _bankTrackMap && file in _bankTrackMap
    ? _bankTrackMap[file]
    : !!(file && file.includes('交通部'));
  return track === 'traffic' ? isTrafficFile : !isTrafficFile;
}

function isBankInActiveTrack(bank) {
  const track = getSelectedTrack();
  if (!track) return true;
  const isTraffic = TRACKS.traffic.sources.includes(bank.source || '') || (bank.file && bank.file.includes('交通部'));
  return track === 'traffic' ? isTraffic : !isTraffic;
}

function isSessionInActiveTrack(session) {
  const sessionBank = (session.answers && session.answers[0] && session.answers[0].bank) ||
                      (session.questions && session.questions[0] && session.questions[0]._bank) ||
                      session.bank || '';
  return isBankFileInActiveTrack(sessionBank);
}

// 需要「限定來源題庫」面板的測驗模式（index.html 的面板與 doStart 共用）
const SCOPE_MODES = ['wrong', 'still-wrong', 'key', 'stat'];

// 題庫歸屬的系列（題庫書架的分類卡片）。交通部分流依科目關鍵字分三類。
function bankCollection(bank) {
  const track = getSelectedTrack();
  if (track === 'traffic') {
    const sub = bank.subject || '';
    const name = bank.name || '';
    if (sub.includes('構造') || name.includes('構造')) return 'traffic-structure';
    if (sub.includes('駕駛') || name.includes('駕駛')) return 'traffic-theory';
    if (sub.includes('法規') || name.includes('法規')) return 'traffic-law';
    return 'traffic-law';
  } else {
    return bank.source === '統測專二' ? 'tve-business' : 'irrigation';
  }
}

// 系列 id -> 顯示名稱。COLLECTIONS 由 index/browse 各自定義（兩頁文案不同）。
function collectionLabel(id) {
  return (typeof COLLECTIONS !== 'undefined' && COLLECTIONS.find(item => item.id === id)?.title) || id;
}

function bankMeta(bank) {
  return [bank.source, bank.category, bank.originalSubject && bank.originalSubject !== bank.subject ? bank.originalSubject : '']
    .filter(Boolean)
    .join(' / ');
}

/* ===== Overrides API ===== */
let _overridesData = null;
async function initOverrides() {
  if (!_overridesData) {
    try {
      _overridesData = await fetchJson('data/overrides.json');
    } catch (e) {
      console.error('Failed to load overrides.json', e);
      _overridesData = {};
    }
  }
  return _overridesData;
}

function applyQuestionOverrides(q) {
  if (!_overridesData || !q || !q._bank) return;
  const fileKey = q._bank;
  const qidKey = String(q.id);
  const bankOverrides = _overridesData[fileKey];
  if (bankOverrides && bankOverrides[qidKey]) {
    const patch = bankOverrides[qidKey];
    if (patch.answer !== undefined) {
      q.answer = patch.answer;
    }
    if (patch.warning) {
      q._warning = patch.warning;
    }
    if (patch.amendmentUrl) {
      q._amendmentUrl = patch.amendmentUrl;
    }
    if (patch.repeats) {
      q._repeats = patch.repeats;
    }
    if (patch.freeScore !== undefined) {
      q.freeScore = patch.freeScore;
    }
  }
}

function getBankWarningCount(file) {
  if (!_overridesData) return 0;
  const bankOverrides = _overridesData[file];
  if (!bankOverrides) return 0;
  let count = 0;
  for (const qid in bankOverrides) {
    if (bankOverrides[qid].warning) {
      count++;
    }
  }
  return count;
}


/* ===== Question Metadata / Tagging & Notes Storage API ===== */
const METADATA_KEY = 'quiz_question_metadata';

function getQuestionMetadata(bank, qid) {
  try {
    const raw = localStorage.getItem(METADATA_KEY);
    const data = raw ? JSON.parse(raw) : {};
    const key = `${bank}::${qid}`;
    return data[key] || { tag: '', notes: '' };
  } catch {
    return { tag: '', notes: '' };
  }
}

function saveQuestionMetadata(bank, qid, meta) {
  try {
    const raw = localStorage.getItem(METADATA_KEY);
    const data = raw ? JSON.parse(raw) : {};
    const key = `${bank}::${qid}`;
    if (!meta.tag && !meta.notes) {
      delete data[key];
    } else {
      data[key] = { tag: meta.tag || '', notes: meta.notes || '' };
    }
    localStorage.setItem(METADATA_KEY, JSON.stringify(data));
  } catch (e) {
    console.error('Failed to save question metadata', e);
  }
}

function getQuestionsWithTag(tag) {
  try {
    const raw = localStorage.getItem(METADATA_KEY);
    const data = raw ? JSON.parse(raw) : {};
    const result = [];
    for (const [key, val] of Object.entries(data)) {
      if (val.tag === tag) {
        const idx = key.indexOf('::');
        if (idx === -1) continue;
        const bank = key.substring(0, idx);
        const qid = parseInt(key.substring(idx + 2), 10);
        result.push({ bank, qid, notes: val.notes });
      }
    }
    return result;
  } catch {
    return [];
  }
}

function toggleQuestionTag(bank, qid, tag, btn) {
  const meta = getQuestionMetadata(bank, qid);
  const newTag = meta.tag === tag ? '' : tag;
  meta.tag = newTag;
  saveQuestionMetadata(bank, qid, meta);
  
  const container = btn.closest('.q-meta-panel');
  if (container) {
    container.querySelectorAll('.tag-pill').forEach(b => b.classList.remove('active'));
    if (newTag) {
      const activeBtn = container.querySelector(`.tag-${newTag}`);
      if (activeBtn) activeBtn.classList.add('active');
    }
  }
  showToast(newTag ? `已標記為${newTag === 'key' ? '重點題' : '排除題'}` : '已取消標記');
}

function saveQuestionNotes(bank, qid, notes, el) {
  const meta = getQuestionMetadata(bank, qid);
  meta.notes = notes;
  saveQuestionMetadata(bank, qid, meta);
  if (el) {
    const container = el.closest('.q-meta-panel');
    if (container) {
      const btn = container.querySelector('.tag-notes-toggle');
      if (btn) btn.classList.toggle('has-notes', !!notes);
    }
  }
}

function toggleNotesCollapse(btn) {
  const container = btn.closest('.q-meta-panel');
  const wrapper = container.querySelector('.q-meta-notes-wrapper');
  if (wrapper) {
    const isCollapsed = wrapper.style.display === 'none';
    wrapper.style.display = isCollapsed ? 'block' : 'none';
    btn.classList.toggle('active', isCollapsed);
    if (isCollapsed) {
      const textarea = wrapper.querySelector('.q-notes-input');
      if (textarea) textarea.focus();
    }
  }
}

// ---- PWA:註冊 Service Worker(sw.js),並請它把題庫補進離線快取 ----
(function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('sw.js');
      // 每個瀏覽階段只請 SW 同步一次題庫快取(只補缺的檔,流量很小)
      if (!sessionStorage.getItem('sw_banks_synced')) {
        sessionStorage.setItem('sw_banks_synced', '1');
        const sw = reg.active || reg.waiting || reg.installing;
        if (sw) sw.postMessage({ type: 'SYNC_BANKS' });
      }
    } catch (e) {
      console.warn('Service worker registration failed', e);
    }
  });
})();
