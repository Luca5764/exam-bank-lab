// 使用者進度：作答歷程、錯題、練習統計、題目標記/筆記、進度備份。
// 全部存在 localStorage。依賴 core.js、tracks.js。

const DB_KEY = 'quiz_history';
const METADATA_KEY = 'quiz_question_metadata';
const LEGACY_BANK = 'questions/questions.json';

/* ===== 作答歷程 ===== */
// 解析結果快取：同一頁會多次讀歷程（錯題、統計、作答次數），不必每次重新 JSON.parse
let _historyCache = null;
let _attemptCountMap = null;
let _practiceStatsCache = null;

function invalidateHistoryCaches() {
  _historyCache = null;
  _attemptCountMap = null;
  _practiceStatsCache = null;
}

// 其他分頁改了紀錄時同步失效
window.addEventListener('storage', e => {
  if (e.key === DB_KEY || e.key === null) invalidateHistoryCaches();
  if (e.key === METADATA_KEY || e.key === null) _metadataCache = null;
});

function loadLocalHistory() {
  if (!_historyCache) {
    const data = readStorageJson(DB_KEY, []);
    _historyCache = Array.isArray(data) ? data : [];
  }
  return _historyCache;
}

function writeLocalHistory(history) {
  writeStorageJson(DB_KEY, history);
  invalidateHistoryCaches();
}

function saveLocalHistory(record) {
  writeLocalHistory([...loadLocalHistory(), record]);
}

function deleteLocalHistory(idx) {
  const history = loadLocalHistory().slice();
  if (idx >= 0 && idx < history.length) {
    history.splice(idx, 1);
    writeLocalHistory(history);
  }
}

function clearLocalHistory() {
  writeLocalHistory([]);
}

function isAnswered(userAnswer) {
  return Array.isArray(userAnswer) ? userAnswer.length > 0 : userAnswer !== null && userAnswer !== undefined;
}

// 逐筆走訪歷程中的作答：fn(item, bankFile, session)。
// 題庫的推導（item.bank 優先，退回 session.bank 與舊版預設）全站必須一致。
function forEachHistoryAnswer(fn) {
  for (const session of loadLocalHistory()) {
    const sessionBank = session.bank || LEGACY_BANK;
    for (const item of session.answers || []) {
      fn(item, item.bank || sessionBank, session);
    }
  }
}

function isSessionInActiveTrack(session) {
  const sessionBank = (session.answers && session.answers[0] && session.answers[0].bank) ||
    (session.questions && session.questions[0] && session.questions[0]._bank) ||
    session.bank || '';
  return isBankFileInActiveTrack(sessionBank);
}

function itemKey(bank, qid) {
  return `${bank}|${qid}`;
}

function parseItemKey(key) {
  const sep = key.lastIndexOf('|');
  return { bank: key.slice(0, sep), qid: parseInt(key.slice(sep + 1), 10) };
}

function sortItems(items) {
  return items.sort((a, b) => a.bank.localeCompare(b.bank) || a.qid - b.qid);
}

// 本地日期（YYYY-M-D）。不可用 toISOString()：那是 UTC，台灣早上 8 點前會算成前一天
function localDateKey(date) {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

// 錯題池（只計目前分流）：
//   ever_wrong 曾錯過、still_wrong 最後一次仍錯、today_wrong 今天錯的、past_wrong 今天以前錯的
function getWrongPool() {
  const today = localDateKey(new Date());
  const lastResult = {};
  const everWrong = new Set();
  const todayWrong = new Set();

  forEachHistoryAnswer((item, bank, session) => {
    if (!isBankFileInActiveTrack(bank)) return;
    const key = itemKey(bank, item.qid);
    lastResult[key] = item.correct;
    if (!item.correct) {
      everWrong.add(key);
      if (session.date_iso && localDateKey(new Date(session.date_iso)) === today) todayWrong.add(key);
    }
  });

  const toList = keys => sortItems(keys.map(parseItemKey));
  return {
    ever_wrong: toList([...everWrong]),
    still_wrong: toList(Object.keys(lastResult).filter(key => !lastResult[key])),
    today_wrong: toList([...todayWrong]),
    past_wrong: toList([...everWrong].filter(key => !todayWrong.has(key))),
  };
}

// 將 ISO 時間轉成 M/D（本地時區）；無效時回空字串
function formatMonthDay(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// 練習統計（僅計目前分流）：
//   attemptedCount 不重複已作答題數（跳過不算、重複不加）
//   attemptCount   累計作答次數（含重複，跳過不算）
//   perBank        每個題庫的 { lastIso 最後練習時間, attempted 已練過的題號集合 }
// 結果會快取（搜尋框每個按鍵都會重繪題庫清單，不能每次全掃歷程）。
function getPracticeStats() {
  if (_practiceStatsCache) return _practiceStatsCache;
  const attempted = new Set();
  let attemptCount = 0;
  const perBank = {};

  forEachHistoryAnswer((item, bank, session) => {
    if (!isBankFileInActiveTrack(bank)) return;
    const iso = session.date_iso || '';
    // 該題庫只要出現在這次測驗就算「練習過」一次（用於最後練習日期）
    const pb = perBank[bank] || (perBank[bank] = { lastIso: '', attempted: new Set() });
    if (iso > pb.lastIso) pb.lastIso = iso;
    if (!isAnswered(item.userAnswer)) return; // 跳過不計入已練題數
    attemptCount++;
    attempted.add(itemKey(bank, item.qid));
    pb.attempted.add(item.qid);
  });

  _practiceStatsCache = { attemptedCount: attempted.size, attemptCount, perBank };
  return _practiceStatsCache;
}

// 各題歷史作答統計（跳過不計，不分分流）：{ total, correct, wrong }
function getAttemptCountMap() {
  if (_attemptCountMap) return _attemptCountMap;
  const map = {};
  forEachHistoryAnswer((item, bank) => {
    if (!isAnswered(item.userAnswer)) return;
    const key = itemKey(bank, item.qid);
    const e = map[key] || (map[key] = { total: 0, correct: 0, wrong: 0 });
    e.total++;
    if (item.correct) e.correct++; else e.wrong++;
  });
  _attemptCountMap = map;
  return map;
}

function getQuestionStats(bank, qid) {
  return getAttemptCountMap()[itemKey(bank, qid)] || { total: 0, correct: 0, wrong: 0 };
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
    const { bank, qid } = parseItemKey(key);
    if (!isBankFileInActiveTrack(bank)) continue;
    if (!matchesStatFilter(s, minWrong, maxAccPct)) continue;
    items.push({ bank, qid, stats: s });
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

// [{ bank, qid }] → { bankFile: Set(qid) }，用來只撈指定題號
function groupItemsByBank(items) {
  const byBank = {};
  for (const { bank, qid } of items) (byBank[bank] = byBank[bank] || new Set()).add(qid);
  return byBank;
}

/* ===== 題目標記（重點/排除）與筆記 ===== */
let _metadataCache = null;

function loadAllMetadata() {
  if (!_metadataCache) {
    const data = readStorageJson(METADATA_KEY, {});
    _metadataCache = data && typeof data === 'object' ? data : {};
  }
  return _metadataCache;
}

function metadataKey(bank, qid) {
  return `${bank}::${qid}`;
}

function getQuestionMetadata(bank, qid) {
  const meta = loadAllMetadata()[metadataKey(bank, qid)];
  return meta ? { tag: meta.tag || '', notes: meta.notes || '' } : { tag: '', notes: '' };
}

function saveQuestionMetadata(bank, qid, meta) {
  const data = { ...loadAllMetadata() };
  const key = metadataKey(bank, qid);
  if (!meta.tag && !meta.notes) {
    delete data[key];
  } else {
    data[key] = { tag: meta.tag || '', notes: meta.notes || '' };
  }
  writeStorageJson(METADATA_KEY, data);
  _metadataCache = data;
}

function getQuestionsWithTag(tag) {
  const result = [];
  for (const [key, val] of Object.entries(loadAllMetadata())) {
    if (!val || val.tag !== tag) continue;
    const idx = key.indexOf('::');
    if (idx === -1) continue;
    result.push({ bank: key.substring(0, idx), qid: parseInt(key.substring(idx + 2), 10), notes: val.notes });
  }
  return result;
}

/* ===== 進度備份（匯出/還原所有本機資料） ===== */
// 要備份的固定鍵與前綴：歷程、題目標記/筆記、選取類別、主題、法條備註
const BACKUP_KEYS = [DB_KEY, METADATA_KEY, 'quiz_selected_track', 'exam_bank_theme'];
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
  // 立即 revoke 在部分瀏覽器（Safari）會讓下載失敗
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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
  _metadataCache = null;
  return count;
}
