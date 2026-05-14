#!/usr/bin/env python3
"""
Generate deterministic cross-links between collected law articles.

Output:
  data/law-links.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAWS = ROOT / "data" / "laws.json"
DEFAULT_OUT = ROOT / "data" / "law-links.json"

CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CN_UNITS = {"十": 10, "百": 100}
ARTICLE_RE = re.compile(
    r"第\s*([一二兩三四五六七八九十百零〇0-9]+)\s*條(?:\s*之\s*([一二兩三四五六七八九十百零〇0-9]+))?"
)
PARENT_LAW_TITLES = {
    "水利法施行細則": "水利法",
    "水污染防治法施行細則": "水污染防治法",
    "土壤及地下水污染整治法施行細則": "土壤及地下水污染整治法",
    "農田水利法施行細則": "農田水利法",
    "農田灌溉排水管理辦法": "農田水利法",
    "灌溉管理組織設置辦法": "農田水利法",
}


@dataclass(frozen=True)
class ArticleRef:
    law_id: str
    law_title: str
    article_id: str
    article_no: str
    title: str


def chinese_to_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)

    total = 0
    current = 0
    for char in value:
        if char in CN_DIGITS:
            current = CN_DIGITS[char]
            continue
        unit = CN_UNITS.get(char)
        if unit:
            if current == 0:
                current = 1
            total += current * unit
            current = 0
            continue
        return None
    return total + current


def normalize_article_no(main: str, sub: str | None = None) -> str | None:
    main_no = chinese_to_int(main)
    if main_no is None:
        return None
    if not sub:
        return str(main_no)
    sub_no = chinese_to_int(sub)
    if sub_no is None:
        return None
    return f"{main_no}-{sub_no}"


def source_key(law_id: str, article_id: str) -> str:
    return f"{law_id}::{article_id}"


def load_indexes(laws: list[dict]) -> tuple[dict[str, dict[str, ArticleRef]], dict[str, list[ArticleRef]], dict[str, str]]:
    by_law_no: dict[str, dict[str, ArticleRef]] = {}
    sequence_by_law: dict[str, list[ArticleRef]] = {}
    law_title_to_id = {law["title"]: law["id"] for law in laws}

    for law in laws:
        articles: list[ArticleRef] = []
        for chapter in law.get("chapters", []):
            for article in chapter.get("articles", []):
                ref = ArticleRef(
                    law_id=law["id"],
                    law_title=law["title"],
                    article_id=article["id"],
                    article_no=article["no"],
                    title=article["title"],
                )
                articles.append(ref)
                by_law_no.setdefault(law["id"], {})[article["no"]] = ref
        sequence_by_law[law["id"]] = articles
    return by_law_no, sequence_by_law, law_title_to_id


def infer_target_law_id(prefix: str, current_law_id: str, law_title_to_id: dict[str, str]) -> tuple[str, str]:
    compact = re.sub(r"\s+", "", prefix)
    for title in sorted(law_title_to_id, key=len, reverse=True):
        if compact.endswith(title):
            return law_title_to_id[title], "rule:explicit-law"
    if compact.endswith("本法"):
        return current_law_id, "rule:this-law"
    return current_law_id, "rule:same-law"


def latest_law_title_context(text: str, law_title_to_id: dict[str, str]) -> tuple[str, str] | None:
    latest: tuple[int, int, str] | None = None
    for title, law_id in law_title_to_id.items():
        start = text.find(title)
        while start >= 0:
            end = start + len(title)
            # Prefer the rightmost completed match. If matches overlap and end at the
            # same position, prefer the longer full law name, e.g. 農田水利法 over 水利法.
            candidate = (end, len(title), law_id)
            if latest is None or candidate[:2] > latest[:2]:
                latest = candidate
            start = text.find(title, start + 1)
    return (latest[2], "rule:law-title-context") if latest else None


def parent_law_id(current: ArticleRef, law_title_to_id: dict[str, str]) -> str | None:
    parent_title = PARENT_LAW_TITLES.get(current.law_title)
    return law_title_to_id.get(parent_title or "")


def active_law_context(text: str, position: int, current: ArticleRef, law_title_to_id: dict[str, str]) -> tuple[str, str] | None:
    sentence_start = max(text.rfind(mark, 0, position) for mark in "。；;：:\n")
    segment = text[sentence_start + 1:position]
    compact = re.sub(r"\s+", "", segment)

    sentence_law = latest_law_title_context(compact, law_title_to_id)
    if sentence_law:
        return sentence_law[0], "rule:sentence-law-context"

    if "本法" in compact:
        return parent_law_id(current, law_title_to_id) or current.law_id, "rule:this-law"

    nearby = re.sub(r"\s+", "", text[max(0, position - 120):position])
    if any(marker in nearby for marker in ("這些規定", "上述規定", "前述規定", "分別是", "包含", "包括", "依據", "根據")):
        nearby_law = latest_law_title_context(nearby, law_title_to_id)
        if nearby_law:
            return nearby_law[0], "rule:nearby-law-context"
    return None


def previous_article(current: ArticleRef, sequence_by_law: dict[str, list[ArticleRef]]) -> ArticleRef | None:
    articles = sequence_by_law.get(current.law_id, [])
    for index, article in enumerate(articles):
        if article.article_id == current.article_id:
            return articles[index - 1] if index > 0 else None
    return None


def add_ref(refs: list[dict], seen: set[tuple], *, field: str, text: str, target: ArticleRef, method: str, confidence: float) -> None:
    key = (field, text, target.law_id, target.article_id)
    if key in seen:
        return
    seen.add(key)
    refs.append(
        {
            "field": field,
            "text": text,
            "targetLawId": target.law_id,
            "targetArticleId": target.article_id,
            "targetLawTitle": target.law_title,
            "targetArticleTitle": target.title,
            "confidence": confidence,
            "method": method,
        }
    )


def scan_field(
    *,
    field: str,
    value: str,
    current: ArticleRef,
    by_law_no: dict[str, dict[str, ArticleRef]],
    sequence_by_law: dict[str, list[ArticleRef]],
    law_title_to_id: dict[str, str],
) -> list[dict]:
    refs: list[dict] = []
    seen: set[tuple] = set()

    for match in re.finditer(r"前條", value):
        target = previous_article(current, sequence_by_law)
        if target:
            add_ref(refs, seen, field=field, text=match.group(0), target=target, method="rule:previous-article", confidence=1.0)

    for match in ARTICLE_RE.finditer(value):
        article_no = normalize_article_no(match.group(1), match.group(2))
        if not article_no:
            continue
        prefix = value[max(0, match.start() - 36): match.start()]
        context = active_law_context(value, match.start(), current, law_title_to_id)
        target_law_id, method = context or infer_target_law_id(prefix, current.law_id, law_title_to_id)
        target = by_law_no.get(target_law_id, {}).get(article_no)
        if not target:
            continue
        if target.law_id == current.law_id and target.article_id == current.article_id:
            continue
        confidence = 1.0 if method != "rule:same-law" else 0.9
        add_ref(refs, seen, field=field, text=match.group(0), target=target, method=method, confidence=confidence)

    return refs


def generate_links(laws: list[dict]) -> list[dict]:
    by_law_no, sequence_by_law, law_title_to_id = load_indexes(laws)
    output: list[dict] = []

    for law in laws:
        for chapter in law.get("chapters", []):
            for article in chapter.get("articles", []):
                current = ArticleRef(
                    law_id=law["id"],
                    law_title=law["title"],
                    article_id=article["id"],
                    article_no=article["no"],
                    title=article["title"],
                )
                refs: list[dict] = []
                for field in ("text", "explanation"):
                    refs.extend(
                        scan_field(
                            field=field,
                            value=article.get(field, ""),
                            current=current,
                            by_law_no=by_law_no,
                            sequence_by_law=sequence_by_law,
                            law_title_to_id=law_title_to_id,
                        )
                    )
                if refs:
                    output.append(
                        {
                            "source": source_key(law["id"], article["id"]),
                            "sourceLawId": law["id"],
                            "sourceArticleId": article["id"],
                            "refs": refs,
                        }
                    )
    return output


def main() -> None:
    laws = json.loads(DEFAULT_LAWS.read_text(encoding="utf-8"))
    links = generate_links(laws)
    DEFAULT_OUT.write_text(json.dumps(links, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ref_count = sum(len(item["refs"]) for item in links)
    print(f"Wrote {DEFAULT_OUT.relative_to(ROOT)}")
    print(f"Sources with links: {len(links)}")
    print(f"Total links: {ref_count}")


if __name__ == "__main__":
    main()
