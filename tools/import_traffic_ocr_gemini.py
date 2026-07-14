#!/usr/bin/env python3
"""
Import 交通部汽車檢、考驗員 exam questions from a scanned PDF without a text layer.
Uses Gemini 2.5 Flash for high-accuracy VLM OCR page-by-page.

Usage:
  .venv\\Scripts\\python.exe tools\\import_traffic_ocr_gemini.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Union

import fitz  # PyMuPDF
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Ensure UTF-8 output on Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_PDF = BASE_DIR / "交通部" / "115練習題答案-檢考驗員學科0701_260713_223648.pdf"
QUESTIONS_DIR = BASE_DIR / "questions"
TMP_DIR = BASE_DIR / ".tmp"
OCR_CACHE_DIR = TMP_DIR / "ocr_cache"
PAGE_IMAGES_DIR = TMP_DIR / "page_images"

# Create directories
OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PAGE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Define Pydantic schema for Gemini structured JSON output
class ExtractedRow(BaseModel):
    id: int = Field(description="The question number (題號) from the table row, e.g. 1, 2, 3...")
    answer_str: str = Field(description="The raw string from the 答案 (Answer) column, e.g. '3', '1、4', 'O', 'X', '○', '╳'")
    question_raw: str = Field(description="The raw text from the 題目 (Question) column, including all inline options (1)(2)(3)(4) and trailing text, but EXCLUDING the legal reference tags at the end like #17, #26, #67-1, (#62及#67)")

class ExtractedPage(BaseModel):
    test_title: str = Field(description="The header/title of the test on this page if present, e.g. '汽車檢、考驗員研習班學科測驗練習題-1 (答案)'")
    section_title: str = Field(description="The section header under the title, e.g. '一、選擇題：(每題2分)' or '二、複選題：20分'")
    questions: List[ExtractedRow] = Field(description="List of extracted questions on this page")


# Spacing and normalizations (adapted from import_traffic_questions.py)
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

    for old, new in TEXT_REPLACEMENTS.items():
        text = text.replace(old, new)

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

    text = re.sub(
        r"(?<=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])(?=[A-Za-z0-9])",
        " ",
        text
    )
    text = re.sub(
        r"(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffee])",
        " ",
        text
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


OPTION_RE = re.compile(
    r"(?:[([（［\]]\s*([1-4１-４])\s*[)\]^）］]?|[([（［\]]?\s*([1-4１-４])\s*[)\]^）］])"
)

common_units = ["個月", "年", "月", "日", "天", "小時", "分", "秒", "元", "次", "倍", "公尺", "公里", "公噸", "公升", "公斤", "歲", "公分"]
units_pattern = "|".join(re.escape(u) for u in common_units)

# Helper function to check if a string is numeric or a numeric unit
is_numeric_or_unit = lambda s: bool(re.match(r"^\s*\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?\s*[\u4e00-\u9fff]{0,3}\s*$", s))

def should_disable_splitting(stem: str) -> bool:
    stem = stem.strip()
    
    # 1. Starts with common choice-comparison question prefixes
    choice_prefixes = [
        "下列何者", "下列何種", "下列哪些", "下列何行為", "下列何者行為",
        "何者是", "何者不是", "何種車", "下列敘述何者"
    ]
    if any(stem.startswith(p) for p in choice_prefixes):
        return True

    # 2. Ends with choice-comparison endings
    choice_endings = [
        "何者正確", "何者錯誤", "何者不正確", "何者為非", "何者為是",
        "何者為正確", "何者為錯誤", "何者為不正確", "下列何者為非",
        "何者為正確者", "下列何者正確", "下列何者錯誤", "下列何者不正確",
        "何者正確？", "何者錯誤？", "何者不正確？", "何者為非？", "何者為是？",
        "何者為非 ?", "何者為是 ?", "何者正確 ?", "何者錯誤 ?", "何者不正確 ?",
        "何者行為？", "何者行為", "何種正確", "何種錯誤", "何種不正確"
    ]
    # Check if choice endings are in the last 15 characters of the stem (handles question marks, etc.)
    if any(e in stem[-15:] for e in choice_endings if len(stem) >= len(e)):
        return True
    return any(stem.endswith(e) for e in choice_endings)

def is_valid_q_part(q_part: str, common_unit: str = "") -> bool:
    if not q_part:
        return False
    if q_part[0] in "，。；、：,.;:?？":
        return True
    
    # If the tail starts with the common unit of options 1-3, reject it
    # because the unit should belong to the option itself.
    if common_unit and q_part.startswith(common_unit):
        return False

    allowed_starts = [
        "以上", "以下", "以內", "以外", "者", "以上者", "以下者", "以內者",
        "處", "並", "得", "記", "吊", "罰", "科", "限", "扣", "至", "標",
        "指定", "核定", "送請", "公告", "規定", "申領", "色", "型", "級", "類", "段",
        "需", "應", "須", "得", "未", "已", "第", "之", "內", "外", "前", "後", "顏",
        "辦", "備", "經", "裝", "變", "同", "且", "自", "起", "駕", "車", "「", "」", "（", "）", "《", "》"
    ] + common_units
    return any(q_part.startswith(w) for w in allowed_starts)

def is_valid_opt_part(opt_part: str) -> bool:
    if not opt_part:
        return False
    # Options should not end with linking particles or conjunctions
    if opt_part[-1] in "之的與或及":
        return False
    return True

def extract_options(text: str) -> tuple[str, list[str]]:
    """Extract question text and options from a question body.
    Returns (question_text, [option1, option2, option3, option4])
    """
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
    option_positions: list[tuple[int, int, int]] = []
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

    # Check if the last option contains trailing question stem
    if len(options) == 4:
        avg_len = sum(len(opt) for opt in options[:3]) / 3
        stem_prefix = text[:first_marker.start()].strip()
        best_opt = options[3]
        best_q = ""

        # Compute common unit for validation
        get_cjk_suffix = lambda s: (re.search(r"[\u4e00-\u9fff\s]+$", s).group(0).strip() 
                                    if re.search(r"[\u4e00-\u9fff\s]+$", s) else "")
        u1 = get_cjk_suffix(options[0])
        u2 = get_cjk_suffix(options[1])
        u3 = get_cjk_suffix(options[2])
        common_unit = u2 if (u2 and u1 == u2 and u2 == u3) else ""

        # Skip split entirely if splitting is disabled for this question style
        if not should_disable_splitting(stem_prefix):
            candidates = []
            is_not_duplicate = lambda op: op.rstrip("。.，,；") not in [o.rstrip("。.，,；") for o in options[:3]]

            # Strategy 1: LCS Suffix Split
            suffix = ""
            if all(options[:3]):
                min_l = min(len(s) for s in options[:3])
                for idx in range(1, min_l + 1):
                    char = options[0][-idx]
                    if all(s[-idx] == char for s in options[:3]):
                        suffix = char + suffix
                    else:
                        break
            if suffix and not suffix.isdigit():
                suffix_regex = r"\s*".join(re.escape(c) for c in suffix)
                for m in re.finditer(suffix_regex, options[3]):
                    split_idx = m.end()
                    opt_part = options[3][:split_idx].strip().rstrip("。.，,；")
                    q_part = options[3][split_idx:].strip()
                    if opt_part and q_part:
                        if len(options[3]) > avg_len + 1:
                            if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                                if is_not_duplicate(opt_part):
                                    candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))

            # Strategy 2: CJK Boundary Split
            if len(options[3]) > avg_len + 1:
                boundary_words = ["標誌", "標線", "號誌", "標字", "路段", "路口", "色", "型", "級", "類", "段"]
                for word in boundary_words:
                    if word in options[3] and not any(word in opt for opt in options[:3]):
                        for m in re.finditer(re.escape(word), options[3]):
                            split_idx = m.start()
                            opt_part = options[3][:split_idx].strip().rstrip("。.，,；")
                            q_part = options[3][split_idx:].strip()
                            if opt_part and q_part:
                                if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                                    if is_not_duplicate(opt_part):
                                        candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))

            # Strategy 3: Individual Suffix Split
            for opt in options[:3]:
                m = re.search(r"([\u4e00-\u9fff]{1,2})$", opt)
                if m:
                    ind_suffix = m.group(1)
                    if ind_suffix in options[3]:
                        split_idx = options[3].find(ind_suffix) + len(ind_suffix)
                        opt_part = options[3][:split_idx].strip().rstrip("。.，,；")
                        q_part = options[3][split_idx:].strip()
                        if opt_part and q_part:
                            if len(options[3]) > avg_len + 1:
                                if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                                    if is_not_duplicate(opt_part):
                                        candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))

            # Strategy 4: Unit-based Split (Only run if Options 1-3 are all numeric or units!)
            if len(options[3]) > avg_len + 1 and all(is_numeric_or_unit(opt) for opt in options[:3]):
                matches = list(re.finditer(rf"(\d+(?:\.\d+)?\s*(?:{units_pattern}))", options[3]))
                for m in matches:
                    # Option A: Split after the unit
                    split_idx = m.end()
                    opt_part = options[3][:split_idx].strip().rstrip("。.，,；")
                    q_part = options[3][split_idx:].strip()
                    if opt_part and q_part:
                        if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                            if is_not_duplicate(opt_part):
                                candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))
                    # Option B: Split before the unit
                    unit_m = re.search(rf"(?:{units_pattern})", m.group(1))
                    if unit_m:
                        unit_start_idx = m.start() + unit_m.start()
                        opt_part = options[3][:unit_start_idx].strip().rstrip("。.，,；")
                        q_part = options[3][unit_start_idx:].strip()
                        if opt_part and q_part:
                            if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                                if is_not_duplicate(opt_part):
                                    candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))

            # Strategy 5: Space Split
            diff_threshold = 2 if avg_len <= 2 else (3 if avg_len <= 5 else 5)
            if len(options[3]) > avg_len + diff_threshold:
                for match in re.finditer(r"\s+", options[3]):
                    start = match.start()
                    opt_part = options[3][:start].strip().rstrip("。.，,；")
                    q_part = options[3][match.end():].strip()
                    if opt_part and q_part:
                        if is_valid_q_part(q_part, common_unit) and is_valid_opt_part(opt_part):
                            if is_not_duplicate(opt_part):
                                candidates.append((opt_part, q_part, abs(len(opt_part) - avg_len)))

            # Select candidate with minimum length diff from options 1-3
            if candidates:
                # If the question ends with a question mark, we only allow splits
                # that yield a substantial trailing stem (length > 5).
                if stem_prefix.rstrip().endswith(("？", "?")):
                    candidates = [c for c in candidates if len(c[1]) > 5]
                if candidates:
                    candidates.sort(key=lambda x: x[2])
                    best_opt, best_q, _ = candidates[0]

        if best_q:
            options[3] = best_opt
            if stem_prefix:
                question_text = f"{stem_prefix} ______ {best_q}"
            else:
                question_text = f"______ {best_q}"

    # Asymmetric Option 4 Chinese suffix extraction (e.g., "以...為限")
    if len(options) == 4:
        if all(is_numeric_or_unit(opt) for opt in options[:3]):
            if options[3].endswith("為限"):
                val_part = options[3][:-2].strip()
                if is_numeric_or_unit(val_part):
                    options[3] = val_part
                    suffix = "為限"
                    if "______" in question_text:
                        question_text = question_text.replace("______", f"______ {suffix}")
                    else:
                        question_text = f"{question_text} ______ {suffix}".strip()
            else:
                get_cjk_suffix = lambda s: (re.search(r"[\u4e00-\u9fff\s]+$", s).group(0).strip() 
                                            if re.search(r"[\u4e00-\u9fff\s]+$", s) else "")
                u1 = get_cjk_suffix(options[0])
                u2 = get_cjk_suffix(options[1])
                u3 = get_cjk_suffix(options[2])
                
                # Check for incompatible units (different non-empty CJK units in options 1-3)
                non_empty_units = {u for u in (u1, u2, u3) if u}
                if len(non_empty_units) > 1:
                    # Incompatible units, keep the units in options list!
                    pass
                else:
                    common_unit = u2 if (u2 and u2 == u3) else ""
                    if common_unit:
                        pattern = rf"^\s*(\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?\s*{re.escape(common_unit)})\s*([\u4e00-\u9fff\w\s]+)$"
                    else:
                        pattern = r"^\s*(\d+(?:\.\d+)?\s*(?:~|-)?\s*(?:\d+(?:\.\d+)?)?\s*%?)\s*([\u4e00-\u9fff\w\s]+)$"
                        
                    suffix_match = re.match(pattern, options[3])
                    if suffix_match:
                        opt_val = suffix_match.group(1).strip()
                        suffix = suffix_match.group(2).strip()
                        if suffix and re.search(r"[\u4e00-\u9fffA-Za-z]", suffix):
                            if suffix == "為限" or len(suffix) >= 2 or not common_unit:
                                options[3] = opt_val
                                if "______" in question_text:
                                    question_text = question_text.replace("______", f"______ {suffix}")
                                else:
                                    question_text = f"{question_text} ______ {suffix}".strip()

    return question_text, options


def parse_answer(ans_str: str, qtype: str) -> Union[int, List[int]]:
    """Parse raw answer string to 0-indexed integer(s)."""
    ans_str = ans_str.strip()
    
    # Check for True/False markers
    if ans_str in ("○", "O", "o", "0"):
        return 0
    elif ans_str in ("╳", "X", "x", "×"):
        # Note: True/False options are ["O", "X"], so O is index 0, X is index 1.
        return 1

    # Find all digits 1-4
    digits = [int(d) for d in re.findall(r"[1-4]", ans_str)]
    if not digits:
        # Default fallback
        return 0
        
    if qtype == "multi":
        return sorted(list(set(d - 1 for d in digits)))
    else:
        return digits[0] - 1


def main():
    load_dotenv()
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    print(f"Connecting to Gemini API...")
    client = genai.Client(api_key=gemini_key)

    doc = fitz.open(str(SOURCE_PDF))
    total_pages = len(doc)
    print(f"Loaded PDF: {SOURCE_PDF} ({total_pages} pages)")

    # 1. Run VLM OCR page-by-page (with caching)
    pages_data = []
    for idx in range(total_pages):
        cache_file = OCR_CACHE_DIR / f"page_{idx}.json"
        
        # Check if Page 13 is the blank separator
        if idx == 13:
            print(f"Page {idx}: Skipping blank separator page")
            pages_data.append(None)
            continue

        if cache_file.exists():
            print(f"Page {idx}: Loading cached OCR results")
            with open(cache_file, "r", encoding="utf-8") as f:
                pages_data.append(json.load(f))
            continue

        print(f"Page {idx}: Rendering to image...")
        page = doc[idx]
        pix = page.get_pixmap(dpi=200)
        img_path = PAGE_IMAGES_DIR / f"page_{idx}.png"
        pix.save(str(img_path))

        prompt = """
        請精確擷取圖片中的學科測驗考題表格。
        請注意：
        1. 答案列 (答案) 包含 '3'、'1、4'、'○'、'╳' 等字樣。
        2. 題目列 (題目) 包含題幹以及選項 (1)... (2)... (3)... (4)...。
        3. 題目最後如果包含法條標記或出處（如 #17、(#62及#67)、#21 115.1.31施行 等），請在提取題目文字時直接將其去除，不要保留在 question_raw 中。
        4. 請勿遺漏任何一列題目。
        5. 重要：有些頁面同時包含兩種題型（例如：頁面頂部是單選題的最後幾題，接著是複選題的開頭）。請務必完整提取該頁面上的「所有」題目，不論它們是否被「二、複選題：...」等標題分隔或屬於不同的表格。請將它們全部放入 questions 列表中！
        6. 注意：有些頁面的最頂部可能只有一列孤立的題目（例如前一頁單選題遺留下來的最後一題，如第40題），其後接著是新題型的標題與新表格。請務必將這一列孤立的題目也一併提取，不要因為它只有一列或與下面的表格分離就將其忽略！
        """

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 3.0
        success = False
        raw_json = None

        for attempt in range(max_retries):
            print(f"Page {idx}: Querying Gemini 2.5 Flash (attempt {attempt + 1}/{max_retries})...")
            try:
                from PIL import Image
                import time
                import random
                
                img = Image.open(img_path)
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[img, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExtractedPage,
                        temperature=0.0,
                    ),
                )
                
                raw_json = json.loads(response.text)
                success = True
                break
            except Exception as e:
                print(f"  Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    sleep_time = retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"  Waiting {sleep_time:.2f}s before retry...")
                    time.sleep(sleep_time)
                else:
                    print(f"Error processing page {idx}: Max retries reached.")
                    sys.exit(1)

        if success and raw_json:
            # Save raw JSON to cache
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(raw_json, f, ensure_ascii=False, indent=2)
            pages_data.append(raw_json)
            print(f"Page {idx}: OCR completed successfully and cached.")

    doc.close()

    # 2. Map pages to the 6 tests
    TEST_PAGES = {
        1: [0, 1, 2, 3],
        2: [4, 5, 6, 7],
        3: [8, 9, 10, 11, 12],
        4: [14, 15, 16, 17],
        5: [18, 19, 20, 21],
        6: [22, 23, 24, 25]
    }

    # Process each test
    for test_idx, page_indices in TEST_PAGES.items():
        print(f"\nProcessing Test {test_idx} (Pages {page_indices})...")
        
        # Merge all questions extracted from the mapped pages
        merged_rows = []
        for p_idx in page_indices:
            p_data = pages_data[p_idx]
            if p_data and "questions" in p_data:
                merged_rows.extend(p_data["questions"])

        # Sort merged questions by their extracted ID
        # Since each test has two sections: Single Choice (1-40) followed by Multi Choice (1-10)
        # We can distinguish them based on their position.
        # Let's clean and identify choice type:
        # First 40 rows should be Single Choice (qtype='single').
        # Next 10 rows should be Multi Choice (qtype='multi').
        
        if len(merged_rows) != 50:
            print(f"Warning: Expected 50 questions for Test {test_idx}, but got {len(merged_rows)}.")
            # Let's inspect the IDs to sort them properly
            # We can group them by ordering of appearance.
            # If there's an ID reset (e.g. ID goes from 40 to 1), that represents the section boundary.
            single_rows = []
            multi_rows = []
            seen_reset = False
            prev_id = -1
            
            for row in merged_rows:
                r_id = row.get("id")
                if prev_id != -1 and r_id < prev_id:
                    seen_reset = True
                
                if not seen_reset:
                    single_rows.append(row)
                else:
                    multi_rows.append(row)
                prev_id = r_id
        else:
            single_rows = merged_rows[:40]
            multi_rows = merged_rows[40:]

        print(f"Test {test_idx}: Separated {len(single_rows)} single-choice and {len(multi_rows)} multi-choice questions.")

        parsed_questions = []
        
        # Parse single choice questions (IDs 1-40)
        for i, row in enumerate(single_rows):
            seq_id = i + 1
            raw_q = row.get("question_raw", "")
            ans_str = row.get("answer_str", "")
            
            # Extract options first on raw text to preserve spacing boundaries
            q_text, opts = extract_options(raw_q)
            q_text = clean_cjk_spaces(q_text)
            q_text = normalize_spacing(q_text)
            opts = [clean_cjk_spaces(o) for o in opts]
            opts = [normalize_spacing(o) for o in opts]
            
            # Parse answer
            ans_val = parse_answer(ans_str, "single")
            
            parsed_questions.append({
                "id": seq_id,
                "question": q_text,
                "options": opts if opts else ["", "", "", ""],
                "answer": ans_val
            })

        # Parse multi choice questions (IDs 41-50)
        for i, row in enumerate(multi_rows):
            seq_id = 40 + i + 1
            raw_q = row.get("question_raw", "")
            ans_str = row.get("answer_str", "")
            
            # Extract options first on raw text to preserve spacing boundaries
            q_text, opts = extract_options(raw_q)
            q_text = clean_cjk_spaces(q_text)
            q_text = normalize_spacing(q_text)
            opts = [clean_cjk_spaces(o) for o in opts]
            opts = [normalize_spacing(o) for o in opts]
            
            # Parse answer
            ans_val = parse_answer(ans_str, "multi")
            
            parsed_questions.append({
                "id": seq_id,
                "question": q_text,
                "options": opts if opts else ["", "", "", ""],
                "answer": ans_val
            })

        # Output to JSON
        output_file = QUESTIONS_DIR / f"交通部115-檢考驗員-道路交通法規練習題{test_idx}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(parsed_questions, f, ensure_ascii=False, indent=2)
            f.write("\n")
            
        print(f"Wrote {len(parsed_questions)} questions to {output_file}")

    print("\nAll practice tests processed successfully!")


if __name__ == "__main__":
    main()
