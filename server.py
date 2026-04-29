#!/usr/bin/env python3
"""
農田水利法規測驗 — 本機伺服器
用法：python server.py
預設 http://0.0.0.0:8080
"""

import http.server
import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8080

if getattr(sys, 'frozen', False):
    # PyInstaller 打包後：靜態檔在 _MEIPASS（onefile 為暫存目錄，onedir 為 exe 所在目錄）
    # 可寫入資料（history.json）固定放在 exe 旁邊
    BASE_DIR = Path(sys._MEIPASS)
    DATA_DIR = Path(sys.executable).parent / "data"
else:
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"

HISTORY_FILE = DATA_DIR / "history.json"


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(data):
    HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class QuizHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/history":
            self._json_response(load_history())

        
        elif path == "/api/banks":
            q_dir = BASE_DIR / "questions"
            banks = []
            if q_dir.exists():
                for f in sorted(q_dir.glob("*.json")):
                    try:
                        import json
                        data = json.loads(f.read_text(encoding="utf-8"))
                        count = len(data) if isinstance(data, list) else 0
                    except:
                        count = 0
                    banks.append({
                        "file": f"questions/{f.name}",
                        "name": f.stem,
                        "count": count
                    })
            self._json_response(banks)
        elif path == "/api/wrong-pool":
            history = load_history()
            today = __import__("datetime").date.today().isoformat()
            last_result = {}
            ever_wrong = set()
            today_wrong = set()
            for session in history:
                sess_bank = session.get("bank", "questions.json")
                for item in session.get("answers", []):
                    qid = item["qid"]
                    b = item.get("bank", sess_bank)
                    key = (b, qid)
                    ok = item.get("correct", False)
                    last_result[key] = ok
                    if not ok:
                        ever_wrong.add(key)
                        if session.get("date_iso", "")[:10] == today:
                            today_wrong.add(key)
            still_wrong = {k for k, ok in last_result.items() if not ok}
            past_wrong = ever_wrong - today_wrong
            def to_list(s):
                return sorted(
                    [{"bank": b, "qid": q} for b, q in s],
                    key=lambda x: (x["bank"], x["qid"])
                )
            self._json_response({
                "ever_wrong": to_list(ever_wrong),
                "still_wrong": to_list(still_wrong),
                "today_wrong": to_list(today_wrong),
                "past_wrong": to_list(past_wrong),
            })
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""

        if path == "/api/history":
            try:
                record = json.loads(body)
                history = load_history()
                history.append(record)
                save_history(history)
                self._json_response({"ok": True})
            except Exception as e:
                self._json_response({"error": str(e)}, code=400)

        elif path == "/api/history/delete":
            try:
                data = json.loads(body)
                idx = data.get("index")
                history = load_history()
                if isinstance(idx, int) and 0 <= idx < len(history):
                    history.pop(idx)
                    save_history(history)
                    self._json_response({"ok": True})
                else:
                    self._json_response({"error": "invalid index"}, code=400)
            except Exception as e:
                self._json_response({"error": str(e)}, code=400)

        elif path == "/api/history/clear":
            save_history([])
            self._json_response({"ok": True})

        else:
            self.send_error(404)

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        msg = args[0] if args else ""
        if "/api/" in str(msg):
            return
        super().log_message(fmt, *args)


def main():
    ensure_data_dir()
    os.chdir(BASE_DIR)
    print(f"\n  工作目錄：{BASE_DIR}")
    print(f"  css/style.css 存在：{(BASE_DIR / 'css' / 'style.css').exists()}")
    print(f"  js/shared.js 存在：{(BASE_DIR / 'js' / 'shared.js').exists()}")
    print(f"  questions/questions.json 存在：{(BASE_DIR / 'questions' / 'questions.json').exists()}")

    server = http.server.HTTPServer(("0.0.0.0", PORT), QuizHandler)
    ip_hint = "localhost"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_hint = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print()
    print("╔══════════════════════════════════════════════╗")
    print("║   農田水利法規測驗伺服器已啟動！             ║")
    print("║                                              ║")
    print(f"║   本機：http://localhost:{PORT}               ║")
    print(f"║   區網：http://{ip_hint}:{PORT}".ljust(48) + "║")
    print("║                                              ║")
    print("║   按 Ctrl+C 停止伺服器                       ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n伺服器已停止。")
        server.server_close()


if __name__ == "__main__":
    main()