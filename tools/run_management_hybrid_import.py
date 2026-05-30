#!/usr/bin/env python3
"""Run the preferred local pipeline for irrigation-management exam PDFs.

The pipeline is intentionally conservative:
1. Use LiteParse JSON coordinates as the primary source when PDFs contain text.
2. Convert the spatial text into quiz JSON.
3. Validate structure and compare against existing/VL reference outputs.
4. Write everything to .tmp; never overwrite the production question banks.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from convert_liteparse_questions import convert, qa_entry
from normalize_question_spacing import normalize_question_item

try:
    from import_management_questions import parse_tve_question_bank
except ImportError:
    parse_tve_question_bank = None

try:
    from crop_tvee_materials import crop_materials
    from crop_tvee_questions import crop_questions
except ImportError:
    crop_materials = None
    crop_questions = None


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "農水_管理組考題" / "農水_管理組考題"
QUESTION_DIR = BASE_DIR / "questions"


@dataclass(frozen=True)
class EmbeddedAnswerBank:
    pdf: str
    output: str


@dataclass(frozen=True)
class TveBank:
    question_pdf: str
    answer_pdf: str
    output: str


EMBEDDED_ANSWER_BANKS = [
    EmbeddedAnswerBank("水利灌溉/102灌溉排水概要題和答.pdf", "102_不分職等-灌溉管理人員(灌溉管理組)-灌溉排水概要.json"),
    EmbeddedAnswerBank("水利灌溉/105_不分職等-灌溉管理人員(灌溉管理組)-灌溉排水概要.pdf", "105_不分職等-灌溉管理人員(灌溉管理組)-灌溉排水概要.json"),
    EmbeddedAnswerBank("水利灌溉/109 不分職等-灌溉管理人員(灌溉管理組)_-農田灌溉排水概要.pdf", "109_不分職等-灌溉管理人員(灌溉管理組)-農田灌溉排水概要.json"),
    EmbeddedAnswerBank("水利灌溉/111灌溉排水概要題和答.pdf", "111_灌溉管理組-農田灌溉排水概要.json"),
    EmbeddedAnswerBank("水利灌溉/113農田灌溉排水概要.pdf", "113農田水利署-農田灌溉排水概要.json"),
    EmbeddedAnswerBank("水利農概/102農業概要題和答.pdf", "102_不分職等-灌溉管理人員(灌溉管理組)-農業概論.json"),
    EmbeddedAnswerBank("水利農概/105_不分職等-灌溉管理人員(灌溉管理組)-農業概論.pdf", "105_不分職等-灌溉管理人員(灌溉管理組)-農業概論.json"),
    EmbeddedAnswerBank("水利農概/109 不分職等-灌溉管理人員(灌溉管理組)_-農業概論.pdf", "109_不分職等-灌溉管理人員(灌溉管理組)-農業概論.json"),
    EmbeddedAnswerBank("水利農概/111農業概論.pdf", "111_灌溉管理組-農業概論.json"),
    EmbeddedAnswerBank("水利農概/113農業概論.pdf", "113農田水利署-農業概論.json"),
]

TVE_BANKS = [
    TveBank("統測農概/112學年度農業群專業科目(二)試題.pdf", "統測農概/112學年度農業群專業科目(二)公告答案.pdf", "112統測農概-農業概論.json"),
    TveBank("統測農概/113學年度農業群專業科目(二)試題.pdf", "統測農概/113學年度農業群專業科目(二)答案.pdf", "113統測農概-農業概論.json"),
    TveBank("統測農概/114學年度農業群專業科目(二)試題.pdf", "統測農概/114學年度農業群專業科目(二)標準答案.pdf", "114統測農概-農業概論.json"),
    TveBank("統測農概/115學年度農業群專業科目(二)試題.pdf", "統測農概/115學年度農業群專業科目(二)公告答案.pdf", "115統測農概-農業概論.json"),
]


DEFAULT_OUTPUT_DIR = BASE_DIR / ".tmp" / "hybrid-management-import"
DEFAULT_VL_DIR = BASE_DIR / ".tmp" / "paddleocr-vl-output" / "management-best-questions"


def normalize_question_spacing(questions: list[dict[str, Any]]) -> None:
    for item in questions:
        normalize_question_item(item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--vl-dir", type=Path, default=DEFAULT_VL_DIR)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--force", action="store_true", help="Regenerate LiteParse JSON.")
    parser.add_argument(
        "--no-compare-vl",
        action="store_true",
        help="Skip comparison against existing PaddleOCR-VL temp outputs.",
    )
    parser.add_argument("--assets", type=Path, default=BASE_DIR / "assets")
    parser.add_argument("--skip-tve", action="store_true", help="Only run the 10 management PDFs.")
    return parser.parse_args()


def lit_exe() -> str:
    sibling = Path(sys.executable).with_name("lit.exe")
    if sibling.exists():
        return str(sibling)
    found = shutil.which("lit")
    if found:
        return found
    raise RuntimeError("Could not find lit.exe. Install liteparse in this Python environment.")


def run_liteparse(pdf: Path, output: Path, dpi: int, force: bool) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not force and output.exists():
        return {"ran": False, "returncode": 0, "stdout": "", "stderr": ""}

    cmd = [
        lit_exe(),
        "parse",
        str(pdf),
        "--format",
        "json",
        "--no-ocr",
        "--preserve-small-text",
        "--dpi",
        str(dpi),
        "-o",
        str(output),
    ]
    proc = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "ran": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def load_questions(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


def norm(text: Any) -> str:
    text = str(text or "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("／", "/")
    return text


def compare_questions(
    candidate: list[dict[str, Any]], reference: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    if reference is None:
        return None
    cand_by_id = {item.get("id"): item for item in candidate}
    ref_by_id = {item.get("id"): item for item in reference}
    ids = sorted(set(cand_by_id) | set(ref_by_id))
    answer_mismatches = []
    question_diffs = []
    option_diffs = []
    missing_in_candidate = []
    extra_in_candidate = []

    for qid in ids:
        cand = cand_by_id.get(qid)
        ref = ref_by_id.get(qid)
        if cand is None:
            missing_in_candidate.append(qid)
            continue
        if ref is None:
            extra_in_candidate.append(qid)
            continue
        if cand.get("answer") != ref.get("answer") or bool(cand.get("freeScore")) != bool(ref.get("freeScore")):
            answer_mismatches.append(qid)
        if norm(cand.get("question")) != norm(ref.get("question")):
            question_diffs.append(qid)
        cand_options = [norm(option) for option in cand.get("options", [])]
        ref_options = [norm(option) for option in ref.get("options", [])]
        if cand_options != ref_options:
            option_diffs.append(qid)

    return {
        "reference_count": len(reference),
        "answer_mismatches": answer_mismatches,
        "question_diffs": question_diffs,
        "option_diffs": option_diffs,
        "missing_in_candidate": missing_in_candidate,
        "extra_in_candidate": extra_in_candidate,
    }


def remove_tail_markers(text: str) -> str:
    text = re.sub(r"\s*【以下空白】\s*$", "", str(text or ""))
    text = re.sub(r"\s*【請接續背面】\s*$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def attach_material(item: dict[str, Any], material: dict[str, Any]) -> None:
    materials = item.setdefault("materials", [])
    if not any(
        m.get("type") == material.get("type")
        and m.get("title") == material.get("title")
        and m.get("src") == material.get("src")
        and m.get("content") == material.get("content")
        for m in materials
    ):
        materials.append(material)


def attach_image_material(
    item: dict[str, Any],
    year: str,
    pdf_path: Path,
    asset_root: Path,
    crop_root: Path,
    full_question: bool = False,
) -> list[str]:
    if crop_materials is None or crop_questions is None:
        return ["crop tools unavailable; image material not attached"]

    qid = int(item["id"])
    crop_dir = crop_root / f"{year}_q{qid:02d}"
    if full_question:
        crops = crop_questions(
            pdf_path=pdf_path,
            out_dir=crop_dir / "question_crops",
            dpi=220,
            x_margin=10,
            top_margin=8,
            bottom_gap=8,
        )
        crop = next((candidate for candidate in crops if candidate.id == qid), None)
        source = (crop_dir / "question_crops" / crop.image) if crop and crop.image else None
    else:
        crops = crop_materials(
            pdf_path=pdf_path,
            out_dir=crop_dir,
            qids={qid},
            dpi=220,
            margin=8,
            text_distance=28,
        )
        crop = next((candidate for candidate in crops if candidate.id == qid), None)
        source = (crop_dir / crop.image) if crop and crop.image else None
    if crop is None or not crop.image or source is None:
        return [f"no image crop generated for Q{qid}"]
    asset_rel = Path("assets") / "tvee-agri" / year / f"q{qid:02d}.png"
    asset_path = asset_root / "tvee-agri" / year / f"q{qid:02d}.png"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, asset_path)
    attach_material(
        item,
        {
            "type": "image",
            "title": f"第 {qid} 題附圖",
            "src": asset_rel.as_posix(),
            "alt": f"{year} 統測農概第 {qid} 題附圖",
        },
    )
    return crop.warnings


def postprocess_tve_agri_materials(
    year: str,
    questions: list[dict[str, Any]],
    pdf_path: Path,
    asset_root: Path,
    crop_root: Path,
) -> dict[str, Any]:
    by_id = {int(q["id"]): q for q in questions if isinstance(q.get("id"), int)}
    warnings: dict[int, list[str]] = {}

    for q in questions:
        q["question"] = remove_tail_markers(q.get("question", ""))
        q["options"] = [remove_tail_markers(opt) for opt in q.get("options", [])]

    reading_re = re.compile(r"▲\s*閱讀下文\s*[，,]\s*回答第\s*(\d+)\s*[-－–~～]\s*(\d+)\s*題\s*(.*)")
    for source in questions:
        options = source.get("options") or []
        for index, option in enumerate(list(options)):
            match = reading_re.search(option)
            if not match:
                continue
            start_id = int(match.group(1))
            end_id = int(match.group(2))
            content = remove_tail_markers(match.group(3))
            options[index] = remove_tail_markers(option[: match.start()])
            title = f"閱讀資料（第 {start_id}-{end_id} 題）"
            group = f"reading-{start_id}-{end_id}"
            for qid in range(start_id, end_id + 1):
                if qid not in by_id:
                    continue
                by_id[qid]["group"] = group
                attach_material(
                    by_id[qid],
                    {
                        "type": "text",
                        "title": title,
                        "content": content,
                    },
                )
            warnings.setdefault(int(source["id"]), []).append(
                f"moved shared reading passage from option {index + 1} to Q{start_id}-Q{end_id} materials"
            )

    if year == "112":
        q47 = by_id.get(47)
        if q47 and len(q47.get("options", [])) == 4:
            option4 = q47["options"][3]
            marker = option4.find("▲閱讀下文")
            if marker != -1:
                q47["options"][3] = remove_tail_markers(option4[:marker])
                warnings.setdefault(47, []).append(
                    "moved shared reading/table material from option D to Q48-Q50 materials"
                )

        shared_table = {
            "type": "table",
            "title": "表（一）快樂有機農場病蟲草害觀察紀錄",
            "headers": ["病害", "蟲害", "雜草"],
            "rows": [
                ["① 玉米露菌病", "① 斜紋夜盜蛾", "① 野茨菰"],
                ["② 馬鈴薯晚疫病", "② 蚜蟲", "② 蘋草"],
                ["③ 胡瓜嵌紋病", "③ 東方果實蠅", "③ 牛筋草"],
                ["④ 番茄青枯病", "④ 椿象", "④ 鴨舌草"],
                ["⑤ 水稻稻熱病", "⑤ 浮塵子", "⑤ 香附子"],
                ["⑥ 水稻黃萎病", "⑥ 介殼蟲", "⑥ 野莧"],
                ["⑦ 蔬菜軟腐病", "⑦ 飛蝨", "⑦ 霍香薊"],
                ["⑧ 木瓜輪點病", "⑧ 蝗蟲", "⑧ 紅骨草"],
                ["⑨ 甘藷簇葉病", "", ""],
            ],
            "notes": "快樂有機農場場主將近年來田間栽培管理發現之病蟲草害紀錄，提供新聘雇之農校畢業生凱恩以協助改善農場問題。",
        }
        for qid in (48, 49, 50):
            if qid in by_id:
                by_id[qid]["group"] = "reading-48-50"
                attach_material(by_id[qid], shared_table)

        if 28 in by_id:
            warnings.setdefault(28, []).extend(
                attach_image_material(by_id[28], year, pdf_path, asset_root, crop_root, full_question=True)
            )

    if year == "113":
        q37 = by_id.get(37)
        if q37 and len(q37.get("options", [])) == 4:
            q37["options"][3] = "水色"
            attach_material(
                q37,
                {
                    "type": "table",
                    "title": "廢水檢驗結果",
                    "headers": ["檢驗項目", "檢驗結果"],
                    "rows": [
                        ["BOD（生化需氧量）", "234 ppm"],
                        ["COD（化學需氧量）", "456 ppm"],
                        ["SS（懸浮固形物）", "106 ppm"],
                        ["水色", "澄清、無色、無異味"],
                    ],
                },
            )
            warnings.setdefault(37, []).append("moved inspection table from option D to materials")

    if year == "115":
        q11 = by_id.get(11)
        if q11 and q11.get("options"):
            q11["options"][0] = remove_tail_markers(
                re.sub(r"\s*圖\s*[（(]\s*一\s*[)）]\s*$", "", q11["options"][0])
            )
            warnings.setdefault(11, []).extend(
                attach_image_material(q11, year, pdf_path, asset_root, crop_root)
            )

    return {"warnings": {str(k): v for k, v in warnings.items() if v}}


def qa_expected(source: Path, questions: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    ids = [q.get("id") for q in questions]
    expected = set(range(1, expected_count + 1))
    seen = set(qid for qid in ids if isinstance(qid, int))
    duplicate_ids = sorted({qid for qid in ids if ids.count(qid) > 1})
    bad_option_count = [
        q.get("id") for q in questions if len(q.get("options") or []) != 4
    ]
    empty_fields = [
        q.get("id")
        for q in questions
        if not q.get("question")
        or len(q.get("options") or []) != 4
        or any(not opt for opt in q.get("options") or [])
    ]
    answer_out_of_range = [
        q.get("id")
        for q in questions
        if not q.get("freeScore") and q.get("answer") not in {0, 1, 2, 3}
    ]
    suspicious_items = []
    suspicious_re = re.compile(r"請接續|以下空白|▲閱讀下文|圖\s*[（(]\s*一\s*[)）]\s*$")
    for q in questions:
        blob = " ".join([q.get("question", ""), *(q.get("options") or [])])
        if suspicious_re.search(blob):
            suspicious_items.append(q.get("id"))
    return {
        "source": str(source),
        "count": len(questions),
        "ids": ids,
        "missing_ids": sorted(expected - seen),
        "extra_ids": sorted(seen - expected),
        "duplicate_ids": duplicate_ids,
        "bad_option_count": bad_option_count,
        "empty_fields": empty_fields,
        "answer_out_of_range": answer_out_of_range,
        "suspicious_items": suspicious_items,
        "status": "ok"
        if len(questions) == expected_count
        and not (expected - seen)
        and not (seen - expected)
        and not duplicate_ids
        and not bad_option_count
        and not empty_fields
        and not answer_out_of_range
        and not suspicious_items
        else "review",
    }


def count_text_items(liteparse_json: Path) -> int:
    data = json.loads(liteparse_json.read_text(encoding="utf-8"))
    return sum(len(page.get("text_items") or []) for page in data.get("pages") or [])


def report_status(
    qa: dict[str, Any],
    existing_compare: dict[str, Any] | None,
    vl_compare: dict[str, Any] | None,
) -> str:
    if qa["status"] != "ok":
        return "review"
    for compare in (existing_compare, vl_compare):
        if compare is None:
            continue
        if compare["answer_mismatches"] or compare["missing_in_candidate"] or compare["extra_in_candidate"]:
            return "review"
    return "ok"


def write_markdown_summary(report: list[dict[str, Any]], output: Path) -> None:
    ok_count = sum(1 for item in report if item["final_status"] == "ok")
    total_questions = sum(item["qa"]["count"] for item in report)
    lines = [
        "# Hybrid Management Import Report",
        "",
        f"- files: {len(report)}",
        f"- ok: {ok_count}",
        f"- review: {len(report) - ok_count}",
        f"- questions: {total_questions}",
        "",
        "| file | status | questions | existing answer diffs | VL answer diffs | notes |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in report:
        existing = item.get("compare_existing") or {}
        vl = item.get("compare_vl") or {}
        notes = []
        if item["qa"].get("suspicious_items"):
            notes.append("suspicious " + ",".join(map(str, item["qa"]["suspicious_items"])))
        if existing.get("question_diffs"):
            notes.append(f"existing text diffs {len(existing['question_diffs'])}")
        if vl.get("question_diffs"):
            notes.append(f"VL text diffs {len(vl['question_diffs'])}")
        lines.append(
            "| {file} | {status} | {count} | {existing_answers} | {vl_answers} | {notes} |".format(
                file=item["target"],
                status=item["final_status"],
                count=item["qa"]["count"],
                existing_answers=len(existing.get("answer_mismatches", [])),
                vl_answers=len(vl.get("answer_mismatches", [])),
                notes="; ".join(notes),
            )
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    liteparse_dir = args.output_dir / "liteparse-json"
    question_dir = args.output_dir / "questions"
    question_dir.mkdir(parents=True, exist_ok=True)

    report = []
    for bank in EMBEDDED_ANSWER_BANKS:
        pdf = SOURCE_DIR / bank.pdf
        target = Path(bank.output)
        liteparse_json = liteparse_dir / f"{target.stem}.liteparse.json"
        run = run_liteparse(pdf, liteparse_json, args.dpi, args.force)
        if run["returncode"] != 0:
            report.append(
                {
                    "target": bank.output,
                    "pdf": str(pdf),
                    "liteparse_json": str(liteparse_json),
                    "final_status": "review",
                    "error": run,
                }
            )
            print(f"{bank.output}: liteparse failed")
            continue

        questions = convert(liteparse_json)
        normalize_question_spacing(questions)
        out_questions = question_dir / target.name
        out_questions.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        qa = qa_entry(liteparse_json, questions)
        existing = load_questions(QUESTION_DIR / target.name)
        compare_existing = compare_questions(questions, existing)
        vl_questions = None
        if not args.no_compare_vl:
            vl_questions = load_questions(args.vl_dir / f"{pdf.stem}.questions.json")
        compare_vl = compare_questions(questions, vl_questions)
        final_status = report_status(qa, compare_existing, compare_vl)

        entry = {
            "target": bank.output,
            "pdf": str(pdf),
            "text_items": count_text_items(liteparse_json),
            "liteparse_json": str(liteparse_json),
            "output": str(out_questions),
            "qa": qa,
            "compare_existing": compare_existing,
            "compare_vl": compare_vl,
            "final_status": final_status,
        }
        report.append(entry)
        print(f"{bank.output}: {final_status} {len(questions)} questions")

    if not args.skip_tve:
        for bank in TVE_BANKS:
            target = Path(bank.output)
            out_questions = question_dir / target.name
            if parse_tve_question_bank is None:
                report.append(
                    {
                        "target": bank.output,
                        "source_kind": "tve",
                        "question_pdf": str(SOURCE_DIR / bank.question_pdf),
                        "answer_pdf": str(SOURCE_DIR / bank.answer_pdf),
                        "final_status": "review",
                        "error": "pypdf is required for TVE parsing",
                    }
                )
                print(f"{bank.output}: review missing pypdf")
                continue

            questions = parse_tve_question_bank(
                SOURCE_DIR / bank.question_pdf,
                SOURCE_DIR / bank.answer_pdf,
            )
            year = bank.output[:3]
            material_report = postprocess_tve_agri_materials(
                year=year,
                questions=questions,
                pdf_path=SOURCE_DIR / bank.question_pdf,
                asset_root=args.assets,
                crop_root=args.output_dir / "material-crops",
            )
            normalize_question_spacing(questions)
            out_questions.write_text(
                json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            qa = qa_expected(SOURCE_DIR / bank.question_pdf, questions, 50)
            existing = load_questions(QUESTION_DIR / target.name)
            compare_existing = compare_questions(questions, existing)
            final_status = report_status(qa, compare_existing, None)
            entry = {
                "target": bank.output,
                "source_kind": "tve",
                "question_pdf": str(SOURCE_DIR / bank.question_pdf),
                "answer_pdf": str(SOURCE_DIR / bank.answer_pdf),
                "output": str(out_questions),
                "qa": qa,
                "compare_existing": compare_existing,
                "compare_vl": None,
                "material_report": material_report,
                "final_status": final_status,
            }
            report.append(entry)
            print(f"{bank.output}: {final_status} {len(questions)} questions")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown_summary(report, args.output_dir / "report.md")
    print(f"wrote report to {args.output_dir / 'report.md'}")
    return 0 if all(item["final_status"] == "ok" for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
