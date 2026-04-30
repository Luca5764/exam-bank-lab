#!/usr/bin/env python3
"""
Build a quiz JSON bank from TVE "統測專二" PDFs.

This is a deterministic first pass:
- answers are extracted from the answer PDF text layer;
- questions/options are extracted from the question PDF text layer using the
  same question-number coordinates as crop_tvee_questions.py;
- questions mentioning charts/tables get a full-question screenshot as an
  image material, so visual content is preserved for the frontend.

Example:
  .venv\\Scripts\\python.exe tools\\build_tvee_bank.py --year 109 --write
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from crop_tvee_questions import (
    DEFAULT_SOURCE_DIR,
    crop_questions,
    find_question_pdf,
    load_fitz,
)


ANSWER_PDF_SUFFIX = "\u7b54.pdf"
OPTION_RE = re.compile(r"\s*\(([A-D])\)\s*")
MATERIAL_PATTERNS = [
    re.compile(r"如\s*[圖表]"),
    re.compile(r"[圖表]\s*[（(]\s*[一二三四五六七八九十\d]+\s*[)）]"),
    re.compile(r"曲線圖"),
    re.compile(r"附圖"),
    re.compile(r"下[圖表]"),
    re.compile(r"上[圖表]"),
]
MATERIAL_TAIL_RE = re.compile(r"\s+[圖表]\s*[（(]\s*[一二三四五六七八九十\d]+\s*[)）].*$")
READING_PASSAGE_RE = re.compile(
    r"▲\s*閱讀下文\s*[，,]\s*回答第\s*(\d+)\s*[-－~～]\s*(\d+)\s*題\s*(.*)$"
)
ANSWER_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}
MATERIAL_OVERRIDES: dict[str, dict[int, list[dict[str, Any]]]] = {
    "109": {
        34: [{
            "type": "table",
            "title": "表（一）產量及總成本",
            "headers": ["Q", "3", "4", "5", "6", "7", "8"],
            "rows": [["TC", "80", "100", "125", "156", "210", "320"]],
        }],
    },
}


def find_answer_pdf(source_dir: Path, year: str) -> Path:
    year_dir = source_dir / year
    matches = [p for p in year_dir.glob("*.pdf") if p.name.endswith(ANSWER_PDF_SUFFIX)]
    if len(matches) != 1:
        names = ", ".join(p.name for p in matches) or "(none)"
        raise FileNotFoundError(f"Expected exactly one answer PDF in {year_dir}; found {names}")
    return matches[0]


def extract_answers(answer_pdf: Path) -> dict[int, int | None]:
    fitz = load_fitz()
    answers: dict[int, int | None] = {}
    with fitz.open(str(answer_pdf)) as doc:
        tokens: list[str] = []
        for page in doc:
            tokens.extend((page.get_text("text") or "").split())

    for idx, token in enumerate(tokens[:-1]):
        if not token.isdigit():
            continue
        qid = int(token)
        if not 1 <= qid <= 50:
            continue
        nxt = tokens[idx + 1].strip().upper()
        if nxt in ANSWER_MAP:
            answers[qid] = ANSWER_MAP[nxt]
        elif "送分" in nxt:
            answers[qid] = None
    return answers


def clean_text(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\u200b", "")
    text = text.replace("不", "不").replace("列", "列").replace("金", "金")
    text = text.replace("ˉ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"【以下空白】.*$", "", text).strip()
    return text


def strip_question_number(text: str, qid: int) -> str:
    match = re.search(rf"{qid}\s*[.．]\s*", text)
    if match:
        return text[match.end():].strip()
    return text.strip()


def parse_question_text(raw: str, qid: int) -> tuple[str, list[str], list[str]]:
    text = strip_question_number(clean_text(raw), qid)
    parts = OPTION_RE.split(text)
    warnings: list[str] = []

    if len(parts) < 9:
        return text, [], [f"expected 4 options, parsed {max(0, (len(parts) - 1) // 2)}"]

    question = parts[0].strip()
    options_by_letter: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        letter = parts[i]
        option_text = MATERIAL_TAIL_RE.sub("", parts[i + 1].strip()).strip()
        options_by_letter[letter] = option_text

    options = [options_by_letter.get(letter, "") for letter in ("A", "B", "C", "D")]
    if any(not opt for opt in options):
        warnings.append("one or more options are empty")

    # If a following footer or accidental extra text was included, trim after D
    # has already been isolated by the option splitter.
    return question, options, warnings


def needs_image_material(question: str) -> bool:
    return any(pattern.search(question) for pattern in MATERIAL_PATTERNS)


def get_material_override(year: str, qid: int) -> list[dict[str, Any]]:
    return copy.deepcopy(MATERIAL_OVERRIDES.get(year, {}).get(qid, []))


def apply_reading_passages(questions: list[dict[str, Any]], report: list[dict[str, Any]]) -> None:
    by_id = {q["id"]: q for q in questions}
    report_by_id = {row["id"]: row for row in report}

    for q in questions:
        for opt_index, option in enumerate(q.get("options", [])):
            match = READING_PASSAGE_RE.search(option)
            if not match:
                continue

            start_id = int(match.group(1))
            end_id = int(match.group(2))
            passage = match.group(3).strip()
            q["options"][opt_index] = option[:match.start()].strip()

            material = {
                "type": "text",
                "title": f"閱讀資料（第 {start_id}-{end_id} 題）",
                "content": passage,
            }
            group_id = f"reading-{start_id}-{end_id}"

            for target_id in range(start_id, end_id + 1):
                target = by_id.get(target_id)
                if not target:
                    continue
                target["group"] = group_id
                materials = target.setdefault("materials", [])
                if not any(m.get("title") == material["title"] and m.get("content") == material["content"] for m in materials):
                    materials.insert(0, material)
                report_by_id.get(target_id, {}).setdefault("warnings", []).append(
                    f"attached shared reading passage from Q{q['id']}"
                )

            report_by_id.get(q["id"], {}).setdefault("warnings", []).append(
                f"removed shared reading passage from option {chr(65 + opt_index)}"
            )


def read_clip_text(pdf_path: Path, crop: dict[str, Any]) -> str:
    fitz = load_fitz()
    with fitz.open(str(pdf_path)) as doc:
        page = doc[crop["page"] - 1]
        clip = fitz.Rect(*crop["clip"])
        return page.get_text("text", clip=clip) or ""


def build_bank(year: str, source_dir: Path, asset_root: Path, crop_out: Path, include_all_images: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    question_pdf = find_question_pdf(source_dir, year)
    answer_pdf = find_answer_pdf(source_dir, year)
    answers = extract_answers(answer_pdf)
    crops = crop_questions(
        pdf_path=question_pdf,
        out_dir=crop_out,
        dpi=180,
        x_margin=10,
        top_margin=8,
        bottom_gap=8,
    )

    asset_dir = asset_root / "tvee" / year
    asset_dir.mkdir(parents=True, exist_ok=True)

    questions: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []

    for crop in crops:
        raw = read_clip_text(question_pdf, {"page": crop.page, "clip": crop.clip}) if crop.image else ""
        question, options, warnings = parse_question_text(raw, crop.id)
        warnings.extend(crop.warnings)

        answer = answers.get(crop.id)
        if answer is None:
            warnings.append("answer is marked as free score; using A as placeholder")
            answer = 0
        elif answer is None or crop.id not in answers:
            warnings.append("answer not found; using A as placeholder")
            answer = 0

        item: dict[str, Any] = {
            "question": question,
            "options": options,
            "answer": answer,
            "id": crop.id,
        }

        material_override = get_material_override(year, crop.id)
        if material_override:
            item["materials"] = material_override

        add_image = include_all_images or (not material_override and needs_image_material(question))
        if add_image and crop.image:
            asset_path = asset_dir / f"q{crop.id:02d}.png"
            shutil.copyfile(crop_out / crop.image, asset_path)
            item.setdefault("materials", []).append({
                "type": "image",
                "title": f"第 {crop.id} 題附圖",
                "src": str(asset_path.as_posix()),
                "alt": f"{year} 統測專二第 {crop.id} 題截圖",
            })

        questions.append(item)
        report.append({
            "id": crop.id,
            "options": len(options),
            "answer": answer,
            "has_material": bool(item.get("materials")),
            "warnings": warnings,
            "preview": question[:100],
        })

    apply_reading_passages(questions, report)
    for row, item in zip(report, questions):
        row["has_material"] = bool(item.get("materials"))

    return questions, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TVE question bank JSON from PDFs.")
    parser.add_argument("--year", required=True, help="Exam year, e.g. 109.")
    parser.add_argument("--source-dir", type=Path, default=Path(DEFAULT_SOURCE_DIR))
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    parser.add_argument("--crop-out", type=Path, help="Temporary crop output directory.")
    parser.add_argument("--out", type=Path, help="Output JSON path.")
    parser.add_argument("--report", type=Path, help="Parse report JSON path.")
    parser.add_argument("--include-all-images", action="store_true", help="Attach full-question image to every question.")
    parser.add_argument("--write", action="store_true", help="Write output files.")
    args = parser.parse_args()

    crop_out = args.crop_out or Path("C:/tmp") / f"tvee_{args.year}_build_crops"
    out_path = args.out or Path("questions") / f"{args.year}統測專二-會計學與經濟學.json"
    report_path = args.report or Path("C:/tmp") / f"tvee_{args.year}_parse_report.json"

    questions, report = build_bank(
        year=args.year,
        source_dir=args.source_dir,
        asset_root=args.assets,
        crop_out=crop_out,
        include_all_images=args.include_all_images,
    )

    failed = [r for r in report if r["options"] != 4 or r["warnings"]]
    print(f"Built {len(questions)} questions for {args.year}")
    print(f"Questions with materials: {sum(1 for q in questions if q.get('materials'))}")
    print(f"Questions needing review: {len(failed)}")
    for row in failed[:20]:
        print(f"  Q{row['id']:02d}: options={row['options']} warnings={row['warnings']} preview={row['preview']}")

    if args.write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")
        print(f"Wrote {report_path}")
    else:
        print("Dry run only. Add --write to save files.")

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
