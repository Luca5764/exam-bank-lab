# 一次性稽核腳本：比對交通部題庫 JSON 與原試卷 PDF，找出切錯的題目/選項與答案不符
import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:\User\Downloads\TS\Code\Irrigation_Quiz")
QUESTIONS = ROOT / "questions"
PDF_DIR = ROOT / "交通部"

# (year, session) -> pdf filename
PDF_MAP = {}
for pdf in PDF_DIR.glob("*.pdf"):
    m = re.match(r"^(\d{3})-(\d)", pdf.name)
    if m:
        PDF_MAP[(m.group(1), m.group(2))] = pdf
    else:
        m = re.match(r"^(\d{3})", pdf.name)
        if m:
            PDF_MAP[(m.group(1), None)] = pdf


def normalize(s: str) -> str:
    """去空白、全形轉半形、去句號，供比對用"""
    s = s.replace("(cid:711)", "ˇ")
    s = re.sub(r"\(cid:\d+\)", "", s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", "", s)
    s = s.replace("。", "").replace("，", ",").replace("：", ":")
    s = s.replace("；", ";").replace("？", "?").replace("！", "!")
    s = s.replace("（", "(").replace("）", ")")
    return s


_pdf_cache = {}


def get_pdf_text(pdf_path: Path) -> str:
    if pdf_path not in _pdf_cache:
        chunks = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        _pdf_cache[pdf_path] = "\n".join(chunks)
    return _pdf_cache[pdf_path]


def extract_subject_section(full_text: str, subject: str) -> str | None:
    """取出某科目從標題到下一科標題（或檔尾）的文字"""
    flex = r"\s*".join(re.escape(c) for c in subject)
    header_re = re.compile(rf"{flex}\s*筆\s*試\s*試\s*題")
    m = header_re.search(full_text)
    if not m:
        return None
    start = m.end()
    nm = re.compile(r"(?m)^[^\n]{0,30}筆\s*試\s*試\s*題").search(full_text, start)
    end = nm.start() if nm else len(full_text)
    return full_text[start:end]


SECTION_RE = re.compile(r"^[一二三四五]\s*、\s*(\S{0,6}題)")


def clean_section(text: str) -> str:
    """移除頁首頁尾雜訊行，標記分節"""
    lines = []
    for line in text.splitlines():
        ls = line.strip()
        if not ls:
            continue
        if re.match(r"^第\s*\d+\s*頁", ls):
            continue
        if "人員訓練所" in ls or "學科檢定" in ls:
            continue
        sm = SECTION_RE.match(ls)
        if sm:
            lines.append(f"@@SECTION:{sm.group(1)}@@")
            continue
        lines.append(ls)
    text = "\n".join(lines)
    # 答案標記偶有跨行（如「（1、2、\n3、4） 內文」）：刪掉下一行行首的殘段
    text = re.sub(r"(?m)^[\d、，,\s]{1,8}[）)]\s*", "", text)
    return text


# 題號允許中間有空白（抽字偶見「2 0.」）；括號內不得再含括號
NUM = r"(\d\s?\d|\d{1,2})"
TAIL = r"\s*[\.、](?!\d)"  # (?!\d) 防止把小數（如 7.1）誤認成題號
Q_RE = re.compile(rf"(?m)^\s*[（(]\s*([^（）()]{{1,14}}?)\s*[）)]\s*{NUM}{TAIL}")
# 不錨定行首的備援版本（部分 PDF 抽字後題目不換行）
Q_RE_LOOSE = re.compile(rf"[（(]\s*([^（）()]{{1,14}}?)\s*[）)]\s*{NUM}{TAIL}")
# 答案標記跨行被截斷（缺右括號）的備援：答案視為不明
Q_RE_OPEN = re.compile(rf"[（(]\s*([\d、，,]{{1,10}})\s+{NUM}{TAIL}")


def _num(m) -> int:
    return int(re.sub(r"\s", "", m.group(2)))


def _accept_sequential(candidates) -> list:
    accepted = []
    expected = 1
    for m in sorted(candidates, key=lambda m: m.start()):
        if _num(m) == expected:
            accepted.append(m)
            expected += 1
    return accepted


def parse_block(text: str, id_offset: int, out: dict) -> int:
    """題號必須從 1 開始連號遞增，跳號的候選視為內文（避免誤吃選項）"""
    best = []
    strict = list(Q_RE.finditer(text))
    loose = list(Q_RE_LOOSE.finditer(text))
    open_ = [(m, True) for m in Q_RE_OPEN.finditer(text)]
    for cand_set in (strict, loose, loose + [m for m, _ in open_]):
        accepted = _accept_sequential(cand_set)
        if len(accepted) > len(best):
            best = accepted
    open_starts = {m.start() for m, _ in open_}
    for i, m in enumerate(best):
        ans_raw = m.group(1)
        num = _num(m)
        body_end = best[i + 1].start() if i + 1 < len(best) else len(text)
        body = text[m.end():body_end]
        nums = re.findall(r"\d", ans_raw)
        if nums:
            answer = [int(d) - 1 for d in nums]
        elif any(c in ans_raw for c in "○〇Ｏ"):
            answer = [0]  # 是非題 O
        elif any(c in ans_raw for c in "╳×Ｘ✕X"):
            answer = [1]  # 是非題 X
        else:
            answer = None
        if "或" in ans_raw or "送分" in ans_raw or m.start() in open_starts:
            answer = None  # 送分/多答/標記截斷，跳過答案比對
        out[num + id_offset] = {"answer": answer, "body": body}
    return len(best)


def parse_questions(section: str) -> dict[int, dict]:
    """回傳 {全卷題號: {answer, body}}，各分節題號接續累加；填充/問答題之後捨棄"""
    cleaned = clean_section(section)
    blocks = re.split(r"@@SECTION:(\S{0,6}題)@@", cleaned)
    out = {}
    offset = 0
    # blocks: [前置文字, 節名, 內容, 節名, 內容, ...]
    if len(blocks) == 1:
        parse_block(blocks[0], 0, out)
        return out
    for i in range(1, len(blocks), 2):
        sec_name, content = blocks[i], blocks[i + 1]
        if re.search(r"填充|問答|申論|簡答|計算", sec_name):
            break
        offset += parse_block(content, offset, out)
    return out


def reconstruct(q: dict) -> str:
    """把 JSON 題目還原成原試卷行文：選項串回填到 ______ 或附加到題尾"""
    opts = "".join(f"({i + 1}){opt}" for i, opt in enumerate(q["options"]))
    text = q["question"]
    if "______" in text:
        return text.replace("______", opts, 1)
    return text + opts


def first_diff(a: str, b: str, ctx: int = 25) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return f"...{a[max(0, i - ctx):i + ctx]}... ↔ ...{b[max(0, i - ctx):i + ctx]}..."
    return f"長度不同 ({len(a)} vs {len(b)}): ...{a[n - ctx:n + ctx]}... ↔ ...{b[n - ctx:n + ctx]}..."


def check_bank(json_path: Path) -> list[str]:
    m = re.match(r"交通部(\d{3})(?:-(\d))?-(.+)\.json$", json_path.name)
    year, session, subject = m.groups()
    pdf = PDF_MAP.get((year, session))
    if not pdf:
        return [f"  [NO PDF] 找不到對應 PDF (year={year}, session={session})"]

    full_text = get_pdf_text(pdf)
    section = extract_subject_section(full_text, subject)
    if section is None:
        return [f"  [NO SECTION] PDF {pdf.name} 中找不到「{subject}」科目"]

    pdf_qs = parse_questions(section)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    issues = []
    if len(pdf_qs) != len(data):
        issues.append(f"  [COUNT] PDF 解析出 {len(pdf_qs)} 題，JSON 有 {len(data)} 題")

    for q in data:
        qid = q["id"]
        if qid not in pdf_qs:
            issues.append(f"  [MISSING] id {qid}: PDF 中找不到此題號")
            continue
        pq = pdf_qs[qid]

        pdf_norm = normalize(pq["body"])
        json_norm = normalize(reconstruct(q))
        if pdf_norm != json_norm:
            # 是非題：JSON 的 (1)O(2)X 選項是轉檔時自行附加的，PDF 原卷沒有
            ox = [str(o).strip().upper() for o in q["options"]]
            if ox in (["O", "X"], ["○", "×"], ["是", "非"]) and pdf_norm == normalize(q["question"]):
                pass
            else:
                issues.append(f"  [TEXT] id {qid}: {first_diff(pdf_norm, json_norm)}")

        if pq["answer"] is not None:
            ja = q["answer"]
            ja_list = sorted(ja) if isinstance(ja, list) else [ja]
            if sorted(pq["answer"]) != ja_list:
                issues.append(
                    f"  [ANSWER] id {qid}: PDF={[(x + 1) for x in pq['answer']]} JSON={[(x + 1) for x in ja_list]}"
                )
    return issues


def main():
    banks = sorted(QUESTIONS.glob("交通部*.json"))
    total_issues = 0
    for b in banks:
        issues = check_bank(b)
        if issues:
            print(f"\n=== {b.name} ===")
            for line in issues:
                print(line)
            total_issues += len(issues)
    print(f"\n{'=' * 50}\n共 {len(banks)} 個題庫，{total_issues} 個待確認項目")


if __name__ == "__main__":
    main()
