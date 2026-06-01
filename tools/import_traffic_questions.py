#!/usr/bin/env python3
"""
Import 交通部汽車檢、考驗員 exam PDFs into static JSON question banks.

Extracts 是非題 (true/false), 單選題 (single-choice), and 複選題 (multi-choice)
questions from each subject section.  Skips 英翻中/中譯英, 填充題, and 論文/公文.

Usage:
  .venv\\Scripts\\python.exe tools\\import_traffic_questions.py
  .venv\\Scripts\\python.exe tools\\import_traffic_questions.py --dry-run
  .venv\\Scripts\\python.exe tools\\import_traffic_questions.py --file "115-1全科試題及答案.pdf"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf  # type: ignore


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "交通部"
QUESTION_DIR = BASE_DIR / "questions"

# ---------------------------------------------------------------------------
# Section / subject detection
# ---------------------------------------------------------------------------

# Title patterns that identify a new subject section (appears in page headers)
SUBJECT_TITLE_RE = re.compile(
    r"(汽車英文專業術語|汽車構造原理概論|汽車構造原理|汽車駕駛理論|道路交通法規|國\s*文)"
    r"[筆試]*\s*[試題]*"
)

# Section type markers within a subject
SECTION_MARKERS = {
    "是非題": "truefalse",
    "單選題": "single",
    "單擇題": "single",
    "複選題": "multi",
    "多選題": "multi",
    "選擇題(單選)": "single",
    "選擇題": "single",
    "填充題": "fill",
    "英翻中": "en2zh",
    "中譯英": "zh2en",
    "論文": "essay",
    "公文": "essay",
    "作文": "essay",
    "翻譯": "translation",
}

# Sections we want to keep
KEEP_TYPES = {"truefalse", "single", "multi"}

# Sections to skip
SKIP_TYPES = {"fill", "en2zh", "zh2en", "essay", "translation"}

# Subjects to skip entirely
SKIP_SUBJECTS = {"汽車英文專業術語", "國文"}

# ---------------------------------------------------------------------------
# Answer parsing patterns
# ---------------------------------------------------------------------------

# True/false answer: （○） or （╳） or （ ○ ） or (O) etc.  Supports mixed full/half parens, anchored to start.
TF_ANSWER_RE = re.compile(r"^\s*[（(]\s*([○╳OX×])\s*[）)]")

# Single choice answer at the START of a line: （2 ） N or ( 2 ) N. Supports mixed full/half parens, anchored to start.
# This must NOT match option markers in the middle of a line.
SINGLE_ANSWER_RE = re.compile(r"^\s*[（(]\s*(\d)\s*[）)]")

# Multi choice answer: （1234） or (1 2 4) or （2、3、4） etc. Supports mixed full/half parens, anchored to start.
MULTI_ANSWER_RE = re.compile(
    r"^\s*[（(]\s*(\d[\s、,，.\d]*\d)\s*[）)]"
)

# Detects a new question line: answer marker + question number like 「（2 ） 13.」
# Allows any characters inside the parenthesis to support "送分", "3或4" etc.
# Supports mixed full/half width parentheses, and uses negative lookahead to prevent decimal collisions.
NEW_QUESTION_TF_RE = re.compile(r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．](?!\d)")
NEW_QUESTION_SINGLE_RE = re.compile(r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．](?!\d)")
NEW_QUESTION_MULTI_RE = re.compile(
    r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．](?!\d)"
)

# Question number at the start: 1. or 1 . etc.
QUESTION_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*")

# Option markers: (1) (2) (3) (4) or [1] or [1) or ]1) etc. (supporting both half-width and full-width)
# We require either a leading character ( (, [, （, ［, ] ) or a trailing character ( ), ], ）, ］, ^ ) or both.
# This prevents matching bare digits (like fractions 1/2 or numbers in text).
OPTION_RE = re.compile(
    r"(?:[([（［\]]\s*([1-4１-４])\s*[)\]^）］]?|[([（［\]]?\s*([1-4１-４])\s*[)\]^）］])"
)


# Section header detection
SECTION_HEADER_RE = re.compile(
    r"[一二三四五六七八九十]+\s*[、．.]\s*"
    r"(是非題|單選題|單擇題|複選題|多選題|選擇題\(單選\)|選擇題|填充題|英翻中|中譯英|論文|公文|作文|翻譯|"
    r"中譯英：單選題|英翻中：單選題|中譯英：選擇題|英翻中：選擇題)"
)

# Page header/footer patterns to strip
PAGE_HEADER_RE = re.compile(r"第\s*\d+\s*頁\s*[，,]\s*共\s*\d+\s*頁")
CONTINUATION_RE = re.compile(r"【?請接續背面】?|請接續背面|【以下空白】")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ParsedQuestion:
    id: int
    question: str
    options: list[str]
    answer: int | list[int]  # single int or list for multi
    qtype: str  # "truefalse", "single", "multi"
    subject: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class SubjectSection:
    name: str
    pages_text: list[str] = field(default_factory=list)
    section_type: str = ""  # current section type being parsed


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_all_text(pdf_path: Path) -> list[str]:
    """Extract text from each page of the PDF."""
    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page in doc:
        text = page.get_text("text") or ""
        pages.append(text)
    doc.close()
    return pages


def clean_line(line: str) -> str:
    """Clean a single line of text."""
    line = CONTINUATION_RE.sub("", line)
    line = line.strip()
    return line


def clean_text(text: str) -> str:
    """Clean extracted text."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if PAGE_HEADER_RE.search(line):
            continue
        if re.fullmatch(r"-\s*\d+\s*-", line):
            continue
        line = clean_line(line)
        if line:
            lines.append(line)
    return "\n".join(lines)


TEXT_REPLACEMENTS = {
    "\uf9e4": "理",  # 理 -> 理
    "\uf9dd": "利",  # 利 -> 利
    "\uf9ca": "流",  # 流 -> 流
    "\uf9ea": "離",  # 離 -> 離
}


def clean_cjk_spaces(text: str) -> str:
    """Remove accidental spaces between Chinese characters and Chinese punctuation."""
    if not text:
        return text
    # \u4e00-\u9fff: CJK Unified Ideographs
    # \u3400-\u4dbf: CJK Unified Ideographs Extension A
    # \uf900-\ufaff: CJK Compatibility Ideographs
    # \u3000-\u303f: CJK Symbols and Punctuation (e.g. 、。〃々〆〇)
    # \uff00-\uffee: Halfwidth and Fullwidth Forms (e.g. ，：；！？（）)
    pattern = re.compile(
        r"(?<=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])"
        r"\s+"
        r"(?=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])"
    )
    return pattern.sub("", text)


def normalize_spacing(text: str) -> str:
    """Insert a single space between Chinese characters and English letters/digits."""
    if not text:
        return text

    # Normalization of compatibility characters
    for old, new in TEXT_REPLACEMENTS.items():
        text = text.replace(old, new)

    # Convert full-width technical symbols to half-width
    mapping = {
        "／": "/",
        "～": "~",
        "〜": "~",
        "－": "-",
        "—": "-",
        "％": "%",
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "：": ":",
    }
    for full, half in mapping.items():
        text = text.replace(full, half)

    # 1. Insert space between CJK and Alphanumeric
    text = re.sub(
        r"(?<=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])(?=[A-Za-z0-9])",
        " ",
        text
    )
    # 2. Insert space between Alphanumeric and CJK
    text = re.sub(
        r"(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])",
        " ",
        text
    )
    # 3. Clean up any accidental double spaces created
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Subject & section splitting
# ---------------------------------------------------------------------------

def identify_subject(text: str) -> str | None:
    """Try to identify the subject from a page header."""
    # Look for the subject title pattern
    match = SUBJECT_TITLE_RE.search(text)
    if match:
        subject = match.group(1).strip()
        # Normalize whitespace
        subject = re.sub(r"\s+", "", subject)
        return subject
    return None


def identify_section_type(line: str) -> str | None:
    """Identify section type from a section header line."""
    match = SECTION_HEADER_RE.search(line)
    if match:
        marker_text = match.group(1)
        # Check for translation markers embedded in section headers
        if "中譯英" in marker_text or "英翻中" in marker_text:
            return "zh2en" if "中譯英" in marker_text else "en2zh"
        for key, stype in SECTION_MARKERS.items():
            if key in marker_text:
                return stype
    return None


def split_into_subjects(pages: list[str]) -> list[dict[str, Any]]:
    """Split PDF pages into subject sections with their section types."""
    subjects: list[dict[str, Any]] = []
    current_subject: str | None = None
    current_sections: list[dict[str, Any]] = []
    current_section_type: str | None = None
    current_section_lines: list[str] = []

    for page_text in pages:
        clean = clean_text(page_text)
        lines = clean.split("\n")

        # Pre-merge split headers (e.g., "一、\n是非題：" -> "一、是非題：")
        merged_lines = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r"^[一二三四五六七八九十]+\s*[、．.]$", line) and i + 1 < len(lines):
                merged_lines.append(line + " " + lines[i+1].strip())
                i += 2
            else:
                merged_lines.append(line)
                i += 1
        lines = merged_lines

        # Pre-merge split answer brackets (e.g., "（\n1\n3\n） 2. 題目" -> "（ 1 3 ） 2. 題目")
        # Handles all cases where opening bracket is on one line and closing bracket is on a subsequent line
        merged_brackets = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r"^\s*[（(]", line) and not re.search(r"[）)]", line):
                found_end = -1
                for j in range(i + 1, min(i + 6, len(lines))):
                    next_line = lines[j].strip()
                    if re.search(r"[）)]", next_line):
                        found_end = j
                        break
                if found_end != -1:
                    merged_line = " ".join(lines[k].strip() for k in range(i, found_end + 1))
                    merged_brackets.append(merged_line)
                    i = found_end + 1
                    continue
            merged_brackets.append(line)
            i += 1
        lines = merged_brackets

        # Check if this page starts a new subject
        # Look at the first few lines for subject identification
        page_header = "\n".join(lines[:5])
        detected_subject = identify_subject(page_header)

        if detected_subject and detected_subject != current_subject:
            # Save current section
            if current_section_type and current_section_lines:
                current_sections.append({
                    "type": current_section_type,
                    "lines": current_section_lines,
                })
            # Save current subject
            if current_subject and current_sections:
                subjects.append({
                    "subject": current_subject,
                    "sections": current_sections,
                })
            current_subject = detected_subject
            current_sections = []
            current_section_type = None
            current_section_lines = []

        # Process each line
        for line in lines:
            # Check for section headers
            stype = identify_section_type(line)
            if stype is not None:
                # Save previous section
                if current_section_type and current_section_lines:
                    current_sections.append({
                        "type": current_section_type,
                        "lines": current_section_lines,
                    })
                current_section_type = stype
                current_section_lines = []
                continue

            # Skip the subject title lines
            if detected_subject and SUBJECT_TITLE_RE.search(line):
                continue
            # Skip organizational header lines
            if "交通部" in line and ("研習班" in line or "檢定" in line or "訓練所" in line):
                continue
            if "汽車檢" in line and "考驗員" in line:
                continue
            if re.match(r"^\d{2,3}\s*年", line) and "檢定" in line:
                continue

            if current_section_type:
                current_section_lines.append(line)

    # Save final section and subject
    if current_section_type and current_section_lines:
        current_sections.append({
            "type": current_section_type,
            "lines": current_section_lines,
        })
    if current_subject and current_sections:
        subjects.append({
            "subject": current_subject,
            "sections": current_sections,
        })

    return subjects


# ---------------------------------------------------------------------------
# Question parsing
# ---------------------------------------------------------------------------

def parse_tf_answer(text: str) -> int | None:
    """Parse true/false answer from （○） or （╳）."""
    match = TF_ANSWER_RE.search(text)
    if match:
        ans = match.group(1)
        if ans in ("○", "O"):
            return 0  # ○ is option 0
        elif ans in ("╳", "X", "×"):
            return 1  # ╳ is option 1
    return None


def parse_single_answer(text: str) -> int | None:
    """Parse single choice answer from （N）."""
    match = SINGLE_ANSWER_RE.search(text)
    if match:
        n = int(match.group(1))
        if 1 <= n <= 4:
            return n - 1  # Convert to 0-indexed
    return None


def parse_multi_answer(text: str) -> list[int] | None:
    """Parse multi-choice answer from （1234） or （1 2 4） or （3.4） etc."""
    match = MULTI_ANSWER_RE.search(text)
    if match:
        raw = match.group(1)
        digits = [int(d) for d in re.findall(r"\d", raw)]
        if all(1 <= d <= 4 for d in digits) and len(digits) >= 2:
            return sorted(set(d - 1 for d in digits))  # Convert to 0-indexed
    return None


def extract_options(text: str) -> tuple[str, list[str]]:
    """Extract question text and options from a question body.
    
    Returns (question_text, [option1, option2, option3, option4])
    """
    # Find all option markers (1) (2) (3) (4)
    markers = list(OPTION_RE.finditer(text))
    
    if len(markers) < 2:
        return text.strip(), []

    # Find the first occurrence of (1)
    first_marker = None
    for m in markers:
        digit = m.group(1) or m.group(2)
        digit = {"１": "1", "２": "2", "３": "3", "４": "4"}.get(digit, digit)
        if digit == "1":
            first_marker = m
            break
    
    if first_marker is None:
        return text.strip(), []

    question_text = text[:first_marker.start()].strip()
    
    # Extract options by finding sequential markers
    option_positions: list[tuple[int, int, int]] = []  # (start, end, option_number)
    expected = 1
    for m in markers:
        digit = m.group(1) or m.group(2)
        digit = {"１": "1", "２": "2", "３": "3", "４": "4"}.get(digit, digit)
        n = int(digit)
        if n == expected:
            option_positions.append((m.start(), m.end(), n))
            expected += 1
            if expected > 4:
                break

    if len(option_positions) < 2:
        return text.strip(), []

    options = []
    for i, (start, end, _) in enumerate(option_positions):
        if i + 1 < len(option_positions):
            opt_text = text[end:option_positions[i + 1][0]]
        else:
            opt_text = text[end:]
        opt_text = opt_text.strip().rstrip("。.，,；")
        opt_text = re.sub(r"\s+", " ", opt_text).strip()
        options.append(opt_text)

    # Check if the last option contains trailing question stem (special inline options or layout-inverted layout)
    if len(options) == 4:
        avg_len = sum(len(opt) for opt in options[:3]) / 3
        # Calculate dynamic threshold based on average option length to support very short options
        diff_threshold = 2 if avg_len <= 2 else (3 if avg_len <= 5 else 5)
        # If Option 4 is significantly longer than the average of the first 3 options,
        # it likely contains trailing question stem.
        if len(options[3]) > avg_len + diff_threshold:
            # If the stem prefix before the options is already a complete question
            # (ends with a question mark), option 4 is just long or wrapped, not a trailing stem.
            stem_prefix = text[:first_marker.start()].strip()
            if stem_prefix.rstrip().endswith(("？", "?")):
                return question_text, options

            # 1. Longest Common Suffix strategy
            # Clean first 3 options to find common CJK/alphanumeric suffix
            def clean_for_suffix(s: str) -> str:
                return re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]", "", s)
            
            cleaned_opts = [clean_for_suffix(opt) for opt in options[:3]]
            suffix = ""
            if all(cleaned_opts):
                min_l = min(len(s) for s in cleaned_opts)
                for idx in range(1, min_l + 1):
                    char = cleaned_opts[0][-idx]
                    if all(s[-idx] == char for s in cleaned_opts):
                        suffix = char + suffix
                    else:
                        break
            
            best_opt = options[3]
            best_q = ""
            
            # Try to split by suffix (must not be purely numeric to avoid digits/values collisions)
            if suffix and not suffix.isdigit():
                # Find all occurrences of suffix in options[3]
                occurrences = []
                start = 0
                while True:
                    idx = options[3].find(suffix, start)
                    if idx == -1:
                        break
                    occurrences.append(idx)
                    start = idx + 1
                
                # Find the occurrence that makes the option length closest to avg_len
                min_diff = float("inf")
                for idx in occurrences:
                    split_idx = idx + len(suffix)
                    opt_part = options[3][:split_idx].strip()
                    q_part = options[3][split_idx:].strip()
                    if opt_part and q_part:
                        diff = abs(len(opt_part) - avg_len)
                        if diff < min_diff:
                            min_diff = diff
                            best_opt = opt_part
                            best_q = q_part
            
            # 2. Whitespace split fallback
            if not best_q:
                min_diff = float("inf")
                for match in re.finditer(r"\s+", options[3]):
                    start = match.start()
                    opt_part = options[3][:start].strip()
                    q_part = options[3][match.end():].strip()
                    if not opt_part or not q_part:
                        continue
                    diff = abs(len(opt_part) - avg_len)
                    if diff < min_diff:
                        min_diff = diff
                        best_opt = opt_part
                        best_q = q_part
            
            if best_q:
                # Update option 4
                options[3] = best_opt
                # Determine how to reconstruct the question stem
                stem_prefix = text[:first_marker.start()].strip()
                if stem_prefix:
                    # In place of the option list, we insert a standard " ______ " placeholder.
                    question_text = f"{stem_prefix} ______ {best_q}"
                else:
                    # Layout-inverted (question stem comes completely after options)
                    question_text = best_q

    # 3. Asymmetric Option 4 Chinese suffix extraction
    if len(options) == 4:
        is_numeric_or_unit = lambda s: bool(re.match(r"^\s*\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?\s*[\u4e00-\u9fff]{0,3}\s*$", s))
        if all(is_numeric_or_unit(opt) for opt in options[:3]):
            # Explicit strip of "為限" if Option 4 ends with it (supporting mixed units like 個月 and 年)
            if options[3].endswith("為限"):
                val_part = options[3][:-2].strip()
                if is_numeric_or_unit(val_part):
                    options[3] = val_part
                    suffix = "為限"
                    if "______" in question_text:
                        question_text = f"{question_text} {suffix}".strip()
                    else:
                        question_text = f"{question_text} ______ {suffix}".strip()
            else:
                # Extract CJK suffixes from option 2 and 3
                get_cjk_suffix = lambda s: (re.search(r"[\u4e00-\u9fff\s]+$", s).group(0).strip() 
                                            if re.search(r"[\u4e00-\u9fff\s]+$", s) else "")
                u2 = get_cjk_suffix(options[1])
                u3 = get_cjk_suffix(options[2])
                common_unit = u2 if (u2 and u2 == u3) else ""
                
                # Build pattern based on common_unit
                if common_unit:
                    pattern = rf"^\s*(\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?\s*{re.escape(common_unit)})\s*([\u4e00-\u9fff\w\s]+)$"
                else:
                    pattern = r"^\s*(\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?)\s*([\u4e00-\u9fff\w\s]+)$"
                    
                suffix_match = re.match(pattern, options[3])
                if suffix_match:
                    opt_val = suffix_match.group(1).strip()
                    suffix = suffix_match.group(2).strip()
                    
                    if suffix and re.search(r"[\u4e00-\u9fffA-Za-z]", suffix):
                        # Suffix must be at least 2 characters if it's not a known common suffix like "為限", or if there is no common unit
                        if suffix == "為限" or len(suffix) >= 2 or not common_unit:
                            options[3] = opt_val
                            if "______" in question_text:
                                question_text = f"{question_text} {suffix}".strip()
                            else:
                                question_text = f"{question_text} ______ {suffix}".strip()

    return question_text, options


def join_continued_lines(lines: list[str], section_type: str) -> list[str]:
    """Join multi-line questions back together.
    
    A new question starts with a full-width answer marker followed by a question
    number (e.g. 「（2 ） 13. 題目」).  Continuation lines (including option
    lines that start with half-width (1)) are appended to the current question.
    
    Some PDFs place the answer on its own line, so we pre-merge those.
    """
    # Pre-pass: merge answer-only lines with the following line.
    # Pattern: a line that is ONLY an answer marker (no question text after it)
    ANSWER_ONLY_RE = re.compile(
        r"^\s*[（(]\s*(?:[○╳OX×]|\d[\s、,，.\d]*|.*?[送分或].*?)\s*[）)]\s*$"
    )
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line and ANSWER_ONLY_RE.match(line) and i + 1 < len(lines):
            # Merge with next line
            merged.append(line + " " + lines[i + 1].strip())
            i += 2
        else:
            merged.append(line)
            i += 1

    joined: list[str] = []
    current = ""

    for line in merged:
        line = line.strip()
        if not line:
            continue

        is_new_question = False
        if section_type == "truefalse":
            is_new_question = bool(NEW_QUESTION_TF_RE.match(line))
        elif section_type == "single":
            is_new_question = bool(NEW_QUESTION_SINGLE_RE.match(line))
        elif section_type == "multi":
            is_new_question = bool(NEW_QUESTION_MULTI_RE.match(line))

        if is_new_question:
            if current:
                joined.append(current)
            current = line
        else:
            if current:
                current += " " + line
            else:
                current = line

    if current:
        joined.append(current)

    return joined


def parse_truefalse_questions(lines: list[str]) -> list[ParsedQuestion]:
    """Parse true/false questions."""
    questions: list[ParsedQuestion] = []
    joined = join_continued_lines(lines, "truefalse")

    for raw in joined:
        if not NEW_QUESTION_TF_RE.match(raw):
            continue

        answer = parse_tf_answer(raw)
        free_score = False
        if answer is None:
            answer = 0
            free_score = True

        # Remove the answer marker from the text
        text = re.sub(r"^\s*[（(].*?[）)]", "", raw, count=1).strip()
        
        # Extract question number
        num_match = QUESTION_NUM_RE.match(text)
        if num_match:
            qid = int(num_match.group(1))
            question_text = text[num_match.end():].strip()
        else:
            # Try to find question number elsewhere
            continue

        # Clean question text
        question_text = re.sub(r"\s+", " ", question_text).strip()
        question_text = clean_cjk_spaces(question_text)
        question_text = normalize_spacing(question_text)
        question_text = question_text.rstrip("。")

        warnings = []
        if not question_text:
            warnings.append("empty question text")

        q = ParsedQuestion(
            id=qid,
            question=question_text,
            options=["O", "X"],
            answer=answer,
            qtype="truefalse",
            warnings=warnings,
        )
        if free_score:
            q.warnings.append("free score question")
        questions.append(q)

    return questions


def parse_single_questions(lines: list[str]) -> list[ParsedQuestion]:
    """Parse single-choice questions."""
    questions: list[ParsedQuestion] = []
    joined = join_continued_lines(lines, "single")

    for raw in joined:
        if not NEW_QUESTION_SINGLE_RE.match(raw):
            continue

        answer = parse_single_answer(raw)
        free_score = False
        if answer is None:
            answer = 0
            free_score = True

        # Remove the answer marker
        text = re.sub(r"^\s*[（(].*?[）)]", "", raw, count=1).strip()

        # Extract question number
        num_match = QUESTION_NUM_RE.match(text)
        if num_match:
            qid = int(num_match.group(1))
            body = text[num_match.end():].strip()
        else:
            continue

        question_text, options = extract_options(body)
        question_text = re.sub(r"\s+", " ", question_text).strip()
        question_text = clean_cjk_spaces(question_text)
        question_text = normalize_spacing(question_text)
        options = [clean_cjk_spaces(opt) for opt in options]
        options = [normalize_spacing(opt) for opt in options]

        warnings = []
        if len(options) < 2:
            warnings.append(f"only {len(options)} options found")
        if not question_text:
            warnings.append("empty question text")

        q = ParsedQuestion(
            id=qid,
            question=question_text,
            options=options if options else ["", "", "", ""],
            answer=answer,
            qtype="single",
            warnings=warnings,
        )
        if free_score:
            q.warnings.append("free score question")
        questions.append(q)

    return questions


def parse_multi_questions(lines: list[str]) -> list[ParsedQuestion]:
    """Parse multi-choice questions."""
    questions: list[ParsedQuestion] = []
    joined = join_continued_lines(lines, "multi")

    for raw in joined:
        if not NEW_QUESTION_MULTI_RE.match(raw):
            continue

        # Try multi-answer first, then single-answer (some multi sections have single-answer items)
        answer = parse_multi_answer(raw)
        is_multi = answer is not None
        
        free_score = False
        if answer is None:
            single_ans = parse_single_answer(raw)
            if single_ans is not None:
                answer = [single_ans]  # Wrap single in list for consistency
                is_multi = True
            else:
                answer = []
                free_score = True

        # Remove the answer marker
        text = re.sub(r"^\s*[（(].*?[）)]", "", raw, count=1).strip()

        # Extract question number
        num_match = QUESTION_NUM_RE.match(text)
        if num_match:
            qid = int(num_match.group(1))
            body = text[num_match.end():].strip()
        else:
            continue

        question_text, options = extract_options(body)
        question_text = re.sub(r"\s+", " ", question_text).strip()
        question_text = clean_cjk_spaces(question_text)
        question_text = normalize_spacing(question_text)
        options = [clean_cjk_spaces(opt) for opt in options]
        options = [normalize_spacing(opt) for opt in options]

        warnings = []
        if len(options) < 2:
            warnings.append(f"only {len(options)} options found")
        if not question_text:
            warnings.append("empty question text")

        q = ParsedQuestion(
            id=qid,
            question=question_text,
            options=options if options else ["", "", "", ""],
            answer=answer,
            qtype="multi",
            warnings=warnings,
        )
        if free_score:
            q.warnings.append("free score question")
        questions.append(q)

    return questions


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def parse_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """Parse a single PDF file into question bank JSON structures.
    
    Returns a list of dicts, one per subject, each containing:
      - subject: str
      - questions: list of question dicts
      - stats: dict with counts
    """
    pages = extract_all_text(pdf_path)
    subjects = split_into_subjects(pages)
    results = []

    for subj_data in subjects:
        subject_name = subj_data["subject"]

        # Skip unwanted subjects
        if subject_name in SKIP_SUBJECTS:
            continue

        all_questions: list[ParsedQuestion] = []
        skipped_sections: list[str] = []

        for section in subj_data["sections"]:
            stype = section["type"]
            section_lines = section["lines"]

            if stype in SKIP_TYPES:
                skipped_sections.append(stype)
                continue

            if stype == "truefalse":
                all_questions.extend(parse_truefalse_questions(section_lines))
            elif stype == "single":
                all_questions.extend(parse_single_questions(section_lines))
            elif stype == "multi":
                all_questions.extend(parse_multi_questions(section_lines))

        if not all_questions:
            continue

        # Convert to JSON-compatible dicts
        json_questions = []
        for index, q in enumerate(all_questions):
            item: dict[str, Any] = {
                "id": index + 1,  # Assign sequential, unique IDs starting from 1
                "question": q.question,
                "options": q.options,
                "answer": q.answer,
            }
            if q.qtype == "truefalse":
                item["noShuffle"] = True
            if "free score question" in q.warnings:
                item["freeScore"] = True
            if q.warnings:
                item["_warnings"] = q.warnings
            json_questions.append(item)

        stats = {
            "total": len(json_questions),
            "truefalse": sum(1 for q in all_questions if q.qtype == "truefalse"),
            "single": sum(1 for q in all_questions if q.qtype == "single"),
            "multi": sum(1 for q in all_questions if q.qtype == "multi"),
            "skipped_sections": skipped_sections,
            "warnings": sum(1 for q in all_questions if q.warnings),
        }

        results.append({
            "subject": subject_name,
            "questions": json_questions,
            "stats": stats,
        })

    return results


def extract_exam_info(filename: str) -> tuple[str, str]:
    """Extract year and session info from filename.
    
    Examples:
      "115-1全科試題及答案.pdf" -> ("115", "1")
      "110年汽車檢...pdf" -> ("110", "")
    """
    # Pattern 1: YYY-N全科
    match = re.match(r"(\d{3})-(\d+)", filename)
    if match:
        return match.group(1), match.group(2)
    
    # Pattern 2: YYY年
    match = re.match(r"(\d{3})年", filename)
    if match:
        return match.group(1), ""

    # Pattern 3: YYY全科 (no session)
    match = re.match(r"(\d{3})全科", filename)
    if match:
        return match.group(1), ""

    return "", ""


def build_output_filename(year: str, session: str, subject: str) -> str:
    """Build the output JSON filename."""
    if session:
        return f"交通部{year}-{session}-{subject}.json"
    else:
        return f"交通部{year}-{subject}.json"


def process_all_pdfs(
    source_dir: Path,
    output_dir: Path,
    dry_run: bool = False,
    target_file: str | None = None,
) -> list[dict[str, Any]]:
    """Process all PDFs in the source directory."""
    report: list[dict[str, Any]] = []

    pdf_files = sorted(source_dir.glob("*.pdf"))
    if target_file:
        pdf_files = [f for f in pdf_files if f.name == target_file]
        if not pdf_files:
            print(f"ERROR: File not found: {target_file}")
            return report

    for pdf_path in pdf_files:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_path.name}")
        print(f"{'='*60}")

        year, session = extract_exam_info(pdf_path.name)
        if not year:
            print(f"  WARNING: Cannot extract year from filename, skipping")
            continue

        try:
            results = parse_pdf(pdf_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            report.append({
                "pdf": pdf_path.name,
                "error": str(e),
            })
            continue

        for result in results:
            subject = result["subject"]
            questions = result["questions"]
            stats = result["stats"]
            output_name = build_output_filename(year, session, subject)

            print(f"\n  Subject: {subject}")
            print(f"    Total: {stats['total']} questions")
            print(f"    是非: {stats['truefalse']}, 單選: {stats['single']}, 多選: {stats['multi']}")
            if stats["skipped_sections"]:
                print(f"    Skipped sections: {', '.join(stats['skipped_sections'])}")
            if stats["warnings"]:
                print(f"    Questions with warnings: {stats['warnings']}")

            # Show warnings
            for q in questions:
                if q.get("_warnings"):
                    print(f"    Q{q['id']}: {q['_warnings']}")

            # Remove internal warnings before writing
            clean_questions = []
            for q in questions:
                q_clean = {k: v for k, v in q.items() if not k.startswith("_")}
                clean_questions.append(q_clean)

            if not dry_run:
                output_path = output_dir / output_name
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(clean_questions, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"    -> Wrote: {output_name}")
            else:
                print(f"    -> Would write: {output_name}")

            report.append({
                "pdf": pdf_path.name,
                "subject": subject,
                "output": output_name,
                "stats": stats,
            })

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import 交通部 exam PDFs into question bank JSON files."
    )
    parser.add_argument(
        "--source-dir", type=Path, default=SOURCE_DIR,
        help="Directory containing the PDF files.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=QUESTION_DIR,
        help="Directory to write JSON files to.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and report but don't write files.",
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Process only a specific PDF file (by name).",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    report = process_all_pdfs(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        target_file=args.file,
    )

    # Summary
    total_questions = sum(
        r.get("stats", {}).get("total", 0) for r in report if "stats" in r
    )
    total_files = sum(1 for r in report if "output" in r)
    errors = sum(1 for r in report if "error" in r)

    print(f"\n{'='*60}")
    print(f"Summary: {total_files} JSON files, {total_questions} questions total")
    if errors:
        print(f"Errors: {errors}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
