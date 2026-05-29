from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ANSWER_RE = re.compile(r"(?:【([^】]+)】|\[([^\]]+)\])\s*(\d{1,2})[.．]")
OPTION_RE = re.compile(r"([①②③④ÅÇÉÑ\uf081\uf082\uf083\uf084])")
MARKER_MAP = str.maketrans(
    {
        "Å": "①",
        "Ç": "②",
        "É": "③",
        "Ñ": "④",
        "\uf081": "①",
        "\uf082": "②",
        "\uf083": "③",
        "\uf084": "④",
    }
)
OPTION_INDEX = {"①": 0, "②": 1, "③": 2, "④": 3}
CROSS_REF_RE = re.compile(r"(?:^|[（(,，、\s])[A-D](?:[）),，、\s]|$)")
LOCK_OPTION_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"選項\([A-D]\)",
        r"選項[一二三四1234]",
        r"以上皆",
        r"皆是",
        r"皆非",
        r"皆正確",
        r"皆錯誤",
    )
]
TEXT_REPLACEMENTS = {
    "": "→",
    "": "÷",
    "": "L",
    "理": "理",
    "利": "利",
    "流": "流",
    "離": "離",
}


def normalize_text(text: str) -> str:
    text = text.translate(MARKER_MAP)
    for old, new in TEXT_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.replace("\u00a0", " ")
    text = text.replace("´", "×")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ,", ",").replace(" .", ".")
    text = clean_pdf_math_artifacts(text)
    return text


def clean_pdf_math_artifacts(text: str) -> str:
    text = re.sub(r"(\d+)\s*[×xX]\s*10\s*元([、，,])\s*6\b", r"\1×10^6 元\2", text)
    text = re.sub(
        r"(\d+)\s*[×xX]\s*10\s*元，效益分別為6\b",
        r"\1×10^6 元，效益分別為",
        text,
    )
    text = re.sub(
        r"(\d+)\s*[×xX]\s*10\s*元，今若資金充裕6\b",
        r"\1×10^6 元，今若資金充裕",
        text,
    )
    text = re.sub(r"(\d+)\s*[×xX]\s*10\s*元\b", r"\1×10 元", text)
    return text


def item_x(item: dict[str, Any]) -> float:
    return float(item.get("x") or 0)


def item_y(item: dict[str, Any]) -> float:
    return float(item.get("y") or 0)


def item_center_x(item: dict[str, Any]) -> float:
    return item_x(item) + float(item.get("width") or 0) / 2


def group_items_into_rows(items: list[dict[str, Any]], tolerance: float = 4.0) -> list[str]:
    rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda it: (item_y(it), item_x(it))):
        y = item_y(item)
        for row in rows:
            if abs(y - row["y"]) <= tolerance:
                row["items"].append(item)
                count = len(row["items"])
                row["y"] = ((row["y"] * (count - 1)) + y) / count
                break
        else:
            rows.append({"y": y, "items": [item]})

    texts: list[str] = []
    for row in sorted(rows, key=lambda r: r["y"]):
        pieces = [
            normalize_text(str(item.get("text") or ""))
            for item in sorted(row["items"], key=item_x)
        ]
        text = normalize_text(" ".join(piece for piece in pieces if piece))
        if text:
            texts.append(text)
    return texts


def page_column_texts(page: dict[str, Any]) -> list[str]:
    width = float(page.get("width") or 0)
    split_x = width / 2 if width else 0
    columns: list[list[dict[str, Any]]] = [[], []]

    for item in page.get("text_items") or []:
        raw_text = str(item.get("text") or "")
        x = item_x(item)
        item_width = float(item.get("width") or 0)
        answer_match = ANSWER_RE.search(raw_text)
        if x < split_x < x + item_width and answer_match and answer_match.start() > 0:
            prefix = item.copy()
            prefix["text"] = raw_text[: answer_match.start()]
            prefix["width"] = max(1.0, split_x - x)

            suffix = item.copy()
            suffix["text"] = raw_text[answer_match.start() :]
            suffix_x = x + item_width * (answer_match.start() / max(1, len(raw_text)))
            suffix["x"] = max(split_x + 1, suffix_x)
            suffix["width"] = max(1.0, x + item_width - float(suffix["x"]))
            columns[0].append(prefix)
            columns[1].append(suffix)
            continue

        col = 0 if item_center_x(item) < split_x else 1
        columns[col].append(item)

    texts: list[str] = []
    for col_items in columns:
        active = False
        for text in group_items_into_rows(col_items):
            if not text:
                continue
            if re.search(r"[貳贰]、", text):
                break
            if "壹、" in text or "壹." in text:
                active = True
                continue
            if ANSWER_RE.search(text):
                active = True
            if active:
                texts.append(text)
    return texts


def split_option_segments(text: str) -> tuple[str, list[tuple[str, str]]]:
    text = normalize_text(text)
    matches = list(OPTION_RE.finditer(text))
    if not matches:
        return text, []

    before = text[: matches[0].start()].strip()
    segments: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        marker = normalize_text(match.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[match.end() : end].strip()
        segments.append((marker, value))
    return before, segments


def parse_answer(raw: str) -> tuple[int, bool]:
    raw = normalize_text(raw)
    if raw in {"1", "2", "3", "4"}:
        return int(raw) - 1, False
    return 0, True


def append_text(parts: list[str], text: str) -> None:
    text = normalize_text(text)
    if text:
        parts.append(text)


def should_lock_options(options: list[str]) -> bool:
    compact = [re.sub(r"\s+", "", option).upper() for option in options]
    if compact in (["A", "B", "C", "D"], ["1", "2", "3", "4"]):
        return True
    return any(CROSS_REF_RE.search(option.upper()) for option in options) or any(
        pattern.search(option) for option in options for pattern in LOCK_OPTION_PATTERNS
    )


def rebalance_repeated_unit_suffix(options: list[str]) -> list[str]:
    if len(options) != 4:
        return options
    last = options[-1]
    repeated_ha = re.search(r"(?:\s*/ha){4}$", last)
    if repeated_ha and all(re.search(r"\bm3$", option) for option in options[:3]):
        return [
            normalize_text(option + "/ha") for option in options[:3]
        ] + [normalize_text(last[: repeated_ha.start()] + "/ha")]
    return options


def clean_field(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("【請接續背面】", "")
    text = text.replace("請接續背面", "")
    text = text.replace(" /", "/")
    text = text.replace("( ", "(").replace(" )", ")")
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"([、，。；：）])\s+(?=[\u4e00-\u9fffA-Za-z0-9])", r"\1", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+([（(])", r"\1", text)
    return text.strip(" \t\n:")


def parse_questions(texts: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        question = clean_field(" ".join(current.pop("_question_parts")))
        options = rebalance_repeated_unit_suffix(
            [clean_field(opt) for opt in current.pop("_options")]
        )
        item = {
            "id": current["id"],
            "question": question,
            "options": options,
            "answer": current["answer"],
        }
        if current["freeScore"]:
            item["freeScore"] = True
        if should_lock_options(options):
            item["noShuffle"] = True
        questions.append(item)
        current = None

    def add_piece(piece: str) -> None:
        if current is None:
            return
        before, opts = split_option_segments(piece)
        if before:
            if current["_options"]:
                current["_options"][-1] = normalize_text(
                    current["_options"][-1] + " " + before
                )
            else:
                append_text(current["_question_parts"], before)
        for marker, value in opts:
            index = OPTION_INDEX.get(marker)
            if index is None:
                continue
            while len(current["_options"]) < index:
                current["_options"].append("")
            if len(current["_options"]) == index:
                current["_options"].append(value)
            else:
                current["_options"][index] = normalize_text(
                    current["_options"][index] + " " + value
                )

    for text in texts:
        remaining = text
        while True:
            match = ANSWER_RE.search(remaining)
            if not match:
                add_piece(remaining)
                break

            prefix = remaining[: match.start()]
            add_piece(prefix)
            finish()

            raw_answer = match.group(1) or match.group(2) or ""
            answer, free_score = parse_answer(raw_answer)
            current = {
                "id": int(match.group(3)),
                "answer": answer,
                "freeScore": free_score,
                "_question_parts": [],
                "_options": [],
            }
            remaining = remaining[match.end() :]
            if not remaining:
                break

    finish()
    return sorted(questions, key=lambda item: item["id"])


def convert(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    texts: list[str] = []
    for page in data.get("pages") or []:
        texts.extend(page_column_texts(page))
    return parse_questions(texts)


def qa_entry(source: Path, questions: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [q["id"] for q in questions]
    expected = set(range(1, 16))
    seen = set(ids)
    duplicate_ids = sorted({qid for qid in ids if ids.count(qid) > 1})
    bad_option_count = [
        q["id"] for q in questions if len(q.get("options") or []) != 4
    ]
    empty_fields = [
        q["id"]
        for q in questions
        if not q.get("question")
        or len(q.get("options") or []) != 4
        or any(not opt for opt in q.get("options") or [])
    ]
    answer_out_of_range = [
        q["id"]
        for q in questions
        if not q.get("freeScore") and q.get("answer") not in {0, 1, 2, 3}
    ]
    suspicious_items = []
    suspicious_re = re.compile(r"�|[ÅÇÉÑ]|[\uf081-\uf084]|×10 元|/ha /ha|題目[一二三四五六]|請接續")
    for q in questions:
        blob = " ".join([q.get("question", ""), *(q.get("options") or [])])
        if suspicious_re.search(blob):
            suspicious_items.append(q["id"])
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
        if len(questions) == 15
        and not (expected - seen)
        and not (seen - expected)
        and not duplicate_ids
        and not bad_option_count
        and not empty_fields
        and not answer_out_of_range
        and not suspicious_items
        else "review",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for path in args.inputs:
        questions = convert(path)
        out = args.output_dir / f"{path.stem}.questions.json"
        out.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        entry = qa_entry(path, questions)
        entry["output"] = str(out)
        report.append(entry)
        print(f"{path.name}: {entry['status']} {entry['count']} questions")

    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
