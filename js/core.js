// 基礎工具：跳脫、主題、提示、剪貼簿、資料讀取、本機儲存、Service Worker。
// 所有頁面都先載入這支，其餘 js/*.js 依賴這裡的函式。

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

// 提示詞開頭的共用提醒：請 AI 先查最新資料再回答（適用所有科目，非僅法規）。
const SEARCH_HINT = '請先上網搜尋最新的相關資訊，確認內容仍為正確且現行有效後再回答。';

// 複製多題提示詞時的分隔線
const PROMPT_SEPARATOR = '\n' + '='.repeat(50) + '\n';

// HTML 跳脫（文字節點與屬性值皆可用）
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 把值安全地塞進 HTML 屬性裡的 inline handler 參數（onclick="fn(${jsArg(v)})"）
function jsArg(value) {
  return JSON.stringify(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

function navigateTo(page) {
  window.location.href = page;
}

/* ===== 本機儲存（localStorage 可能被停用或滿了，一律包 try/catch） ===== */
function readStorageJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    console.error(`Failed to read ${key} from localStorage`, e);
    return fallback;
  }
}

function writeStorageJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (e) {
    console.error(`Failed to write ${key} to localStorage`, e);
    return false;
  }
}

/* ===== 深淺色主題 ===== */
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

function onDomReady(fn) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn);
  } else {
    fn();
  }
}

applyTheme(getPreferredTheme());
onDomReady(installThemeToggle);

/* ===== Toast 與剪貼簿 ===== */
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

/* ===== 資料讀取 ===== */
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

// ---- PWA：註冊 Service Worker（sw.js），並請它把題庫補進離線快取 ----
(function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('sw.js');
      // 每個瀏覽階段只請 SW 同步一次題庫快取（只補缺的檔，流量很小）
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
