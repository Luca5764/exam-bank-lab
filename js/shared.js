const LETTERS = ['A', 'B', 'C', 'D'];

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
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

function buildPrompt(q, userAns) {
  const userLetter = userAns !== undefined && userAns !== null ? LETTERS[userAns] : '未作答';
  const correctLetter = q.freeScore ? '送分' : (LETTERS[q.answer] || '未設定');
  const materialsText = buildMaterialText(q.materials);
  let t = '';
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

function buildBrowsePrompt(q) {
  const correctLetter = q.freeScore ? '送分' : (LETTERS[q.answer] || '未設定');
  const materialsText = buildMaterialText(q.materials);
  let t = '';
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
  const { idx, userAns, mode } = opts;
  const isResult = mode === 'result';
  const isFreeScore = !!q.freeScore;
  const isSkipped = isResult && (userAns === undefined || userAns === null);
  const isCorrect = isResult && (isFreeScore ? !isSkipped : userAns === q.answer);
  const isWrong = isResult && !isCorrect;

  let cls = 'ri-neutral';
  let badgeCls = 'badge-neutral';
  let badgeText = isFreeScore ? '送分' : '';

  if (isResult) {
    cls = isWrong ? 'ri-wrong' : 'ri-correct';
    badgeCls = isWrong ? 'badge-wrong' : 'badge-correct';
    badgeText = isSkipped ? '未作答' : (isFreeScore ? '送分' : (isCorrect ? '答對' : '答錯'));
  }

  const optsHtml = q.options.map((opt, oi) => {
    let c = '';
    if (!isFreeScore && oi === q.answer) {
      c = 'opt-correct';
    }
    if (isResult && userAns === oi && !isCorrect) {
      c = 'opt-wrong';
    }
    return `<div class="${c}">(${LETTERS[oi]}) ${esc(opt)}</div>`;
  }).join('');

  const copyFn = isResult ? `copyReview(${idx})` : `copyBrowse(${idx})`;
  const copyLabel = '複製解析提示';

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span style="font-weight:700;color:var(--text-dim)">第 ${idx + 1} 題</span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
    <div class="ri-q">${esc(q.question)}</div>
    ${renderMaterialsHTML(q.materials)}
    <div class="ri-opts">${optsHtml}</div>
    <button class="copy-btn" id="cpbtn-${idx}" onclick="${copyFn}">${copyLabel}</button>
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
  const res = await fetch(toAssetUrl(path), { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status}`);
  }
  return res.json();
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
}

function deleteLocalHistory(idx) {
  const history = loadLocalHistory();
  if (idx >= 0 && idx < history.length) {
    history.splice(idx, 1);
    localStorage.setItem(DB_KEY, JSON.stringify(history));
  }
}

function clearLocalHistory() {
  localStorage.setItem(DB_KEY, JSON.stringify([]));
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
      const qid = item.qid;
      const bank = item.bank || sessionBank;
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
