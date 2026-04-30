// ===== shared.js ???梁撌亙 =====

const LETTERS = ['A', 'B', 'C', 'D'];

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ===== Toast =====
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

// ===== Clipboard with feedback =====
async function copyText(text, btnEl) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // fallback
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
    btnEl.innerHTML = '??撌脰?鋆踝?';
    btnEl.classList.add('copied');
    setTimeout(() => { btnEl.innerHTML = orig; btnEl.classList.remove('copied'); }, 2000);
  }
  showToast('??撌脰?鋆賢?芾票蝪?);
}

// ===== Build AI prompt for a question =====
function buildPrompt(q, userAns) {
  const userLetter = (userAns !== undefined && userAns !== null) ? LETTERS[userAns] : '?芯?蝑?;
  const correctLetter = LETTERS[q.answer];
  let t = '';
  t += `隞乩??臭??噙?唳偌?拇?閬???嚗蝙?刻鈭?${userLetter}嚗迤蝣箇?獢 ${correctLetter}?n`;
  t += `隢?質店??瘛粹＊???撘?閫?????箔?暻潛?獢 ${correctLetter}嚗蒂???嫣噶閮?見蝡???見?n\n`;
  t += `???柴?{q.question}\n`;
  q.options.forEach((opt, i) => { t += `(${LETTERS[i]}) ${opt}\n`; });
  t += `\n雿輻?嚗?{userLetter}\n甇?Ⅱ蝑?嚗?{correctLetter}\n`;
  return t;
}

// Browse-only prompt (no user answer)
function buildBrowsePrompt(q) {
  const correctLetter = LETTERS[q.answer];
  let t = '';
  t += `隞乩??臭??噙?唳偌?拇?閬???嚗迤蝣箇?獢 ${correctLetter}?n`;
  t += `隢?質店??瘛粹＊???撘?閫???箔?暻潛?獢 ${correctLetter}嚗蒂???嫣噶閮?見蝡???見?n\n`;
  t += `???柴?{q.question}\n`;
  q.options.forEach((opt, i) => { t += `(${LETTERS[i]}) ${opt}\n`; });
  t += `\n甇?Ⅱ蝑?嚗?{correctLetter}\n`;
  return t;
}

// ===== Build review item HTML =====
// mode: 'result' (with user answer), 'browse' (just show question+answer), 'wrong-pool' (show question+correct)
function buildReviewItemHTML(q, opts) {
  const { idx, userAns, mode } = opts;
  const isResult = mode === 'result';
  const isCorrect = isResult && userAns === q.answer;
  const isSkipped = isResult && (userAns === undefined || userAns === null);
  const isWrong = isResult && !isCorrect;

  let cls = 'ri-neutral';
  let badgeCls = 'badge-neutral';
  let badgeText = '';
  if (isResult) {
    cls = isWrong ? 'ri-wrong' : 'ri-correct';
    badgeCls = isWrong ? 'badge-wrong' : 'badge-correct';
    badgeText = isSkipped ? '?芯?蝑? : (isCorrect ? '甇?Ⅱ' : '?航炊');
  }

  const optsHtml = q.options.map((opt, oi) => {
    let c = '';
    let suffix = '';
    if (oi === q.answer) { c = 'opt-correct'; suffix = ' ??; }
    if (isResult && userAns === oi && !isCorrect) { c = 'opt-wrong'; suffix = ' ??雿??豢?嚗?; }
    return `<div class="${c}">(${LETTERS[oi]}) ${esc(opt)}${suffix}</div>`;
  }).join('');

  const copyFn = isResult ? `copyReview(${idx})` : `copyBrowse(${idx})`;
  const copyLabel = '?? 銴ˊ甇日?嚗?內閰?';

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span style="font-weight:700;color:var(--text-dim)">蝚?${idx + 1} 憿?/span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
    <div class="ri-q">${esc(q.question)}</div>
    <div class="ri-opts">${optsHtml}</div>
    <button class="copy-btn" id="cpbtn-${idx}" onclick="${copyFn}">${copyLabel}</button>
  </div>`;
}

// ===== Navigation =====
function navigateTo(page) {
  window.location.href = page;
}


// ===== LocalStorage Data Access (Static Site replacement for /api/...) =====
const DB_KEY = 'quiz_history';

function toAssetUrl(path) {
  return new URL(encodeURI(path), document.baseURI).toString();
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
    console.error("Failed to load history from localStorage", e);
    return [];
  }
}

function saveLocalHistory(record) {
  const history = loadLocalHistory();
  history.push(record);
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(history));
  } catch (e) {
    console.error("Failed to save history to localStorage", e);
    // If quota exceeded, we might want to prune old records
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
  const last_result = {};
  const ever_wrong = new Set();
  const today_wrong = new Set();
  
  for (const session of history) {
    const sess_bank = session.bank || "questions/questions.json";
    for (const item of session.answers || []) {
      const qid = item.qid;
      const b = item.bank || sess_bank;
      const key = `${b}|${qid}`;
      const ok = item.correct;
      last_result[key] = ok;
      if (!ok) {
        ever_wrong.add(key);
        if (session.date_iso && session.date_iso.split('T')[0] === today) {
          today_wrong.add(key);
        }
      }
    }
  }
  
  const still_wrong = Object.keys(last_result).filter(k => !last_result[k]);
  const past_wrong = [...ever_wrong].filter(k => !today_wrong.has(k));
  
  const to_list = (keys) => keys.map(k => {
    const parts = k.split('|');
    const bank = parts[0];
    const qid = parts[1];
    return { bank, qid: parseInt(qid) };
  }).sort((a, b) => a.bank.localeCompare(b.bank) || a.qid - b.qid);
  
  return {
    ever_wrong: to_list([...ever_wrong]),
    still_wrong: to_list(still_wrong),
    today_wrong: to_list([...today_wrong]),
    past_wrong: to_list(past_wrong),
  };
}

