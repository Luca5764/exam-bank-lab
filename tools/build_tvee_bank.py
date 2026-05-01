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
    "110": {
        7: [{
            "type": "table",
            "title": "表（一）資產交換資料",
            "headers": ["", "X 公司汽車", "Y 公司機器"],
            "rows": [
                ["歷史成本", "$3,000,000", "$4,000,000"],
                ["累計折舊", "1,600,000", "2,000,000"],
                ["公允價值", "1,900,000", "1,800,000"],
            ],
        }],
        8: [
            {
                "type": "table",
                "title": "表（二）個別重大客戶之應收帳款及預估減損",
                "headers": ["客戶名稱", "應收帳款金額", "預估減損金額"],
                "rows": [
                    ["甲公司", "$900,000", ""],
                    ["乙公司", "1,200,000", "$400,000"],
                    ["丙公司", "700,000", "50,000"],
                ],
            },
            {
                "type": "table",
                "title": "表（三）非個別重大客戶之應收帳款",
                "headers": ["客戶名稱", "應收帳款金額"],
                "rows": [
                    ["子公司", "$120,000"],
                    ["丑公司", "80,000"],
                    ["寅公司", "100,000"],
                ],
            },
        ],
        32: [{
            "type": "table",
            "title": "表（四）產量、投入與成本",
            "headers": ["Q", "TFC", "L", "TVC", "TC", "AC", "AVC", "MC"],
            "rows": [
                ["0", "4,000", "0", "0", "X3", "", "", ""],
                ["100", "", "1", "1,000", "", "X5", "", ""],
                ["250", "", "2", "", "", "", "X6", ""],
                ["420", "X1", "3", "", "", "", "", ""],
                ["580", "", "4", "X2", "", "", "", ""],
                ["660", "", "5", "", "", "", "", "X7"],
                ["720", "", "6", "", "X4", "", "", ""],
            ],
        }],
    },
}
QUESTION_OVERRIDES: dict[str, dict[int, str]] = {
    "110": {
        7: "如表（一）為 X 公司以舊汽車交換 Y 公司舊機器，Y 公司並支付 X 公司 $100,000。下列有關資產交換之敘述何者正確？",
        8: "公司於 2018 年起，依國際會計準則對應收帳款的規定，進行減損（呆帳）提列。該公司於 2020 年 12 月 31 日，調整前備抵損失－應收帳款（備抵呆帳－應收帳款）為貸餘 $110,000。該公司有以下表（二）個別重大客戶之應收帳款金額及預估減損金額；其中甲公司之信用經個別評估後，並未發現有減損之客觀證據，故推斷甲公司之信用與以下表（三）非個別重大客戶之信用相接近。公司評估非個別重大客戶之估計呆帳率為 5%，則該公司年底之備抵損失－應收帳款（備抵呆帳－應收帳款）與預期信用減損損失（呆帳損失）金額應為多少？",
        26: "設甲國僅生產 X、Y 兩財貨，X、Y 的生產可能曲線為 PPC 如圖（一）。已知 A 點生產財貨 X 之機會成本為 2，在技術與資源不變下，則下列敘述何者正確？",
        31: "某廠商的邊際產量（MP）、平均產量（AP）兩曲線如圖（二）所示，圖中 MP 最高點為 A 點，AP 最高點為 B 點，L 為勞動投入量，且 TP 表總產量。下列敘述何者正確？",
        32: "表（四）為某廠商短期下之各種產量的要素投入數量及成本之變動關係。表中 Q 為產量，L 為勞動投入量，TFC 為總固定成本，TVC 為總變動成本，TC 為總成本，AC 為平均（總）成本，AVC 為平均變動成本，MC 為邊際成本。若變動生產要素只有勞動且其他條件不變下，下列敘述何者錯誤？",
    },
}
OPTION_OVERRIDES: dict[str, dict[int, list[str]]] = {
    "110": {
        26: [
            "若 B 點也在 PPC 線上且 Y 數量為 5，則 B 點生產 X 的機會成本小於 2",
            "C 點與 A 點相比，Y 數量相同但 X 數量較多，則 C 點具有生產效率性",
            "D 點與 A 點相比，Y 數量相同但 X 數量較少，則 D 點不具有生產效率性",
            "PPC 線為負斜率是因為機會成本遞增",
        ],
        31: [
            "L ＝ 30 時，TP 達到最大",
            "TP 最大值為 100",
            "L ＝ 20 時，廠商處於報酬遞增階段",
            "TP 最大值為 2500",
        ],
        32: [
            "X1 ＝ X2 ＝ 4,000",
            "X3 ＝ 4,000，X4 ＝ 10,000",
            "X5 ＝ 50，X6 ＝ 8，X7 ＝ 12.5",
            "MC 最低點的產量為 580",
        ],
    },
}
EXCLUDED_QUESTION_IDS: dict[str, set[int]] = {}
READING_TITLE_OVERRIDES: dict[str, dict[int, str]] = {
    "110": {
        24: "閱讀資料（第 24 題）",
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


def apply_text_overrides(year: str, item: dict[str, Any]) -> None:
    qid = item["id"]
    question = QUESTION_OVERRIDES.get(year, {}).get(qid)
    options = OPTION_OVERRIDES.get(year, {}).get(qid)
    if question:
        item["question"] = question
    if options:
        item["options"] = options


def apply_postprocess_overrides(
    year: str,
    questions: list[dict[str, Any]],
    report: list[dict[str, Any]],
    answers: dict[int, int | None],
) -> None:
    excluded = set(EXCLUDED_QUESTION_IDS.get(year, set()))
    excluded.update(qid for qid, answer in answers.items() if answer is None)
    if excluded:
        questions[:] = [q for q in questions if q["id"] not in excluded]
        report[:] = [row for row in report if row["id"] not in excluded]

    title_overrides = READING_TITLE_OVERRIDES.get(year, {})
    for q in questions:
        if q["id"] in title_overrides:
            for material in q.get("materials", []):
                if material.get("type") == "text" and str(material.get("title", "")).startswith("閱讀資料"):
                    material["title"] = title_overrides[q["id"]]

    group_counts: dict[str, int] = {}
    for q in questions:
        group = q.get("group")
        if group:
            group_counts[group] = group_counts.get(group, 0) + 1
    for q in questions:
        group = q.get("group")
        if group and group_counts.get(group, 0) <= 1:
            q.pop("group", None)


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

        item: dict[str, Any] = {
            "question": question,
            "options": options,
            "id": crop.id,
        }

        answer = answers.get(crop.id)
        if crop.id in answers and answer is None:
            warnings.append("answer is marked as free score")
            item["answer"] = None
            item["freeScore"] = True
        elif crop.id not in answers:
            warnings.append("answer not found; using A as placeholder")
            item["answer"] = 0
        else:
            item["answer"] = answer

        apply_text_overrides(year, item)

        material_override = get_material_override(year, crop.id)
        if material_override:
            item["materials"] = material_override

        add_image = include_all_images or (not material_override and needs_image_material(item["question"]))
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
            "options": len(item["options"]),
            "answer": item["answer"],
            "has_material": bool(item.get("materials")),
            "warnings": warnings,
            "preview": item["question"][:100],
        })

    apply_reading_passages(questions, report)
    apply_postprocess_overrides(year, questions, report, answers)
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
