# 考古題練習室

這是一個部署在 GitHub Pages 上的純前端考古題練習網站。網站目前收錄農田水利招考與統測商管群題庫，支援題庫瀏覽、隨機測驗、指定題數、交卷檢視、錯題複習與作答續作。

目前網站：
[https://luca5764.github.io/exam-bank-lab/](https://luca5764.github.io/exam-bank-lab/)

## 專案定位

首頁以「題庫系列」整理不同考試來源，避免不同考科混在同一層級造成混亂。

目前題庫系列：

- `農田水利招考`：水利會、農田水利署共同科目與專業科目。
- `統測商管群`：統測專二會計學與經濟學。

未來如果加入更多題庫，建議優先新增題庫系列與科目 metadata，而不是單純把所有題庫塞進同一排篩選按鈕。

## 功能

- 純靜態網站，沒有後端服務。
- 可直接部署到 GitHub Pages。
- 題庫由 `questions/*.json` 提供。
- 題庫索引由 `tools/build_index.py` 產生 `data/banks.json`。
- 題庫可依系列、科目、年份與關鍵字瀏覽。
- 測驗題數可由使用者輸入，並保留 `10 題快測` 與 `全部題目`。
- 支援隨機抽題、照順序練習、錯題複習、歷史紀錄與未完成測驗續作。
- 題組題會盡量保持同組一起出現，避免「承上題」被拆散。

## 資料保存方式

本網站的測驗資料保存在使用者自己的瀏覽器 `localStorage`，不是存在伺服器上。

這代表：

- 每位使用者的作答紀錄只存在自己的裝置與瀏覽器中。
- 關閉分頁、重新打開瀏覽器後，通常仍會保留紀錄。
- 若清除瀏覽器資料、使用無痕模式、換瀏覽器或換裝置，紀錄可能消失。
- 網站管理者無法看到其他人的成績或錯題紀錄。

## 目錄說明

```text
index.html            首頁、題庫系列選擇與測驗設定
quiz.html             測驗頁
review.html           交卷後檢視
browse.html           題庫內容瀏覽
wrong.html            錯題複習
changelog.html        更新日誌
css/style.css         樣式
js/shared.js          共用前端邏輯
questions/            題庫 JSON
data/banks.json       題庫索引與顯示 metadata
data/changelog.json   commit 產生的更新日誌
tools/build_index.py  重建題庫索引
tools/                題庫轉換、OCR、裁圖與維護工具
農田水利/             農田水利原始 PDF 題目來源
統測專二/             統測專二原始 PDF 題目來源
```

## 本機使用

這個專案本質上是靜態網站，直接用瀏覽器開 HTML 雖然有時能看到畫面，但題庫 `fetch` 在某些環境會失敗。建議用本機伺服器測試。

例如：

```bash
python -m http.server 8765
```

然後開啟：

```text
http://127.0.0.1:8765/
```

## GitHub Pages 部署

此專案使用 GitHub Actions 自動部署。

流程如下：

1. push 到 `main`
2. GitHub Actions 執行 `tools/build_index.py`
3. 將靜態檔案部署到 `gh-pages`

工作流程設定檔：

[`/.github/workflows/deploy.yml`](./.github/workflows/deploy.yml)

## 題庫整理規則

`data/banks.json` 內每份題庫會包含：

- `file`：題庫 JSON 路徑。
- `name`：較完整的顯示名稱。
- `displayName`：首頁卡片使用的短名稱。
- `year`：年度。
- `source`：原始來源，例如農田水利、農田水利署、統測專二。
- `category`：職等、群別或科目類別。
- `subject`：統一後的科目名稱。
- `originalSubject`：原始檔名或 PDF 中的科目名稱。
- `count`：題數。

常見科目會做名稱統一，例如 `法學緒論`、`公文及法學緒論`、`公文與農田水利相關法規` 會歸到 `公文與法學緒論`。

## 注意事項

- 這個網站沒有帳號系統。
- 沒有跨裝置同步。
- 沒有排行榜或集中儲存成績。
- 若未來需要共用成績、帳號登入或雲端同步，必須新增後端服務。
