# 農田水利考古題測驗

這是一個部署在 GitHub Pages 上的純前端測驗網站，提供農田水利相關考古題練習、交卷檢視、錯題複習與題庫瀏覽功能。

網站網址：
[https://luca5764.github.io/Irrigation_Quiz/](https://luca5764.github.io/Irrigation_Quiz/)

## 專案特性

- 純靜態網站，沒有後端服務。
- 可直接部署到 GitHub Pages。
- 題庫由 `questions/*.json` 提供。
- 題庫清單由 `tools/build_index.py` 自動產生 `data/banks.json`。
- 題庫名稱依原始 PDF 年份整理，目前依 `105 / 109 / 111 / 113` 排序顯示。
- 支援測驗作答、交卷、歷史紀錄、錯題整理、續作與題庫瀏覽。

## 資料保存方式

本網站的測驗資料是保存在使用者自己的瀏覽器 `localStorage`，不是存在伺服器上。

這代表：

- 每位使用者的作答紀錄只存在自己的裝置與瀏覽器中。
- 關閉分頁、重新打開瀏覽器後，通常仍會保留紀錄。
- 若清除瀏覽器資料、使用無痕模式、換瀏覽器或換裝置，紀錄可能消失。
- 網站管理者無法看到其他人的成績或錯題紀錄。

## 目錄說明

```text
index.html            首頁與題庫選擇
quiz.html             測驗頁
review.html           交卷後檢視
browse.html           題庫瀏覽
wrong.html            錯題複習
css/style.css         樣式
js/shared.js          共用前端邏輯
questions/            題庫 JSON
data/banks.json       題庫索引
tools/build_index.py  重建題庫索引
農田水利/             原始 PDF 題目來源
```

## 本機使用

這個專案本質上是靜態網站，直接用瀏覽器開 HTML 雖然有時能看到畫面，但題庫 `fetch` 在某些環境會失敗。建議用本機伺服器測試。

例如：

```bash
python -m http.server 8080
```

然後開啟：

```text
http://localhost:8080/
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

- 顯示名稱由 `tools/build_index.py` 自動整理。
- 題庫會依原始 PDF 所在資料夾年份排序。
- `questions/questions.json` 已視為舊版綜合題庫，不再顯示在前台題庫清單中。

## 注意事項

- 這個網站沒有帳號系統。
- 沒有跨裝置同步。
- 沒有排行榜或集中儲存成績。
- 若未來需要共用成績、帳號登入或雲端同步，必須新增後端服務。
