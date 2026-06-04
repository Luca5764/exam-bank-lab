const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

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
  let userLetter;
  if (isMultiAnswer(q)) {
    userLetter = Array.isArray(userAns) && userAns.length > 0 ? formatAnswerLetters(userAns) : '未作答';
  } else {
    userLetter = userAns !== undefined && userAns !== null ? LETTERS[userAns] : '未作答';
  }
  const correctLetter = q.freeScore ? '送分' : formatAnswerLetters(q.answer);
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
  const correctLetter = q.freeScore ? '送分' : formatAnswerLetters(q.answer);
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
  applyQuestionOverrides(q);
  const { idx, userAns, mode } = opts;
  const isResult = mode === 'result';
  const isFreeScore = !!q.freeScore;
  const multi = isMultiAnswer(q);

  let isSkipped, isCorrect;
  if (multi) {
    isSkipped = isResult && (!Array.isArray(userAns) || userAns.length === 0);
    isCorrect = isResult && (isFreeScore ? !isSkipped : multiAnswerCorrect(userAns, q.answer));
  } else {
    isSkipped = isResult && (userAns === undefined || userAns === null);
    isCorrect = isResult && (isFreeScore ? !isSkipped : userAns === q.answer);
  }
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
    ? `<span class="repeat-badge" style="margin-left:8px" title="重複考過年份：${q._repeats.join('、')}">🔄 重複 ${q._repeats.length} 次</span>`
    : '';
  const warningHtml = q._warning
    ? `<div class="amendment-warning">${esc(q._warning)}</div>`
    : '';

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span style="font-weight:700;color:var(--text-dim)">第 ${idx + 1} 題 ${repeatsHtml}</span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
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

/* ===== Persona / Track Selection Utilities ===== */
const TRACKS = {
  irrigation: {
    name: '農田水利招考',
    sources: ['農田水利', '農田水利署', '統測專二', '統測農概']
  },
  traffic: {
    name: '交通部檢考驗員',
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
}

function isBankFileInActiveTrack(file) {
  const track = getSelectedTrack();
  if (!track) return true; // Default to allow all if none selected
  const isTrafficFile = file && file.includes('交通部');
  return track === 'traffic' ? isTrafficFile : !isTrafficFile;
}

function isBankInActiveTrack(bank) {
  const track = getSelectedTrack();
  if (!track) return true;
  const isTraffic = (bank.source === '交通部') || (bank.file && bank.file.includes('交通部'));
  return track === 'traffic' ? isTraffic : !isTraffic;
}

function isSessionInActiveTrack(session) {
  const sessionBank = (session.answers && session.answers[0] && session.answers[0].bank) ||
                      (session.questions && session.questions[0] && session.questions[0]._bank) ||
                      session.bank || '';
  return isBankFileInActiveTrack(sessionBank);
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
