# 考古題練習室

這是一個部署在 GitHub Pages 上的純前端考古題練習網站。網站收錄農田水利相關招考、灌溉管理組、統測農概與統測商管群題庫，支援題庫瀏覽、隨機測驗、指定題數、交卷檢視、錯題複習、作答續作與法條字卡。

網站：
[https://luca5764.github.io/exam-bank-lab/](https://luca5764.github.io/exam-bank-lab/)

## 功能

- 純靜態網站，沒有後端服務。
- 題庫由 `questions/*.json` 提供。
- 題庫索引由 `tools/build_index.py` 產生 `data/banks.json`。
- 可依系列、科目、年份與關鍵字瀏覽題庫。
- 支援隨機抽題、照順序練習、錯題複習、歷史紀錄與未完成測驗續作。
- 題組題會盡量保持同組一起出現，避免「承上題」被拆散。
- 題目可帶 `materials`，用來顯示附圖、表格、閱讀資料與註解。
- 法條字卡可依法律與章節閱讀，支援手機左右滑與個人備註。

## 題庫範圍

目前主要資料來源：

- 農田水利、水利會與農田水利署招考題庫。
- 灌溉管理組相關題庫。
- 統測農概題庫。
- 統測商管群專二題庫。
- 農田水利相關法條字卡。

首頁以題庫系列和科目整理資料。未來如果加入更多來源，優先補齊 `data/banks.json` 需要的 metadata，而不是把所有題庫直接混在同一層篩選。

## 資料保存

測驗紀錄、錯題紀錄、續作狀態與法條備註都保存在使用者自己的瀏覽器 `localStorage`，不是存在伺服器上。

這代表：

- 每位使用者的作答紀錄只存在自己的裝置與瀏覽器中。
- 關閉分頁、重新打開瀏覽器後，通常仍會保留紀錄。
- 清除瀏覽器資料、使用無痕模式、換瀏覽器或換裝置時，紀錄可能消失。
- 網站管理者看不到其他人的成績或錯題紀錄。

## 目錄

```text
index.html            首頁、題庫選擇與測驗設定
quiz.html             測驗頁
review.html           交卷後檢視
browse.html           題庫內容瀏覽
wrong.html            錯題複習
changelog.html        更新日誌
laws.html             法條字卡
css/style.css         樣式
js/shared.js          共用前端邏輯
assets/               題目附圖與前端 vendor 檔
questions/            題庫 JSON
data/banks.json       題庫索引與顯示 metadata
data/changelog.json   commit 產生的更新日誌
data/laws.json        法條字卡資料
tools/                維護與資料重建工具
法條/                 法條 txt 來源
農田水利/             農田水利原始 PDF 題目來源
統測專二/             統測專二原始 PDF 題目來源
農水_管理組考題/       管理組與統測農概原始 PDF 題目來源
```

`tools/` 內只保留仍有維護價值的腳本；用途整理在 [tools/README.md](tools/README.md)。

## 本機使用

這個專案本質上是靜態網站。直接用瀏覽器開 HTML 有時能看到畫面，但題庫 `fetch` 在某些環境會失敗，建議用本機伺服器測試。

```bash
python -m http.server 8765
```

然後開啟：

```text
http://127.0.0.1:8765/
```

## GitHub Pages 部署

此專案使用 GitHub Actions 自動部署。

流程：

1. push 到 `main`
2. GitHub Actions 執行 `tools/build_index.py`
3. 將靜態網站部署到 `gh-pages`

工作流程設定檔：

[.github/workflows/deploy.yml](.github/workflows/deploy.yml)

## 題庫格式

每份題庫是 `questions/*.json`，內容為題目陣列。常用欄位：

- `id`：題號。
- `question`：題目文字。
- `options`：選項陣列。
- `answer`：正確答案索引，從 `0` 開始。
- `noShuffle`：選項不可打亂時設為 `true`。
- `freeScore`：送分題或不計一般選擇題判分時使用。
- `group` 或 `groupId`：題組識別。
- `materials`：附圖、表格、閱讀資料或註解。

`data/banks.json` 由 `tools/build_index.py` 重建，每份題庫會包含：

- `file`：題庫 JSON 路徑。
- `name`：完整顯示名稱。
- `displayName`：首頁卡片使用的短名稱。
- `year`：年度。
- `source`：原始來源，例如農田水利、農田水利署、統測專二、統測農概。
- `category`：職等、群別或科目類別。
- `subject`：統一後的科目名稱。
- `originalSubject`：原始檔名或 PDF 中的科目名稱。
- `count`：題數。

## 維護原則

- 題庫 JSON、索引資料與必要圖片應進 Git。
- 原始 PDF 可以留在本機來源資料夾，但不推到 GitHub。
- 一次性實驗輸出、模型 cache、OCR 中間檔放在 `.tmp/`。
- 新增題庫後先跑 `tools/build_index.py`，再確認 `data/banks.json` 題數正確。
- 有附圖、表格或閱讀資料的題目，優先用 `materials` 保留結構，而不是塞回題目文字。

## 限制

- 沒有帳號系統。
- 沒有跨裝置同步。
- 沒有排行榜或集中儲存成績。
- 若未來需要共用成績、帳號登入或雲端同步，必須新增後端服務。
