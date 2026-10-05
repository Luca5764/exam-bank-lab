# CLAUDE.md

考古題練習室 — 部署在 GitHub Pages 的純前端靜態考古題網站（無後端）。
專案概觀、題庫 JSON 格式、`data/banks.json` 欄位說明見 [README.md](README.md)。

## 常用指令

```bash
# 本機預覽（直接開 HTML 會因 fetch 失敗而壞掉，要用 server）
python -m http.server 8765

# 新增/修改題庫後重建索引，並確認 data/banks.json 題數正確
python tools/build_index.py
```

Python 環境用 uv 管理（`uv.lock`、`.python-version`，Python 3.13+）。

## 架構

- **前端**：每個 HTML 頁面 = `js/` 共用模組 + 頁面內嵌的一段 `<script>`。
  沒有打包工具、沒有框架。樣式集中在 `css/style.css`。共用模組依序載入：
  - `core.js`：跳脫、主題、toast、剪貼簿、`fetchJson`、localStorage 讀寫、SW 註冊
  - `tracks.js`：考試類別 `TRACKS` 設定表、題庫索引、分流切換列、題庫書架 `BankShelf`
  - `progress.js`：作答歷程、錯題池、練習統計、題目標記/筆記、進度備份
  - `question-view.js`：判分、附圖、AI 提示詞、修法覆寫、題目卡片、來源題庫勾選 `BankScopePicker`
  （`laws.html`、`changelog.html` 只需要 `core.js`）
- **考試類別（分流）**：新增類別只要在 `js/tracks.js` 的 `TRACKS` 加一筆
  （`sources` 對應 banks.json 的 `source`、`collections` 為書架系列），
  並在 `tools/build_index.py` 讓新題庫檔名能解析出該 `source`。
- **資料**：`questions/*.json`（題庫）→ `tools/build_index.py` → `data/banks.json`（索引）。
  使用者狀態（作答紀錄、錯題、法條備註）全存 `localStorage`。
- **部署**：push 到 `main` → GitHub Actions 跑 `build_index.py` → 部署到 `gh-pages`
  （`.github/workflows/deploy.yml`，會排除 `tools/`、`*.py` 等）。
- **維護腳本**：放 `tools/`，每支腳本用途記在 `tools/README.md`，新增腳本要同步補上。

## 慣例

- Commit 訊息：繁體中文，`feat:`/`fix:`/`chore:` 前綴（見 `git log`）。
- **跨頁共用的 JS 邏輯一律放 `js/*.js`，頁面 inline script 不得定義與共用模組
  同名的函式或變數**（全域函式會互相遮蔽，曾因此出過 `bankLabel` 顯示錯誤
  的 bug）。要改共用行為就直接改模組；新增頁面函式前先 `grep js/` 確認沒有撞名。
- **改了 css/js 要同步更新版號**：所有頁面引用 `?v=YYYYMMDD`，`sw.js` 的
  `CORE_ASSETS` 也要用同一個版號（SW 以含 `?v` 的完整網址比對快取），
  並 bump `CACHE_VERSION`。
- **post-commit hook 會自動更新 `data/changelog.json` 並 amend 進同一個 commit**
  （`.githooks/post-commit`）。commit 後看到 hash 變動是正常的；
  設 `SKIP_CHANGELOG=1` 可跳過。
- 一次性除錯腳本、實驗輸出、模型 cache 放 `scratch/`（gitignored）或 `.tmp/`，
  不要進版本控制。過期的一次性檔案歸檔到 `.tmp/archived-oneoffs-<日期>/`。
- 原始 PDF 留在本機來源資料夾（`農田水利/`、`統測專二/`、`農水_管理組考題/`、
  `交通部/`），`*.pdf` 與 `*.txt` 已 gitignore，不推上 GitHub。
- 題庫檔名決定 metadata（見 `tools/build_index.py`）：`交通部YYY-N-科目`、
  `YYY統測專二-科目`、`EMT{級數}-{開課單位}-{科目}`，其餘歸農田水利。
- 題目附圖、表格、閱讀資料用 `materials` 欄位保留結構，不要塞回題目文字。

## Windows 注意事項

- 終端機輸出中文的 Python 腳本要加 `sys.stdout.reconfigure(encoding='utf-8')`，
  讀寫檔案一律明確指定 `encoding="utf-8"`。
- 檔名大量使用中文（questions/、來源資料夾），shell 操作時注意引號與編碼。
