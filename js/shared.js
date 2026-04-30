const LETTERS = ['A', 'B', 'C', 'D'];

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
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

function buildPrompt(q, userAns) {
  const userLetter = userAns !== undefined && userAns !== null ? LETTERS[userAns] : '未作答';
  const correctLetter = LETTERS[q.answer];
  let t = '';
  t += `請說明這題為什麼正確答案是 ${correctLetter}，並分析我選的答案 ${userLetter}。\n`;
  t += `請用簡潔、易懂的方式說明，先講解題意，再比較各選項，最後指出判斷關鍵。\n\n`;
  t += `題目：${q.question}\n`;
  q.options.forEach((opt, i) => {
    t += `(${LETTERS[i]}) ${opt}\n`;
  });
  t += `\n我的答案：${userLetter}\n正確答案：${correctLetter}\n`;
  return t;
}

function buildBrowsePrompt(q) {
  const correctLetter = LETTERS[q.answer];
  let t = '';
  t += `請說明這題為什麼正確答案是 ${correctLetter}。\n`;
  t += `請用簡潔、易懂的方式說明，先講解題意，再比較各選項，最後指出判斷關鍵。\n\n`;
  t += `題目：${q.question}\n`;
  q.options.forEach((opt, i) => {
    t += `(${LETTERS[i]}) ${opt}\n`;
  });
  t += `\n正確答案：${correctLetter}\n`;
  return t;
}

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
    badgeText = isSkipped ? '未作答' : (isCorrect ? '答對' : '答錯');
  }

  const optsHtml = q.options.map((opt, oi) => {
    let c = '';
    let suffix = '';
    if (oi === q.answer) {
      c = 'opt-correct';
      suffix = ' 正確答案';
    }
    if (isResult && userAns === oi && !isCorrect) {
      c = 'opt-wrong';
      suffix = ' 你的答案';
    }
    return `<div class="${c}">(${LETTERS[oi]}) ${esc(opt)}${suffix}</div>`;
  }).join('');

  const copyFn = isResult ? `copyReview(${idx})` : `copyBrowse(${idx})`;
  const copyLabel = '複製解析提示';

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span style="font-weight:700;color:var(--text-dim)">第 ${idx + 1} 題</span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
    <div class="ri-q">${esc(q.question)}</div>
    <div class="ri-opts">${optsHtml}</div>
    <button class="copy-btn" id="cpbtn-${idx}" onclick="${copyFn}">${copyLabel}</button>
  </div>`;
}

function navigateTo(page) {
  window.location.href = page;
}

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
