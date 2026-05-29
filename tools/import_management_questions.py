#!/usr/bin/env python3
"""
Import irrigation-management question PDFs into static JSON question banks.

Requires pypdf:
  python tools/import_management_questions.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "農水_管理組考題" / "農水_管理組考題"
QUESTION_DIR = BASE_DIR / "questions"

LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}

NUMERIC_OPTION_MARKERS = {
    "\uf081": 0,
    "\uf082": 1,
    "\uf083": 2,
    "\uf084": 3,
    "\x81": 0,
    "\x82": 1,
    "\x83": 2,
    "\x84": 3,
    "①": 0,
    "②": 1,
    "③": 2,
    "④": 3,
}

CROSS_REF_PATTERNS = [
    r"選項\([A-D]\)",
    r"選項[一二三四1234]",
    r"以上皆",
    r"皆是",
    r"皆非",
    r"皆正確",
    r"皆錯誤",
]


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


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def clean_lines(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "公告試題僅供參考" in stripped:
            continue
        if re.search(r"第\s*\d+\s*頁", stripped) or re.search(r"共\s*\d+\s*頁", stripped):
            continue
        if re.fullmatch(r"-\s*\d+\s*-", stripped):
            continue
        if re.fullmatch(r"\d{3}\s*年四技", stripped):
            continue
        if stripped in {"【請接續背面】", "請接續背面"}:
            continue
        kept.append(stripped)
    return " ".join(kept)


def clean_text(text: str) -> str:
    text = clean_lines(text)
    text = text.replace("", "L")
    text = text.replace("", "->")
    text = text.replace("ˉ", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n，；")


def should_lock_options(options: list[str]) -> bool:
    return any(re.search(pattern, option) for option in options for pattern in CROSS_REF_PATTERNS)


def numeric_marker_positions(text: str) -> list[tuple[int, int]]:
    positions = []
    for index, char in enumerate(text):
        marker_index = NUMERIC_OPTION_MARKERS.get(char)
        if marker_index is not None:
            positions.append((index, marker_index))
    return positions


def alpha_marker_positions(text: str) -> list[tuple[int, int, int]]:
    positions = []
    for match in re.finditer(r"\(\s*([A-D])\s*\)", text):
        positions.append((match.start(), match.end(), LETTER_TO_INDEX[match.group(1)]))
    return positions


def parse_numeric_options(body: str) -> tuple[str, list[str]]:
    markers = numeric_marker_positions(body)
    sequence = []
    for pos, marker_index in markers:
        if marker_index == len(sequence):
            sequence.append((pos, marker_index))
            if len(sequence) == 4:
                break

    if len(sequence) != 4:
        raise ValueError(f"Expected 4 numeric options, found {len(sequence)} in: {body[:120]}")

    question = clean_text(body[: sequence[0][0]])
    options = []
    for i, (start, _) in enumerate(sequence):
        end = sequence[i + 1][0] if i + 1 < len(sequence) else len(body)
        options.append(clean_text(body[start + 1 : end]))
    return question, options


def parse_alpha_options(body: str) -> tuple[str, list[str]]:
    markers = alpha_marker_positions(body)
    sequence = []
    for start, end, marker_index in markers:
        if marker_index == len(sequence):
            sequence.append((start, end, marker_index))
            if len(sequence) == 4:
                break

    if len(sequence) != 4:
        raise ValueError(f"Expected 4 alpha options, found {len(sequence)} in: {body[:120]}")

    question = clean_text(body[: sequence[0][0]])
    options = []
    for i, (_, marker_end, _) in enumerate(sequence):
        end = sequence[i + 1][0] if i + 1 < len(sequence) else len(body)
        options.append(clean_text(body[marker_end:end]))
    return question, options


def parse_embedded_answer_bank(pdf_path: Path) -> list[dict]:
    text = read_pdf_text(pdf_path)
    section_end = text.find("\n貳、")
    if section_end != -1:
        text = text[:section_end]

    starts = list(re.finditer(r"【([^】]+)】\s*(\d{1,2})\s*[.．]", text))
    questions = []
    for idx, match in enumerate(starts):
        question_number = int(match.group(2))
        body_start = match.end()
        body_end = starts[idx + 1].start() if idx + 1 < len(starts) else len(text)
        body = text[body_start:body_end]
        if question_number < 1 or question_number > 50:
            continue

        question, options = parse_numeric_options(body)
        if not question or len(options) != 4:
            continue

        answer_text = match.group(1)
        answer_match = re.search(r"[1-4]", answer_text)
        item = {
            "id": question_number,
            "question": question,
            "options": options,
            "answer": int(answer_match.group(0)) - 1 if answer_match else 0,
        }
        if not answer_match:
            item["freeScore"] = True
        if should_lock_options(options):
            item["noShuffle"] = True
        questions.append(item)

    return questions


def parse_tve_answers(pdf_path: Path) -> dict[int, int]:
    text = read_pdf_text(pdf_path)
    answers = {}
    for match in re.finditer(r"\b(\d{1,2})\s+([A-D])\b", text):
        question_number = int(match.group(1))
        if 1 <= question_number <= 50 and question_number not in answers:
            answers[question_number] = LETTER_TO_INDEX[match.group(2)]
        if len(answers) == 50:
            break
    return answers


def parse_tve_question_bank(question_pdf: Path, answer_pdf: Path) -> list[dict]:
    answers = parse_tve_answers(answer_pdf)
    if len(answers) != 50:
        raise ValueError(f"Expected 50 answers in {answer_pdf}, found {len(answers)}")

    text = read_pdf_text(question_pdf)
    starts = list(re.finditer(r"(?:^|\n)\s*(\d{1,2})\.\s+", text))
    questions = []
    expected = 1
    for idx, match in enumerate(starts):
        question_number = int(match.group(1))
        if question_number != expected:
            continue

        body_start = match.end()
        body_end = starts[idx + 1].start() if idx + 1 < len(starts) else len(text)
        body = text[body_start:body_end]
        try:
            question, options = parse_alpha_options(body)
        except ValueError:
            continue

        item = {
            "id": question_number,
            "question": question,
            "options": options,
            "answer": answers[question_number],
        }
        if should_lock_options(options):
            item["noShuffle"] = True
        questions.append(item)
        expected += 1

        if expected > 50:
            break

    return questions


def write_bank(filename: str, questions: list[dict]) -> None:
    output_path = QUESTION_DIR / filename
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(questions, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    QUESTION_DIR.mkdir(exist_ok=True)

    results = []
    for bank in EMBEDDED_ANSWER_BANKS:
        questions = parse_embedded_answer_bank(SOURCE_DIR / bank.pdf)
        if len(questions) != 15:
            raise ValueError(f"Expected 15 questions in {bank.pdf}, found {len(questions)}")
        write_bank(bank.output, questions)
        results.append((bank.output, len(questions)))

    for bank in TVE_BANKS:
        questions = parse_tve_question_bank(SOURCE_DIR / bank.question_pdf, SOURCE_DIR / bank.answer_pdf)
        if len(questions) != 50:
            raise ValueError(f"Expected 50 questions in {bank.question_pdf}, found {len(questions)}")
        write_bank(bank.output, questions)
        results.append((bank.output, len(questions)))

    for filename, count in results:
        print(f"{filename}: {count}")


if __name__ == "__main__":
    main()
