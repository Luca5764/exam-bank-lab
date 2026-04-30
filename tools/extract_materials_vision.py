#!/usr/bin/env python3
"""
Extract missing question materials, especially tables, from PDF page images.

This tool is intentionally narrower than parse_pdf_vision.py: it assumes the
question JSON already exists and asks a vision model only for the missing
`materials` block of selected questions.

Examples:
  python tools/extract_materials_vision.py ^
    --pdf "農田水利/113/113農田水利署-經濟學概要.pdf" ^
    --questions "questions/113農田水利署-經濟學概要.json" ^
    --ids 29 31 32 33 ^
    --model qwen3.5:9b ^
    --think

  python tools/extract_materials_vision.py --pdf exam.pdf --questions bank.json --auto --write
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TABLE_HINTS = ("【表", "下表", "如下表", "統計表", "表格", "資料如下", "情形如下")
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"


class ModelJsonError(ValueError):
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def load_fitz() -> Any:
    global fitz
    try:
        import fitz as fitz_module  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - runtime environment dependent
        raise SystemExit("Missing dependency: install PyMuPDF first, e.g. `pip install PyMuPDF`.") from exc
    fitz = fitz_module
    return fitz


def load_questions(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def select_targets(
    questions: list[dict[str, Any]],
    ids: list[int] | None,
    auto: bool,
) -> list[dict[str, Any]]:
    if ids:
      id_set = set(ids)
      return [q for q in questions if q.get("id") in id_set]

    if not auto:
        return []

    targets = []
    for q in questions:
        text = str(q.get("question", ""))
        if not q.get("materials") and any(hint in text for hint in TABLE_HINTS):
            targets.append(q)
    return targets


def normalize_for_search(text: str) -> str:
    return re.sub(r"\s+", "", text)


def find_candidate_pages(doc: fitz.Document, question: dict[str, Any], explicit_pages: list[int] | None) -> list[int]:
    if explicit_pages:
        return [p - 1 for p in explicit_pages if 1 <= p <= len(doc)]

    q_text = normalize_for_search(str(question.get("question", "")))
    snippets = [q_text[:40], q_text[:24]]
    pages = []

    for idx, page in enumerate(doc):
        page_text = normalize_for_search(page.get_text("text") or "")
        if any(snippet and snippet in page_text for snippet in snippets):
            pages.append(idx)

    if pages:
        expanded = set()
        for p in pages:
            expanded.add(p)
            if p + 1 < len(doc):
                expanded.add(p + 1)
        return sorted(expanded)

    # If text extraction fails, scan all pages. This is slower but handles image-only PDFs.
    return list(range(len(doc)))


def render_page(page: fitz.Page, out_path: Path, dpi: int) -> None:
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(out_path)


def build_prompt(question: dict[str, Any]) -> str:
    options = "\n".join(
        f"({chr(65 + idx)}) {option}"
        for idx, option in enumerate(question.get("options", []))
    )
    return f"""你是考試題目資料表擷取助理。請只根據圖片內容，替指定題目擷取作答所需的附表、統計表、圖表中的文字資料。

指定題目 id: {question.get("id")}
題目:
{question.get("question", "")}

選項:
{options}

任務:
1. 判斷圖片中是否包含這一題作答需要的表格或補充資料。
2. 若沒有，輸出 found=false。
3. 若有，將表格轉成 materials JSON。表格請用 type="table"，保留欄名、列名、年份、單位、金額符號、百分比與註解。
4. 複雜表格可以拆成多個 material，但不要省略任何會影響作答的數字。
5. 多層表頭必須展平成單列 headers，且 headers 的欄位數必須等於每一列 rows 的欄位數。例如產品 A/B/C/D 各有 Q 與 P 時，headers 應為 ["年份", "A 數量 Q_A", "A 價格 P_A", "B 數量 Q_B", ...]，不要把第二層表頭放進 rows。
6. 可以在內部仔細推理與比對，但最終只輸出 JSON，不要輸出解釋、Markdown code fence 或額外文字。

輸出格式必須完全符合:
{{
  "found": true,
  "question_id": {question.get("id")},
  "materials": [
    {{
      "type": "table",
      "title": "表格標題，若無標題可用空字串",
      "headers": ["欄位1", "欄位2"],
      "rows": [
        ["第一列欄位1", "第一列欄位2"]
      ],
      "notes": "表格註解或單位，沒有則省略"
    }}
  ],
  "confidence": 0.0,
  "warnings": []
}}
"""


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    text = strip_thinking(text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ModelJsonError("model response did not contain a JSON object", text)
    raw = re.sub(r",\s*([}\]])", r"\1", match.group(0))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelJsonError(f"model response contained invalid JSON: {exc}", text) from exc


def ask_ollama(
    image_path: Path,
    prompt: str,
    model: str,
    url: str,
    think: bool,
    temperature: float,
) -> dict[str, Any]:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
        },
        "think": think,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as res:
            body = json.loads(res.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to call Ollama at {url}: {exc}") from exc

    message = body.get("message", {})
    content = message.get("content") or message.get("thinking") or ""
    return extract_json_object(content)


def valid_materials(result: dict[str, Any], qid: int) -> bool:
    if result.get("question_id") not in (qid, str(qid), None):
        return False
    materials = result.get("materials")
    return bool(result.get("found") and isinstance(materials, list) and materials)


def merge_materials(questions: list[dict[str, Any]], results: list[dict[str, Any]]) -> int:
    by_id = {q.get("id"): q for q in questions}
    changed = 0
    for item in results:
        qid = item["id"]
        materials = item.get("materials")
        if qid in by_id and materials:
            by_id[qid]["materials"] = materials
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract table materials from PDF images with a vision model.")
    parser.add_argument("--pdf", required=True, type=Path, help="Source PDF path.")
    parser.add_argument("--questions", required=True, type=Path, help="Existing question bank JSON.")
    parser.add_argument("--ids", nargs="*", type=int, help="Question ids to process.")
    parser.add_argument("--auto", action="store_true", help="Process questions with table-like hints and no materials.")
    parser.add_argument("--pages", nargs="*", type=int, help="Limit scan to 1-based PDF pages.")
    parser.add_argument("--model", default="qwen3.5:9b", help="Ollama vision model name.")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama chat API URL.")
    parser.add_argument("--dpi", type=int, default=220, help="PDF render DPI.")
    parser.add_argument("--think", action="store_true", help="Ask supported Qwen/Ollama models to enable thinking.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Model temperature.")
    parser.add_argument("--write", action="store_true", help="Write extracted materials back to --questions.")
    parser.add_argument("--out", type=Path, help="Optional report JSON path.")
    parser.add_argument("--keep-images", type=Path, help="Optional directory to keep rendered page PNGs.")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    targets = select_targets(questions, args.ids, args.auto)
    if not targets:
        raise SystemExit("No target questions. Pass --ids or --auto.")

    fitz = load_fitz()
    report: list[dict[str, Any]] = []
    with fitz.open(args.pdf) as doc:
        image_root_cm = tempfile.TemporaryDirectory() if not args.keep_images else None
        image_root = args.keep_images or Path(image_root_cm.name)  # type: ignore[union-attr]
        image_root.mkdir(parents=True, exist_ok=True)

        try:
            for q in targets:
                qid = int(q.get("id"))
                prompt = build_prompt(q)
                page_indexes = find_candidate_pages(doc, q, args.pages)
                eprint(f"Q{qid}: scanning pages {', '.join(str(p + 1) for p in page_indexes)}")

                best: dict[str, Any] | None = None
                attempts = []
                for page_idx in page_indexes:
                    image_path = image_root / f"q{qid}_page{page_idx + 1}.png"
                    render_page(doc[page_idx], image_path, args.dpi)
                    try:
                        result = ask_ollama(
                            image_path=image_path,
                            prompt=prompt,
                            model=args.model,
                            url=args.ollama_url,
                            think=args.think,
                            temperature=args.temperature,
                        )
                    except Exception as exc:  # keep processing other targets
                        failed = {"page": page_idx + 1, "error": str(exc)}
                        if isinstance(exc, ModelJsonError):
                            failed["raw_response"] = exc.raw[:4000]
                        attempts.append(failed)
                        eprint(f"  page {page_idx + 1}: {exc}")
                        continue

                    result["page"] = page_idx + 1
                    attempts.append(result)
                    if valid_materials(result, qid):
                        if best is None or float(result.get("confidence", 0)) > float(best.get("confidence", 0)):
                            best = result

                item = {
                    "id": qid,
                    "question": q.get("question", ""),
                    "found": bool(best),
                    "page": best.get("page") if best else None,
                    "materials": best.get("materials") if best else [],
                    "confidence": best.get("confidence") if best else 0,
                    "warnings": best.get("warnings", []) if best else [],
                    "attempts": attempts,
                }
                report.append(item)
        finally:
            if image_root_cm:
                image_root_cm.cleanup()

    if args.write:
        changed = merge_materials(questions, report)
        args.questions.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        eprint(f"Updated {changed} question(s) in {args.questions}")

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
        eprint(f"Wrote report to {args.out}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
