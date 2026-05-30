#!/usr/bin/env python3
"""Normalize accidental CJK word breaks in question-bank JSON files.

PDF and LiteParse text extraction can turn line wraps into plain spaces.  For
Chinese question text that often leaves artifacts like "臺 灣" or "下列 何種".
This tool removes only high-confidence CJK-to-CJK whitespace in
question/options text and keeps table-like option spacing intact.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
QUESTION_DIR = BASE_DIR / "questions"
BANK_INDEX = BASE_DIR / "data" / "banks.json"

CJK_RE = re.compile(r"[\u3400-\u9fff]")
CJK_GAP_RE = re.compile(r"([\u3400-\u9fff])\s+([\u3400-\u9fff])")
SENTENCE_PUNCT_RE = re.compile(r"[\u3001\u3002\uff0c\uff1b\uff1a\uff1f\uff01,.;:!?]")

JOIN_LEFT_CHARS = set("的之及與和或為是在於由以而並但若則將被可需須應會能未已不無有此該其第下上中內外前後至到向對就把給使讓因從才且仍又更最何哪幾同所")
JOIN_RIGHT_CHARS = set("的之及與和或為是在於由以而並但若則種類項個些時內外到何哪幾可需須應不未已同所")

JOIN_PAIRS = {
    ("大", "幅"),
    ("市", "場"),
    ("曲", "線"),
    ("有", "效"),
    ("機", "械"),
    ("減", "量"),
    ("流", "動"),
    ("物", "種"),
    ("現", "象"),
    ("兩", "側"),
    ("產", "品"),
    ("相", "關"),
    ("臺", "灣"),
    ("藥", "量"),
    ("購", "入"),
    ("過", "程"),
    ("長", "期"),
    ("重", "要"),
    ("需", "求"),
    ("供", "給"),
    ("消", "費"),
    ("價", "格"),
    ("財", "貨"),
    ("資", "產"),
    ("負", "債"),
    ("權", "益"),
    ("會", "計"),
    ("調", "整"),
    ("分", "錄"),
    ("現", "金"),
    ("存", "貨"),
    ("淨", "利"),
    ("費", "用"),
    ("折", "舊"),
    ("損", "失"),
    ("股", "利"),
    ("普", "通"),
    ("特", "別"),
    ("公", "司"),
    ("設", "備"),
    ("專", "利"),
    ("財", "務"),
    ("報", "表"),
    ("收", "益"),
    ("出", "售"),
    ("成", "本"),
    ("保", "護"),
    ("設", "施"),
    ("其", "他"),
    ("許", "多"),
    ("授", "粉"),
    ("暫", "時"),
    ("導", "向"),
    ("能", "力"),
    ("上", "述"),
}

PHRASE_REPLACEMENTS = {
    "農民 購物": "農民購物",
    "伴 手禮": "伴手禮",
    "有效 分蘗": "有效分蘗",
    "分蘗 數": "分蘗數",
    "巨 花魔芋": "巨花魔芋",
    "起源 中心": "起源中心",
    "大幅 波動": "大幅波動",
    "出現 糧食": "出現糧食",
    "投入 大量": "投入大量",
    "重要 角色": "重要角色",
    "最能 說明": "最能說明",
    "哈密 瓜": "哈密瓜",
    "下列 何種": "下列何種",
    "下列 何者": "下列何者",
    "固定 成本": "固定成本",
    "變動 成本": "變動成本",
    "出售 成本": "出售成本",
    "公允 價值": "公允價值",
    "重大 影響": "重大影響",
    "應收 帳款": "應收帳款",
    "應付 帳款": "應付帳款",
    "應付 薪資": "應付薪資",
    "股利 會計": "股利會計",
    "金融 資產": "金融資產",
    "平均 消費": "平均消費",
    "實質 利率": "實質利率",
    "下完藥 後": "下完藥後",
    "情形 下": "情形下",
    "公分 等": "公分等",
    "高海拔至 低海拔": "高海拔至低海拔",
    "作物 最不適合": "作物最不適合",
    "作物 培土": "作物培土",
    "哪些 作物": "哪些作物",
    "透過 參與": "透過參與",
    "特遣隊 登陸": "特遣隊登陸",
    "防止 褐變": "防止褐變",
    "農業 專業": "農業專業",
    "訓練內容 著重": "訓練內容著重",
    "降低 福壽螺": "降低福壽螺",
}


@dataclass(frozen=True)
class Change:
    path: Path
    qid: Any
    field: str
    before: str
    after: str


def cjk_gap_count(text: str) -> int:
    return len(CJK_GAP_RE.findall(text))


def looks_like_spaced_option_table(text: str) -> bool:
    """Keep spaces in compact option tables/lists such as "A B C D" rows.

    Question prose should not contain CJK word spaces, but some options are
    extracted as multi-column lists.  Those usually have several CJK gaps and no
    sentence punctuation.
    """

    if cjk_gap_count(text) < 2:
        return False
    if SENTENCE_PUNCT_RE.search(text):
        return False

    tokens = [token for token in re.split(r"\s+", text.strip()) if token]
    cjk_tokens = [token for token in tokens if CJK_RE.search(token)]
    return len(tokens) >= 4 or len(cjk_tokens) >= 3


def normalize_cjk_gaps(text: str, *, preserve_table_spacing: bool = False) -> str:
    if not isinstance(text, str) or not text:
        return text
    if preserve_table_spacing and looks_like_spaced_option_table(text):
        return text
    for before, after in PHRASE_REPLACEMENTS.items():
        text = re.sub(re.escape(before).replace(r"\ ", r"\s+"), after, text)

    def replace_gap(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        if left in JOIN_LEFT_CHARS or right in JOIN_RIGHT_CHARS or (left, right) in JOIN_PAIRS:
            return left + right
        return match.group(0)

    return CJK_GAP_RE.sub(replace_gap, text)


def normalize_question_item(item: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Mutate one question item and return changed field triples."""

    changes: list[tuple[str, str, str]] = []
    question = item.get("question")
    if isinstance(question, str):
        normalized = normalize_cjk_gaps(question)
        if normalized != question:
            item["question"] = normalized
            changes.append(("question", question, normalized))

    options = item.get("options")
    if isinstance(options, list):
        normalized_options = []
        for index, option in enumerate(options):
            if isinstance(option, str):
                normalized = normalize_cjk_gaps(option, preserve_table_spacing=True)
                if normalized != option:
                    changes.append((f"options[{index}]", option, normalized))
                normalized_options.append(normalized)
            else:
                normalized_options.append(option)
        item["options"] = normalized_options

    materials = item.get("materials")
    if isinstance(materials, list):
        for material_index, material in enumerate(materials):
            if not isinstance(material, dict):
                continue
            for key in ("content", "notes"):
                value = material.get(key)
                if not isinstance(value, str):
                    continue
                normalized = normalize_cjk_gaps(value)
                if normalized != value:
                    material[key] = normalized
                    changes.append((f"materials[{material_index}].{key}", value, normalized))

    return changes


def iter_bank_paths(files: list[Path] | None) -> list[Path]:
    if files:
        return [path if path.is_absolute() else BASE_DIR / path for path in files]

    banks = json.loads(BANK_INDEX.read_text(encoding="utf-8"))
    paths = []
    for bank in banks:
        file_name = bank.get("file")
        if isinstance(file_name, str) and file_name:
            paths.append(BASE_DIR / file_name)
    return sorted(set(paths))


def normalize_file(path: Path) -> tuple[list[dict[str, Any]], list[Change]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} does not contain a question list")

    output = copy.deepcopy(data)
    changes: list[Change] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for field, before, after in normalize_question_item(item):
            changes.append(Change(path=path, qid=item.get("id"), field=field, before=before, after=after))
    return output, changes


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path, help="Specific question JSON files to normalize.")
    parser.add_argument("--write", action="store_true", help="Write normalized JSON files.")
    parser.add_argument("--sample-limit", type=int, default=30, help="Maximum changed fields to print.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_changes: list[Change] = []
    changed_files = 0

    for path in iter_bank_paths(args.files):
        normalized, changes = normalize_file(path)
        if not changes:
            continue
        changed_files += 1
        all_changes.extend(changes)
        if args.write:
            write_json(path, normalized)

    action = "updated" if args.write else "would update"
    print(f"{action} {len(all_changes)} fields in {changed_files} files")
    for change in all_changes[: args.sample_limit]:
        rel = change.path.relative_to(BASE_DIR)
        print(f"- {rel} Q{change.qid} {change.field}: {change.before} -> {change.after}")
    if len(all_changes) > args.sample_limit:
        print(f"... {len(all_changes) - args.sample_limit} more changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
