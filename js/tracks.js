// 考試類別（分流）與題庫索引。
// 新增考試類別只要在 TRACKS 加一筆設定：首頁選單、切換列、題庫書架分類、
// 錯題/統計的分流過濾都會自動套用。依賴 core.js。

const ALL_FILTER = '全部';

// collections：題庫書架的系列卡片；match 回傳 true 代表題庫屬於該系列，
// 省略 match 的系列是該分流的預設歸屬（每個分流恰好一個）。
// filePattern：banks.json 尚未載入時，用題庫檔名推斷分流的後備規則。
const TRACKS = [
  {
    id: 'irrigation',
    icon: '🌾',
    name: '農田水利招考',
    shortName: '農田水利',
    accent: '#2e7d32',
    sources: ['農田水利', '農田水利署', '統測專二', '統測農概'],
    subtitle: '農田水利、統測專二與更多題庫，都用同一套流程練習。',
    intro: '包含農田水利署、水利會歷屆考古題、農業概論、灌溉排水概要，以及統測專二商管群精選科目。',
    collections: [
      { id: 'irrigation', title: '農田水利招考', desc: '水利會、農田水利署與共同/專業科目' },
      { id: 'tve-business', title: '統測商管群', desc: '專二：會計學與經濟學', match: bank => bank.source === '統測專二' },
    ],
  },
  {
    id: 'traffic',
    icon: '🚗',
    name: '交通部考驗員',
    shortName: '交通部',
    accent: '#1565c0',
    sources: ['交通部'],
    filePattern: /交通部/,
    subtitle: '交通部公路局公路監理人員汽車駕駛考驗員歷年精選學科題庫。',
    intro: '包含汽車構造原理概論、汽車駕駛理論、道路交通法規等汽車駕駛考驗員檢定學科題庫。',
    collections: [
      { id: 'traffic-structure', title: '汽車構造原理', desc: '汽車構造與構造原理概論', match: bank => bankText(bank).includes('構造') },
      { id: 'traffic-theory', title: '汽車駕駛理論', desc: '駕駛理論與安全駕駛知識', match: bank => bankText(bank).includes('駕駛') },
      { id: 'traffic-law', title: '道路交通法規', desc: '交通安全法規與相關監理實務' },
    ],
  },
  {
    id: 'emt',
    icon: '🚑',
    name: '初級救護技術員',
    shortName: 'EMT-1',
    accent: '#c62828',
    sources: ['初級救護技術員'],
    filePattern: /^(?:.*\/)?EMT/i,
    subtitle: '初級救護技術員（EMT-1）初訓、複訓學科測驗題庫。',
    intro: '包含創傷評估、燒燙傷、心肺復甦術、呼吸道處置、傷病患搬運與到院前救護等 EMT-1 學科題目。',
    collections: [
      { id: 'emt-1', title: 'EMT-1 學科', desc: '初級救護技術員初訓／複訓學科測驗' },
    ],
  },
];

const DEFAULT_TRACK_ID = TRACKS[0].id;
const TRACK_KEY = 'quiz_selected_track';

function bankText(bank) {
  return `${bank.subject || ''} ${bank.name || ''}`;
}

function getTrack(id) {
  return TRACKS.find(t => t.id === id) || null;
}

function trackIdForSource(source) {
  const track = TRACKS.find(t => t.sources.includes(source || ''));
  return track ? track.id : '';
}

function trackIdForFile(file) {
  if (_bankTrackMap && file in _bankTrackMap) return _bankTrackMap[file];
  const track = TRACKS.find(t => t.filePattern && t.filePattern.test(file || ''));
  return track ? track.id : DEFAULT_TRACK_ID;
}

function bankTrackId(bank) {
  return trackIdForSource(bank.source) || trackIdForFile(bank.file);
}

/* ===== 目前選擇的分流 ===== */
function getSelectedTrack() {
  try {
    const id = localStorage.getItem(TRACK_KEY) || '';
    return getTrack(id) ? id : '';
  } catch {
    return '';
  }
}

function getActiveTrack() {
  return getTrack(getSelectedTrack()) || TRACKS[0];
}

// 切換分流。只有真的換到不同分流時才捨棄未完成的測驗，
// 避免單純開瀏覽頁（會補存預設分流）就把續作進度清掉。
function setSelectedTrack(trackId) {
  if (!getTrack(trackId)) return;
  const changed = getSelectedTrack() !== trackId;
  try {
    localStorage.setItem(TRACK_KEY, trackId);
    if (changed) localStorage.removeItem('quiz_session');
  } catch { }
  // 練習統計依分流過濾，分流變動後必須重算
  if (changed && typeof invalidateHistoryCaches === 'function') invalidateHistoryCaches();
}

function isBankFileInActiveTrack(file) {
  const track = getSelectedTrack();
  if (!track) return true; // 尚未選擇分流時不過濾
  return trackIdForFile(file) === track;
}

function isBankInActiveTrack(bank) {
  const track = getSelectedTrack();
  if (!track) return true;
  return bankTrackId(bank) === track;
}

/* ===== 題庫書架的系列 ===== */
function getTrackCollections(trackId = getSelectedTrack()) {
  const track = getTrack(trackId) || TRACKS[0];
  return [{ id: ALL_FILTER, title: '全部題庫', desc: '跨系列搜尋與混合練習' }, ...track.collections];
}

// 題庫歸屬的系列 id（依題庫本身所屬的分流判斷，不受目前選擇影響）
function bankCollection(bank) {
  const track = getTrack(bankTrackId(bank)) || TRACKS[0];
  const hit = track.collections.find(c => c.match && c.match(bank))
    || track.collections.find(c => !c.match);
  return hit.id;
}

function collectionLabel(id) {
  for (const track of TRACKS) {
    const hit = track.collections.find(c => c.id === id);
    if (hit) return hit.title;
  }
  return id;
}

/* ===== 題庫索引（data/banks.json） ===== */
// file -> 顯示名稱、file -> 分流 id
let _bankLabelMap = null;
let _bankTrackMap = null;
let _bankIndexPromise = null;

function normalizeBank(bank) {
  return {
    ...bank,
    source: bank.source || '農田水利',
    subject: bank.subject || bank.name,
  };
}

function registerBankIndex(banks) {
  _bankLabelMap = _bankLabelMap || {};
  _bankTrackMap = _bankTrackMap || {};
  (banks || []).forEach(b => {
    if (!b || !b.file) return;
    _bankLabelMap[b.file] = b.displayName || b.name || b.file;
    _bankTrackMap[b.file] = bankTrackId(b);
  });
  if (typeof invalidateHistoryCaches === 'function') invalidateHistoryCaches();
}

// 載入並登錄題庫索引，回傳正規化後的清單（同一頁只下載一次）。
// 失敗時回傳空陣列，名稱改由檔名推導。
function loadBankIndex() {
  if (!_bankIndexPromise) {
    _bankIndexPromise = fetchJson('data/banks.json')
      .then(banks => {
        const list = (Array.isArray(banks) ? banks : []).map(normalizeBank);
        registerBankIndex(list);
        return list;
      })
      .catch(e => {
        console.error('Failed to load bank index', e);
        _bankIndexPromise = null;
        return [];
      });
  }
  return _bankIndexPromise;
}

function bankLabel(bankPath) {
  if (!bankPath) return '未知來源';
  if (_bankLabelMap && _bankLabelMap[bankPath]) return _bankLabelMap[bankPath];
  // 後備：直接從檔名推導
  return bankPath.replace(/^.*\//, '').replace(/\.json$/, '');
}

function bankTitle(bank) {
  return bank.displayName || `${bank.year || ''} ${bank.subject || bank.name || ''}`.trim() || bank.file;
}

function bankMeta(bank) {
  return [bank.source, bank.category, bank.originalSubject && bank.originalSubject !== bank.subject ? bank.originalSubject : '']
    .filter(Boolean)
    .join(' / ');
}

function bankMatchesSearch(bank, query) {
  if (!query) return true;
  const haystack = [
    bank.year,
    bank.subject,
    bank.originalSubject,
    bank.source,
    collectionLabel(bankCollection(bank)),
    bank.category,
    bank.name,
    bank.displayName,
    bank.file,
  ].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function sumQuestionCount(banks) {
  return banks.reduce((sum, bank) => sum + (bank.count || 0), 0);
}

/* ===== 分流切換列與首次選擇視窗 ===== */
function trackLabelHTML(track) {
  return `<span aria-hidden="true">${track.icon}</span>`
    + `<span class="track-name-full">${esc(track.name)}</span>`
    + `<span class="track-name-short">${esc(track.shortName || track.name)}</span>`;
}

// 在 container 內畫出分流切換列；點選不同分流時呼叫 onSwitch(trackId)
function renderTrackSwitcher(container, onSwitch) {
  if (!container) return;
  container.innerHTML = `<div class="track-switcher" role="tablist">${TRACKS.map(track =>
    `<button type="button" class="track-btn" role="tab" data-track="${esc(track.id)}">${trackLabelHTML(track)}</button>`
  ).join('')}</div>`;
  container.addEventListener('click', e => {
    const btn = e.target.closest('[data-track]');
    if (!btn || btn.dataset.track === getSelectedTrack()) return;
    setSelectedTrack(btn.dataset.track);
    markActiveTrack(container);
    onSwitch(btn.dataset.track);
  });
  markActiveTrack(container);
}

function markActiveTrack(container) {
  const active = getSelectedTrack();
  container.querySelectorAll('[data-track]').forEach(btn => {
    const on = btn.dataset.track === active;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
}

// 首次造訪的全螢幕分流選擇；選定後呼叫 onSelect(trackId)
function showTrackPicker(onSelect) {
  const overlay = document.createElement('div');
  overlay.className = 'track-overlay';
  overlay.innerHTML = `
    <div class="track-modal fade-in" role="dialog" aria-modal="true" aria-labelledby="trackPickerTitle">
      <div class="track-modal-header">
        <h2 id="trackPickerTitle">歡迎來到考古題練習室</h2>
        <p>請選擇您要準備的考試類別，系統將為您切換專屬的題庫與紀錄：</p>
      </div>
      <div class="track-cards-container">
        ${TRACKS.map(track => `
          <button type="button" class="track-card" data-track="${esc(track.id)}" style="--track-accent:${esc(track.accent)}">
            <span class="track-icon" aria-hidden="true">${track.icon}</span>
            <span class="track-card-title">${esc(track.name)}</span>
            <span class="track-card-desc">${esc(track.intro)}</span>
            <span class="btn btn-primary btn-block track-card-cta">進入此練習室</span>
          </button>`).join('')}
      </div>
    </div>`;
  overlay.addEventListener('click', e => {
    const card = e.target.closest('[data-track]');
    if (!card) return;
    setSelectedTrack(card.dataset.track);
    overlay.classList.add('is-leaving');
    setTimeout(() => overlay.remove(), 300);
    onSelect(card.dataset.track);
  });
  document.body.appendChild(overlay);
}

/* ===== 題庫書架（系列卡片 + 科目篩選 + 關鍵字搜尋），首頁與瀏覽頁共用 ===== */
class BankShelf {
  // els: { search, collections, subjects }；onChange：篩選條件改變時呼叫
  // collectionStats(banks)：回傳系列卡片額外的一行 HTML（可省略）
  constructor({ els, onChange, collectionStats = null }) {
    this.els = els;
    this.onChange = onChange;
    this.collectionStats = collectionStats;
    this.banks = [];
    this.source = ALL_FILTER;
    this.subject = ALL_FILTER;

    els.collections.addEventListener('click', e => {
      const card = e.target.closest('[data-collection]');
      if (!card) return;
      this.source = card.dataset.collection;
      this.subject = ALL_FILTER;
      this.onChange();
    });
    els.subjects.addEventListener('click', e => {
      const chip = e.target.closest('[data-subject]');
      if (!chip) return;
      this.subject = chip.dataset.subject;
      this.onChange();
    });
    els.search.addEventListener('input', () => this.onChange());
  }

  reset(banks) {
    this.banks = banks;
    this.source = ALL_FILTER;
    this.subject = ALL_FILTER;
  }

  // 讓書架直接定位到某份題庫所在的系列與科目
  focus(bank) {
    this.source = bankCollection(bank);
    this.subject = bank.subject || ALL_FILTER;
  }

  inSource(bank) {
    return this.source === ALL_FILTER || bankCollection(bank) === this.source;
  }

  visibleBanks() {
    const query = this.els.search.value.trim();
    return this.banks.filter(bank =>
      this.inSource(bank) &&
      (this.subject === ALL_FILTER || bank.subject === this.subject) &&
      bankMatchesSearch(bank, query)
    );
  }

  // 只有一個選項時不必讓使用者選：連同上方的 .filter-label 一起隱藏
  static setSectionVisible(el, visible) {
    el.hidden = !visible;
    const label = el.previousElementSibling;
    if (label && label.classList.contains('filter-label')) label.hidden = !visible;
  }

  render() {
    const collections = getTrackCollections();
    BankShelf.setSectionVisible(this.els.collections, collections.length > 2);
    this.els.collections.style.setProperty('--cols', Math.min(collections.length, 4));
    this.els.collections.innerHTML = collections.map(item => {
      const banks = item.id === ALL_FILTER ? this.banks : this.banks.filter(b => bankCollection(b) === item.id);
      const extra = this.collectionStats ? this.collectionStats(banks) : '';
      return `<button type="button" class="collection-card ${item.id === this.source ? 'active' : ''}" data-collection="${esc(item.id)}">
          <span class="collection-title">${esc(item.title)}</span>
          <span class="collection-desc">${esc(item.desc)}</span>
          <span class="collection-count">${banks.length} 份 / ${sumQuestionCount(banks)} 題</span>
          ${extra}
        </button>`;
    }).join('');

    const subjects = [ALL_FILTER, ...new Set(this.banks.filter(b => this.inSource(b)).map(b => b.subject).filter(Boolean))];
    if (!subjects.includes(this.subject)) this.subject = ALL_FILTER;
    BankShelf.setSectionVisible(this.els.subjects, subjects.length > 2);
    this.els.subjects.innerHTML = subjects.map(s =>
      `<button type="button" class="filter-chip ${s === this.subject ? 'active' : ''}" data-subject="${esc(s)}">${esc(s)}</button>`
    ).join('');
  }
}

// 題庫卡片（首頁多選、瀏覽頁單選共用），點擊由頁面以 data-file 事件委派處理
function bankCardHTML(bank, { selected = false, practice = null } = {}) {
  const warnCount = typeof getBankWarningCount === 'function' ? getBankWarningCount(bank.file) : 0;
  const warningBadge = warnCount > 0 ? `<span class="bank-warning-badge">⚠️ ${warnCount} 題受修法影響</span>` : '';
  let practiceLine = '';
  if (practice !== null) {
    const pb = practice.perBank[bank.file];
    practiceLine = `<span class="bank-practice ${pb ? '' : 'is-fresh'}">${pb
      ? `🕒 最後練習 ${formatMonthDay(pb.lastIso)} · 已練 ${pb.attempted.size}/${bank.count}`
      : '尚未練習'}</span>`;
  }
  return `<button type="button" class="bank-card ${selected ? 'selected' : ''}" data-file="${esc(bank.file)}" aria-pressed="${selected}">
      <span class="bank-check">${selected ? '✓' : ''}</span>
      <span class="bank-main">
        <span class="bank-title">${esc(bankTitle(bank))}</span>
        <span class="bank-meta">${esc(bankMeta(bank))}</span>
        ${practiceLine}
        <span class="bank-tags">
          <span class="bank-series">${esc(collectionLabel(bankCollection(bank)))}</span>
          <span class="bank-count">${bank.count} 題</span>
          ${warningBadge}
        </span>
      </span>
    </button>`;
}
