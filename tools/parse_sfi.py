#!/usr/bin/env python3
"""
解析 SFI 考試 PDF（題目 + 解答）→ questions_XXXXX.json

用法（單檔）：
  python parse_sfi.py 114/11401.pdf 114/11401a.pdf [questions_11401.json]

用法（批次處理 112~114 全部）：
  python parse_sfi.py --all

需要：pdfplumber
  uv run --with pdfplumber parse_sfi.py --all
"""

import pdfplumber
import re
import json
import sys
from pathlib import Path


CROSS_REF_PATTERNS = [
    r'選項\([A-D]\)',
    r'以上皆',
    r'皆是',
    r'皆非',
    r'皆正確',
    r'皆錯誤',
]


def extract_text(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return '\n'.join(page.extract_text() or '' for page in pdf.pages)


def parse_answers(pdf_path):
    """解析解答 PDF → {題號: 0-based index}，只取第一科（法規與實務）"""
    text = extract_text(pdf_path)
    letter_to_idx = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    answers = {}
    for m in re.finditer(r'(\d+)\s+([A-D])', text):
        qnum = int(m.group(1))
        if qnum in answers:  # 題號重複 = 第二科開始，停止
            break
        answers[qnum] = letter_to_idx[m.group(2)]
    return answers


def find_option_positions(text):
    """在 text 中按順序找 (A)(B)(C)(D) 的位置"""
    positions = {}
    search_from = 0
    for letter in 'ABCD':
        pos = text.find(f'({letter})', search_from)
        if pos == -1:
            break
        positions[letter] = pos
        search_from = pos + 3
    return positions


EXAM_FOOTER_PAT = re.compile(r'\s+1\d{2}\s*年第\s*\d+\s*次.*$', re.DOTALL)


def extract_options(body, positions):
    """依位置擷取各選項文字（option D 可安全包含 (A)(B)(C) 字串）"""
    letters = [l for l in 'ABCD' if l in positions]
    options = []
    for i, letter in enumerate(letters):
        start = positions[letter] + 3
        end = positions[letters[i + 1]] if i + 1 < len(letters) else len(body)
        opt = re.sub(r'\s+', ' ', body[start:end]).strip()
        # 最後一題的最後一個選項可能夾帶下一科目的試卷標頭，截除之
        opt = EXAM_FOOTER_PAT.sub('', opt).strip()
        options.append(opt)
    return options


def parse_questions(text, answers):
    """從全文解析所有題目，對應解答後回傳題目列表"""
    # 找第一題起始位置，跳過 header
    m = re.search(r'(?:^|\n)\s*1\.\s', text)
    if m:
        text = text[m.start():].lstrip('\n')

    # 用 MULTILINE 找所有題號位置
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\.\s+', re.MULTILINE)
    matches = list(q_pattern.finditer(text))

    questions = []
    seen_qnums = set()
    for idx, match in enumerate(matches):
        qnum = int(match.group(1))
        if qnum in seen_qnums:  # 題號重複 = 第二科開始，停止
            break
        seen_qnums.add(qnum)
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end]

        # 找 (A) 起始位置，分離題幹與選項
        opt_start = body.find('(A)')
        if opt_start == -1:
            continue

        q_text = re.sub(r'\s+', ' ', body[:opt_start]).strip()
        if len(q_text) < 3:
            continue

        positions = find_option_positions(body[opt_start:])
        if len(positions) < 3:
            continue

        options = extract_options(body[opt_start:], positions)
        options = options[:4]

        ans_idx = answers.get(qnum)
        if ans_idx is None:
            print(f"  警告: 第 {qnum} 題無解答，跳過")
            continue

        q = {
            'id': qnum,
            'question': q_text,
            'options': options,
            'answer': ans_idx,
        }
        if any(re.search(pat, opt) for opt in options for pat in CROSS_REF_PATTERNS):
            q['noShuffle'] = True

        questions.append(q)

    return questions


def process_pair(q_pdf, a_pdf, out_json=None):
    q_pdf, a_pdf = Path(q_pdf), Path(a_pdf)
    if out_json is None:
        Path('questions').mkdir(exist_ok=True)
        out_json = f'questions/questions_{q_pdf.stem}.json'

    print(f"\n處理: {q_pdf.name} + {a_pdf.name}")

    answers = parse_answers(a_pdf)
    text = extract_text(q_pdf)
    questions = parse_questions(text, answers)

    # 重新編號
    for i, q in enumerate(questions):
        q['id'] = i + 1

    locked = sum(1 for q in questions if q.get('noShuffle'))
    print(f"  共 {len(questions)} 題（{locked} 題鎖定選項順序）→ {out_json}")

    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    # 顯示前 2 題確認
    for q in questions[:2]:
        lock = ' [lock]' if q.get('noShuffle') else ''
        print(f"  Q{q['id']}{lock}: {q['question'][:55]}...")
        for i, o in enumerate(q['options']):
            mark = '*' if i == q['answer'] else ' '
            print(f"    {mark}({chr(65+i)}) {o[:45]}")

    return questions


YEAR_LABELS = {
    '112': '112年', '113': '113年', '114': '114年',
}


def main():
    if len(sys.argv) == 1 or '--all' in sys.argv:
        base = Path('.')
        results = []
        for year in ['112', '113', '114']:
            year_dir = base / year
            if not year_dir.exists():
                continue
            for session in range(1, 4):
                stem = f'{year}0{session}'
                q_pdf = year_dir / f'{stem}.pdf'
                a_pdf = year_dir / f'{stem}a.pdf'
                if q_pdf.exists() and a_pdf.exists():
                    qs = process_pair(q_pdf, a_pdf, f'questions/questions_{stem}.json')
                    results.append((stem, year, session, len(qs)))

        print('\n=== 批次完成 ===')
        for stem, year, session, n in results:
            print(f'  questions/questions_{stem}.json  {year}年第{session}次  {n}題')
    else:
        if len(sys.argv) < 3:
            print(__doc__)
            sys.exit(1)
        out = sys.argv[3] if len(sys.argv) > 3 else None
        process_pair(sys.argv[1], sys.argv[2], out)


if __name__ == '__main__':
    main()
