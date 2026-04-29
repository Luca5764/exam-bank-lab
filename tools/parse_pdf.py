#!/usr/bin/env python3
"""
解析 114年證券交易法規 PDF → questions.json
用法：python parse_pdf.py "114年證券交易法規_6月版_.pdf"

輸出：questions_114.json
"""

import pdfplumber
import re
import json
import sys
from pathlib import Path


def extract_all_text(pdf_path):
    """Extract full text from all pages, skipping page 1 (title page)."""
    pdf = pdfplumber.open(pdf_path)
    full_text = ""
    for i, page in enumerate(pdf.pages):
        if i == 0:
            continue  # skip title page
        text = page.extract_text() or ""
        # Remove page numbers (standalone digits at end)
        text = re.sub(r'\n\d+\s*$', '', text)
        full_text += text + "\n"
    pdf.close()
    return full_text


def parse_questions(text):
    """Parse questions from extracted text."""
    # Split by bullet points (•, ⚫) which separate each question
    # Clean up the text first
    text = text.replace('\ufeff', '').replace('\u200b', '')

    # Split on bullet markers
    chunks = re.split(r'[•⚫]\s*\n?', text)
    chunks = [c.strip() for c in chunks if c.strip()]

    questions = []
    qid = 0

    # Patterns for cross-referencing options (should not shuffle)
    cross_ref_patterns = [
        r'選項\([A-D1-4]\)',
        r'以上皆',
        r'\([A-D1-4]\)和\([A-D1-4]\)',
        r'\([A-D1-4]\)或\([A-D1-4]\)',
        r'\([A-D1-4]\)\([A-D1-4]\)',
    ]

    for chunk in chunks:
        # Skip very short chunks or instruction text
        if len(chunk) < 10:
            continue
        if '藍色字體' in chunk or '代表電腦考試' in chunk:
            continue

        # Normalize whitespace
        chunk = re.sub(r'\s+', ' ', chunk).strip()

        # Remove trailing period
        chunk = chunk.rstrip('。').strip()

        # Check if this has MC options: (A)...(B)...(C)...(D)... or (1)...(2)...(3)...(4)...
        has_abcd = bool(re.search(r'\(A\)', chunk))
        has_1234 = bool(re.search(r'\(1\)', chunk)) and bool(re.search(r'\(2\)', chunk))

        if has_abcd or has_1234:
            q = parse_mc(chunk, has_abcd, cross_ref_patterns)
            if q:
                qid += 1
                q['id'] = qid
                questions.append(q)
        else:
            # Fill-in-blank: has 【answer】 pattern
            bracket = re.search(r'【([^】]+)】', chunk)
            if bracket:
                answer = bracket.group(1).strip()
                q_text = re.sub(r'【[^】]+】', '______', chunk).strip()
                if len(q_text) > 10 and len(answer) > 0:
                    qid += 1
                    questions.append({
                        'id': qid,
                        'type': 'fill',
                        'question': q_text,
                        'answer': answer,
                        'options': []
                    })

    return questions


def parse_mc(chunk, has_abcd, cross_ref_patterns):
    """Parse a multiple-choice question chunk."""
    # Protect composite option text like "選項(A)(B)(C)皆是"
    protected = chunk
    placeholders = {}
    ph_idx = 0
    for pat in [
        r'選項\([A-D1-4]\)\([A-D1-4]\)\([A-D1-4]\)[^(\n]*',
        r'選項\([A-D1-4]\)或\([A-D1-4]\)[^(\n]*',
        r'選項\([A-D1-4]\)和\([A-D1-4]\)[^(\n]*',
    ]:
        for m in re.finditer(pat, protected):
            ph = f'__PH{ph_idx}__'
            placeholders[ph] = m.group()
            protected = protected[:m.start()] + ph + protected[m.end():]
            ph_idx += 1
            break

    # Split on option markers
    if has_abcd:
        parts = re.split(r'\(([A-D])\)', protected)
    else:
        parts = re.split(r'\(([1-4])\)', protected)

    if len(parts) < 5:  # need q + at least 2 (marker, text) pairs
        return None

    q_text = parts[0].strip()
    # Restore placeholders in question
    for ph, val in placeholders.items():
        q_text = q_text.replace(ph, val)

    # Remove 【】 from question text
    q_text = re.sub(r'[【】]', '', q_text).strip()

    if len(q_text) < 5:
        return None

    options = []
    option_letters = []
    correct_idx = None

    for j in range(1, len(parts) - 1, 2):
        letter = parts[j]
        opt = parts[j + 1].strip() if j + 1 < len(parts) else ''
        # Restore placeholders
        for ph, val in placeholders.items():
            opt = opt.replace(ph, val)
        opt = opt.strip().rstrip('。').strip()

        # Check for answer bracket
        if '【' in opt and '】' in opt:
            clean = re.sub(r'[【】]', '', opt).strip()
            correct_idx = len(options)
            options.append(clean)
        elif '【' in opt:
            clean = opt.replace('【', '').strip()
            correct_idx = len(options)
            options.append(clean)
        elif '】' in opt:
            clean = opt.replace('】', '').strip()
            correct_idx = len(options)
            options.append(clean)
        else:
            options.append(opt)
        option_letters.append(letter)

    if len(options) < 3 or correct_idx is None:
        return None

    # Trim to max 4
    options = options[:4]
    correct_idx = min(correct_idx, len(options) - 1)

    # Check if should not shuffle
    no_shuffle = False
    for opt in options:
        for pat in cross_ref_patterns:
            if re.search(pat, opt):
                no_shuffle = True
                break
        if no_shuffle:
            break

    q = {
        'id': 0,
        'question': q_text,
        'options': options,
        'answer': correct_idx,
    }
    if no_shuffle:
        q['noShuffle'] = True

    return q


def main():
    if len(sys.argv) < 2:
        pdf_path = "114年證券交易法規_6月版_.pdf"
    else:
        pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"找不到檔案: {pdf_path}")
        sys.exit(1)

    print(f"解析 PDF: {pdf_path}")
    text = extract_all_text(pdf_path)
    print(f"提取文字: {len(text)} 字元")

    questions = parse_questions(text)

    mc = [q for q in questions if 'options' in q and q.get('options')]
    fill = [q for q in questions if not q.get('options')]
    mc_only = [q for q in mc if len(q['options']) >= 3]

    print(f"解析結果: {len(questions)} 題 (選擇 {len(mc_only)}, 填充 {len(fill)})")

    # Only output MC questions (matching the quiz app's format)
    # Remove 'type' field from fill questions if any snuck in
    output = []
    for q in mc_only:
        out = {
            'id': q['id'],
            'question': q['question'],
            'options': q['options'],
            'answer': q['answer'],
        }
        if q.get('noShuffle'):
            out['noShuffle'] = True
        output.append(out)

    # Renumber
    for i, q in enumerate(output):
        q['id'] = i + 1

    Path('questions').mkdir(exist_ok=True)
    out_path = "questions/questions_114.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    locked = sum(1 for q in output if q.get('noShuffle'))
    print(f"輸出: {out_path} ({len(output)} 題選擇題, {locked} 題鎖定選項順序)")

    # Show some samples
    print("\n=== 前 3 題 ===")
    for q in output[:3]:
        lock = ' 🔒' if q.get('noShuffle') else ''
        print(f"Q{q['id']}{lock}: {q['question'][:60]}...")
        for i, o in enumerate(q['options']):
            m = '✓' if i == q['answer'] else ' '
            print(f"  {m} ({chr(65+i)}) {o[:50]}")

    # Also output fill-in questions separately
    fill_output = []
    for q in fill:
        fill_output.append({
            'id': len(fill_output) + 1,
            'question': q['question'],
            'answer': q['answer'],
        })

    fill_path = "questions/questions_114_fill.json"
    with open(fill_path, 'w', encoding='utf-8') as f:
        json.dump(fill_output, f, ensure_ascii=False, indent=2)
    print(f"\n填充題另存: {fill_path} ({len(fill_output)} 題)")


if __name__ == "__main__":
    main()
