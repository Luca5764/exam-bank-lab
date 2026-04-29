# 農田水利測驗系統 — 未來規劃

## 🔲 區網外遠端存取

**目標：** 讓不在同一個 WiFi 下的人也能連到測驗網站。

**方案：** 使用 Cloudflare Tunnel (Quick Tunnel)
- 完全免費、不用註冊、無流量限制
- 安裝：`winget install cloudflare.cloudflared`
- 啟動：`cloudflared tunnel --url http://localhost:8080`
- 會產生一個 `https://xxxxx.trycloudflare.com` 的隨機網址
- 關掉 cloudflared 就自動斷線

**使用流程：**
1. 開一個終端機跑 `python server.py`
2. 開另一個終端機跑 `cloudflared tunnel --url http://localhost:8080`
3. 把產生的網址分享給需要做測驗的人
