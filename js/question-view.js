// 題目呈現：判分、附圖/表格、AI 解析提示詞、修法覆寫、題目標記面板、
// 交卷/瀏覽用的題目卡片、來源題庫勾選面板。依賴 core.js、tracks.js、progress.js。

/* ===== 判分 ===== */
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
  const answered = multi ? (Array.isArray(ua) && ua.length > 0) : isAnswered(ua);
  const ok = answered && (q.freeScore ? true : (multi ? multiAnswerCorrect(ua, q.answer) : ua === q.answer));
  return { answered, ok };
}

// 題型：tf 是非題（O/X 兩個短選項）、sc 單選題、mc 複選題
function questionType(q) {
  if (isMultiAnswer(q)) return 'mc';
  const isTrueFalse = q.options.length === 2 && q.options.every(o => String(o).trim().length <= 2);
  return isTrueFalse ? 'tf' : 'sc';
}

function formatAnswerLetters(ans) {
  if (Array.isArray(ans)) return ans.map(i => LETTERS[i]).filter(Boolean).join(',');
  return LETTERS[ans] || '未設定';
}

/* ===== 附圖、表格、閱讀資料 ===== */
function normalizeMaterials(materials) {
  return Array.isArray(materials) ? materials.filter(Boolean) : [];
}

function materialRows(material) {
  const rows = Array.isArray(material.rows) ? material.rows : [];
  return rows.map(row => (Array.isArray(row) ? row : Object.values(row || {})));
}

function buildMaterialText(materials) {
  return normalizeMaterials(materials).map((material) => {
    const title = material.title ? `${material.title}\n` : '';
    const notes = material.notes ? `\n${material.notes}` : '';
    if (material.type === 'table') {
      const headers = Array.isArray(material.headers) ? material.headers : [];
      const tableRows = [];
      if (headers.length) {
        tableRows.push(`| ${headers.join(' | ')} |`);
        tableRows.push(`| ${headers.map(() => '---').join(' | ')} |`);
      }
      materialRows(material).forEach(cells => tableRows.push(`| ${cells.join(' | ')} |`));
      return `${title}${tableRows.join('\n')}${notes}`.trim();
    }

    if (material.type === 'image') {
      const src = material.src ? `圖片路徑：${material.src}` : '圖片材料';
      const alt = material.alt ? `\n圖片說明：${material.alt}` : '';
      return `${title}${src}${alt}${notes}`.trim();
    }

    const body = material.content || material.markdown || '';
    return `${title}${body}`.trim();
  }).filter(Boolean).join('\n\n');
}

function renderMaterialsHTML(materials) {
  const html = normalizeMaterials(materials).map((material) => {
    const title = material.title ? `<div class="material-title">${esc(material.title)}</div>` : '';
    const notes = material.notes ? `<div class="material-notes">${esc(material.notes)}</div>` : '';

    if (material.type === 'table') {
      const headers = Array.isArray(material.headers) ? material.headers : [];
      const headerHtml = headers.length
        ? `<thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>`
        : '';
      const bodyHtml = materialRows(material)
        .map(cells => `<tr>${cells.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`)
        .join('');
      return `<div class="material-block">${title}<div class="material-table-wrap"><table class="material-table">${headerHtml}<tbody>${bodyHtml}</tbody></table></div>${notes}</div>`;
    }

    if (material.type === 'image') {
      const src = material.src ? toAssetUrl(material.src) : '';
      const alt = material.alt || material.title || '題目附圖';
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

/* ===== AI 解析提示詞 ===== */
// withUser：是否附上「我的答案」（交卷檢視用）；瀏覽/錯題本只問正確答案
function buildExplainPrompt(q, { withUser = false, userAns, searchHint = true } = {}) {
  const correctLetter = q.freeScore ? '送分' : formatAnswerLetters(q.answer);
  const userLetter = isAnswered(userAns) ? formatAnswerLetters(userAns) : '未作答';
  const materialsText = buildMaterialText(q.materials);
  let t = '';
  if (searchHint) t += `${SEARCH_HINT}\n`;
  t += withUser
    ? `請說明這題為什麼正確答案是 ${correctLetter}，並分析我選的答案 ${userLetter}。\n`
    : `請說明這題為什麼正確答案是 ${correctLetter}。\n`;
  t += `請用簡潔、易懂的方式說明，先講解題意，再比較各選項，最後指出判斷關鍵。\n\n`;
  t += `題目：${q.question}\n`;
  if (materialsText) t += `\n附表/資料：\n${materialsText}\n`;
  q.options.forEach((opt, i) => {
    t += `(${LETTERS[i]}) ${opt}\n`;
  });
  t += withUser
    ? `\n我的答案：${userLetter}\n正確答案：${correctLetter}\n`
    : `\n正確答案：${correctLetter}\n`;
  return t;
}

function buildPrompt(q, userAns, { searchHint = true } = {}) {
  return buildExplainPrompt(q, { withUser: true, userAns, searchHint });
}

function buildBrowsePrompt(q, { searchHint = true } = {}) {
  return buildExplainPrompt(q, { searchHint });
}

// 多題一次複製：開頭說明 + 每題提示詞（不重複 SEARCH_HINT）
function buildBatchPrompt(header, prompts) {
  return `${SEARCH_HINT}\n${header}\n\n${prompts.join(PROMPT_SEPARATOR)}`;
}

/* ===== 修法/送分覆寫（data/overrides.json） ===== */
let _overridesData = null;
let _overridesPromise = null;

function initOverrides() {
  if (_overridesData) return Promise.resolve(_overridesData);
  if (!_overridesPromise) {
    _overridesPromise = fetchJson('data/overrides.json')
      .catch(e => {
        console.error('Failed to load overrides.json', e);
        return {};
      })
      .then(data => (_overridesData = data || {}));
  }
  return _overridesPromise;
}

function applyQuestionOverrides(q) {
  if (!_overridesData || !q || !q._bank) return;
  const patch = (_overridesData[q._bank] || {})[String(q.id)];
  if (!patch) return;
  if (patch.answer !== undefined) q.answer = patch.answer;
  if (patch.freeScore !== undefined) q.freeScore = patch.freeScore;
  if (patch.warning) q._warning = patch.warning;
  if (patch.amendmentUrl) q._amendmentUrl = patch.amendmentUrl;
  if (patch.repeats) q._repeats = patch.repeats;
}

function getBankWarningCount(file) {
  const bankOverrides = _overridesData && _overridesData[file];
  if (!bankOverrides) return 0;
  return Object.values(bankOverrides).filter(patch => patch.warning).length;
}

/* ===== 題目標記面板（重點/排除/筆記） ===== */
// notesOpen：筆記框預設展開（交卷檢視、瀏覽）或收合（作答中）
function questionMetaPanelHTML(bank, qid, { notesOpen = true } = {}) {
  const meta = getQuestionMetadata(bank, qid);
  const args = `${jsArg(bank)}, ${jsArg(qid)}`;
  return `
    <div class="q-meta-panel">
      <div class="q-meta-tags">
        <span class="q-meta-label">題目標記：</span>
        <button type="button" class="tag-pill tag-key ${meta.tag === 'key' ? 'active' : ''}" onclick="toggleQuestionTag(${args}, 'key', this)">⭐ 重點</button>
        <button type="button" class="tag-pill tag-exclude ${meta.tag === 'exclude' ? 'active' : ''}" onclick="toggleQuestionTag(${args}, 'exclude', this)">🚫 排除</button>
        <button type="button" class="tag-pill tag-notes-toggle ${notesOpen ? 'active' : ''} ${meta.notes ? 'has-notes' : ''}" onclick="toggleNotesCollapse(this)">📝 筆記</button>
      </div>
      <div class="q-meta-notes-wrapper" ${notesOpen ? '' : 'hidden'}>
        <textarea class="q-notes-input" placeholder="對此題撰寫筆記心得..." oninput="saveQuestionNotes(${args}, this.value, this)">${esc(meta.notes)}</textarea>
      </div>
    </div>`;
}

function toggleQuestionTag(bank, qid, tag, btn) {
  const meta = getQuestionMetadata(bank, qid);
  const newTag = meta.tag === tag ? '' : tag;
  meta.tag = newTag;
  saveQuestionMetadata(bank, qid, meta);

  const container = btn.closest('.q-meta-panel');
  if (container) {
    container.querySelectorAll('.tag-key, .tag-exclude').forEach(b => b.classList.remove('active'));
    if (newTag) container.querySelector(`.tag-${newTag}`)?.classList.add('active');
  }
  showToast(newTag ? `已標記為${newTag === 'key' ? '重點題' : '排除題'}` : '已取消標記');
}

function saveQuestionNotes(bank, qid, notes, el) {
  const meta = getQuestionMetadata(bank, qid);
  meta.notes = notes;
  saveQuestionMetadata(bank, qid, meta);
  el?.closest('.q-meta-panel')?.querySelector('.tag-notes-toggle')?.classList.toggle('has-notes', !!notes);
}

function toggleNotesCollapse(btn) {
  const wrapper = btn.closest('.q-meta-panel')?.querySelector('.q-meta-notes-wrapper');
  if (!wrapper) return;
  const opening = wrapper.hidden;
  wrapper.hidden = !opening;
  btn.classList.toggle('active', opening);
  if (opening) wrapper.querySelector('.q-notes-input')?.focus();
}

function repeatsBadgeHTML(q) {
  if (!q._repeats || q._repeats.length <= 1) return '';
  return `<span class="repeat-badge" title="重複考過年份：${esc(q._repeats.join('、'))}">🔄 ${esc(q._repeats.map(r => r.split(' ')[0]).join('、'))} 年</span>`;
}

function amendmentWarningHTML(q) {
  if (!q._warning) return '';
  const link = q._amendmentUrl
    ? ` <a href="${esc(q._amendmentUrl)}" target="_blank" rel="noopener" class="amendment-link" title="查看現行法條">📜 查看異動法條</a>`
    : '';
  return `<div class="amendment-warning">${esc(q._warning)}${link}</div>`;
}

/* ===== 交卷檢視 / 瀏覽 / 錯題本的題目卡片 ===== */
// mode：'result' 顯示對錯（需 userAns）；'browse' 只標正確答案。
// 複製按鈕呼叫頁面提供的 copyReview(idx)（result）或 copyBrowse(idx)（browse）。
function buildReviewItemHTML(q, { idx, userAns, mode }) {
  applyQuestionOverrides(q);
  const isResult = mode === 'result';
  const isFreeScore = !!q.freeScore;
  const multi = isMultiAnswer(q);

  const { answered, ok } = evaluateAnswer(q, userAns);
  const isSkipped = isResult && !answered;
  const isWrong = isResult && !ok;

  let cls = 'ri-neutral';
  let badgeCls = 'badge-neutral';
  let badgeText = isFreeScore ? '送分' : (multi ? '複選' : '');
  if (isResult) {
    cls = isWrong ? 'ri-wrong' : 'ri-correct';
    badgeCls = isWrong ? 'badge-wrong' : 'badge-correct';
    badgeText = isSkipped ? '未作答' : (isFreeScore ? '送分' : (ok ? '答對' : '答錯'));
    if (multi && !isSkipped) badgeText += '（複選）';
  }

  const correctSet = new Set(multi ? q.answer : [q.answer]);
  const userSet = new Set(multi ? (Array.isArray(userAns) ? userAns : []) : [userAns]);
  const optsHtml = q.options.map((opt, oi) => {
    let c = '';
    if (!isFreeScore && correctSet.has(oi)) c = 'opt-correct';
    if (isWrong && userSet.has(oi) && !correctSet.has(oi)) c = 'opt-wrong';
    return `<div class="${c}">(${LETTERS[oi]}) ${esc(opt)}</div>`;
  }).join('');

  const bank = q._bank || '';
  const sourceHtml = bank
    ? `<div class="ri-source">📄 來源：${esc(bankLabel(bank))} · 原試卷第 ${esc(q.id)} 題 · ${questionAttemptLabel(bank, q.id)}</div>`
    : '';
  const copyFn = isResult ? `copyReview(${idx})` : `copyBrowse(${idx})`;

  return `<div class="review-item ${cls}">
    <div class="ri-header">
      <span class="ri-number">第 ${idx + 1} 題 ${repeatsBadgeHTML(q)}</span>
      ${badgeText ? `<span class="ri-badge ${badgeCls}">${badgeText}</span>` : ''}
    </div>
    ${sourceHtml}
    <div class="ri-q">${esc(q.question)}</div>
    ${amendmentWarningHTML(q)}
    ${renderMaterialsHTML(q.materials)}
    <div class="ri-opts">${optsHtml}</div>
    <div class="ri-actions">
      <button class="copy-btn" id="cpbtn-${idx}" onclick="${copyFn}">複製解析提示</button>
    </div>
    ${questionMetaPanelHTML(bank, q.id)}
  </div>`;
}

/* ===== 來源題庫勾選面板（首頁錯題/標記模式、錯題本共用） ===== */
// items: [{ bank, qid }] → [{ file, count, title }]，依題數多→少排序；
// 清單內若有同名（年度＋科目相同、僅梯次/組別不同）的題庫，補上 category 以利區分。
function summarizeItemsByBank(items, bankInfo = []) {
  const counts = {};
  for (const it of items) counts[it.bank] = (counts[it.bank] || 0) + 1;
  const infoByFile = new Map(bankInfo.map(b => [b.file, b]));
  const banks = Object.keys(counts).map(file => {
    const info = infoByFile.get(file);
    return { file, count: counts[file], title: info ? bankTitle(info) : bankLabel(file), info };
  });
  const nameCount = {};
  banks.forEach(b => { nameCount[b.title] = (nameCount[b.title] || 0) + 1; });
  banks.forEach(b => {
    if (nameCount[b.title] > 1 && b.info && b.info.category && !b.title.includes(b.info.category)) {
      b.title += ` · ${b.info.category}`;
    }
  });
  return banks.sort((a, b) => b.count - a.count || a.title.localeCompare(b.title));
}

class BankScopePicker {
  // container：面板容器；hint：說明文字；onChange：勾選變動時呼叫
  constructor({ container, hint, onChange = () => { } }) {
    this.container = container;
    this.hint = hint;
    this.onChange = onChange;
    this.banks = [];
    this.selected = null; // null = 尚未初始化（視同全選）；空集合是使用者刻意全不選

    container.addEventListener('change', e => {
      const item = e.target.closest('.scope-item');
      if (!item) return;
      this.ensureSelection();
      if (e.target.checked) this.selected.add(item.dataset.file); else this.selected.delete(item.dataset.file);
      item.classList.toggle('selected', e.target.checked);
      this.updateSummary();
      this.onChange();
    });
    container.addEventListener('click', e => {
      const btn = e.target.closest('[data-scope-all]');
      if (btn) this.setAll(btn.dataset.scopeAll === '1');
    });
  }

  ensureSelection() {
    if (!this.selected) this.selected = new Set(this.banks.map(b => b.file));
  }

  // 重新設定來源（例如切換模式、門檻改變）：回到全選
  reset() {
    this.selected = null;
  }

  render(banks) {
    this.banks = banks;
    const valid = new Set(banks.map(b => b.file));
    // 保留既有勾選，但移除已不存在的題庫（例如該題庫的錯題已全部答對）
    this.selected = this.selected ? new Set([...this.selected].filter(f => valid.has(f))) : new Set(valid);
    this.container.innerHTML = `
      <div class="scope-head">
        <span class="scope-title">限定來源題庫</span>
        <span class="scope-summary"></span>
      </div>
      <div class="scope-hint">${esc(this.hint)}</div>
      <div class="bank-toolbar">
        <button type="button" class="btn btn-secondary btn-sm" data-scope-all="1">全選</button>
        <button type="button" class="btn btn-secondary btn-sm" data-scope-all="0">全不選</button>
      </div>
      <div class="scope-list">
        ${banks.map(b => `
          <label class="scope-item ${this.selected.has(b.file) ? 'selected' : ''}" data-file="${esc(b.file)}">
            <input type="checkbox" ${this.selected.has(b.file) ? 'checked' : ''}>
            <span class="scope-item-title"><span class="scope-marquee">${esc(b.title)}</span></span>
            <span class="scope-item-count">${b.count} 題</span>
          </label>`).join('')}
      </div>`;
    this.updateSummary();
    this.applyMarquee();
  }

  setAll(on) {
    this.selected = on ? new Set(this.banks.map(b => b.file)) : new Set();
    this.container.querySelectorAll('.scope-item').forEach(item => {
      const sel = this.selected.has(item.dataset.file);
      item.classList.toggle('selected', sel);
      const cb = item.querySelector('input');
      if (cb) cb.checked = sel;
    });
    this.updateSummary();
    this.onChange();
  }

  isSelected(file) {
    return !this.selected || this.selected.has(file);
  }

  selectedBanks() {
    return this.banks.filter(b => this.isSelected(b.file));
  }

  isNarrowed() {
    return this.selectedBanks().length < this.banks.length;
  }

  updateSummary() {
    const summary = this.container.querySelector('.scope-summary');
    if (!summary) return;
    const total = this.banks.reduce((s, b) => s + b.count, 0);
    const sel = this.selectedBanks().reduce((s, b) => s + b.count, 0);
    summary.textContent = `已選 ${sel} 題 / 共 ${total} 題`;
  }

  // 量測每個標題是否超出可視寬度，只有超出的才啟用跑馬燈，並依超出量決定捲動距離與速度
  applyMarquee() {
    this.container.querySelectorAll('.scope-item-title').forEach(box => {
      const inner = box.querySelector('.scope-marquee');
      if (!inner) return;
      box.classList.remove('is-marquee');
      box.style.removeProperty('--marquee-shift');
      box.style.removeProperty('--marquee-dur');
      const overflow = inner.scrollWidth - box.clientWidth;
      if (overflow > 2) {
        const dist = overflow + 8;
        box.style.setProperty('--marquee-shift', `-${dist}px`);
        box.style.setProperty('--marquee-dur', `${Math.max(5, dist / 22).toFixed(1)}s`);
        box.classList.add('is-marquee');
      }
    });
  }

  // 視窗縮放、字型載入後字寬會變，需重新量測
  watchLayout() {
    let timer = null;
    window.addEventListener('resize', () => {
      clearTimeout(timer);
      timer = setTimeout(() => this.applyMarquee(), 150);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => this.applyMarquee());
    return this;
  }
}
