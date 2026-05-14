#!/usr/bin/env python3
"""
Generate law article explanations with the Gemini API.

Default input:
  法條/完整版/*.txt

Default outputs:
  法條/AI解釋/*.txt
  data/laws.generated.json
  .tmp/law_explanations_gemini/cache.json

Environment:
  GEMINI_API_KEY=...
  or GOOGLE_API_KEY=...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "法條" / "完整版"
DEFAULT_OUT_DIR = ROOT / "法條" / "AI解釋"
DEFAULT_JSON_OUT = ROOT / "data" / "laws.generated.json"
DEFAULT_CACHE = ROOT / ".tmp" / "law_explanations_gemini" / "cache.json"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
PROMPT_VERSION = "gemini-v7-simplified-system-lenient-validation"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

LAW_ORDER = [
    "水利法.txt",
    "水利法施行細則.txt",
    "水污染防治法.txt",
    "水污染防治法施行細則.txt",
    "土壤及地下水污染整治法.txt",
    "土壤及地下水污染整治法施行細則.txt",
    "農田水利法.txt",
    "農田水利法施行細則.txt",
    "農田灌溉排水管理辦法.txt",
    "灌溉管理組織設置辦法.txt",
]
KNOWN_LAW_IDS = {
    "水利法": "water-act",
    "水利法施行細則": "water-act-enforcement-rules",
    "水污染防治法": "water-pollution-control-act",
}

DEFAULT_SUMMARIES = {
    "水利法": [
        "水資源屬於國家所有，用水、取水與水利事業興辦都要回到法定管理架構。",
        "考試重點通常集中在主管機關、水權、水利事業、河川與海堤管理、災害防護及罰則。",
        "閱讀順序建議先掌握總則與水權，再看水利建造物、河川管理與行政處分。",
    ],
    "水利法施行細則": [
        "施行細則負責補足水利法的操作定義與行政程序，是理解水利法實務執行的輔助規範。",
        "考試重點通常集中在名詞定義、水權登記、主管機關處理程序與水利事業執行細節。",
        "閱讀時可搭配水利法母法條文，先記定義，再看程序與例外。",
    ],
    "水污染防治法": [
        "核心目標是防治水污染、維持水體用途、管制廢污水排放並建立責任與裁罰制度。",
        "考試重點通常集中在主管機關、事業定義、排放許可、污染防治措施、監測申報與罰則。",
        "閱讀時建議先抓總則與基本措施，再整理許可、管制、裁罰之間的關係。",
    ],
    "水污染防治法施行細則": [
        "本細則補充水污染防治法的執行細節，重點在名詞、許可、申報、監測與主管機關作業程序。",
        "讀法上應搭配母法的防治措施與罰則，先理解事業、污水下水道系統與各類許可文件如何運作。",
        "考試常考程序性規定，例如資料提報、檢測紀錄、改善期限與主管機關通知方式。",
    ],
    "土壤及地下水污染整治法": [
        "核心架構是發現污染後，如何調查、公告控制場址或整治場址，並要求污染責任人處理。",
        "重點在污染行為人、潛在污染責任人、污染土地關係人之間的責任分配，以及控制計畫、整治計畫與費用負擔。",
        "閱讀時建議先抓場址公告流程，再整理管制措施、整治復育、基金費用與罰則。",
    ],
    "土壤及地下水污染整治法施行細則": [
        "本細則補充土壤及地下水污染整治法的資料、公告、通知、計畫內容與執行程序。",
        "重點是把母法中的調查評估、控制計畫、整治計畫與場址管理，轉成具體行政作業要求。",
        "讀法上可搭配母法第十二條以後的場址處理流程，特別注意文件內容與主管機關審查節點。",
    ],
    "農田水利法": [
        "本法規範農田水利設施、灌溉排水管理、農田水利事業組織、經費與罰則。",
        "考試重點通常集中在主管機關、農田水利設施範圍、灌溉用水、非農田排水、管理組織與作業基金。",
        "閱讀時建議先掌握設施管理與灌溉排水規則，再看組織、人員、經費及罰則。",
    ],
    "農田水利法施行細則": [
        "本細則補充農田水利法的具體執行規定，主要說明設施使用、灌溉管理組織、人員訓練與財務作業。",
        "重點在母法條文如何落地，例如照舊使用、作業基金設置前的預算與決算處理。",
        "閱讀時適合搭配農田水利法第二章到第五章，補足制度轉換與行政執行細節。",
    ],
    "農田灌溉排水管理辦法": [
        "本辦法是農田灌溉排水管理的操作規範，重點在設施範圍、兼作使用、排水許可、水質與違規處理。",
        "考試常見重點包含非農田排水、灌溉水質基準、許可申請、補正、展延、變更與廢止。",
        "閱讀時可依申請流程整理：哪些行為要許可、主管機關如何審查、違規後如何改善或處罰。",
    ],
    "灌溉管理組織設置辦法": [
        "本辦法規範農田水利事業灌溉管理組織的設置、任務、區域、人員與運作方式。",
        "重點在灌溉管理組織如何協助農田水利設施管理與灌溉服務，屬於農田水利法下位的組織性規定。",
        "閱讀時可先掌握設置目的與任務，再看組織區域、管理事項與主管機關監督。",
    ],
}


@dataclass
class Article:
    id: str
    no: str
    title: str
    text: str = ""
    explanation: str = ""


@dataclass
class Chapter:
    id: str
    no: str
    title: str
    articles: list[Article] = field(default_factory=list)


@dataclass
class Law:
    id: str
    title: str
    source_file: str
    summary: list[str]
    chapters: list[Chapter] = field(default_factory=list)


class RateLimiter:
    def __init__(self, rpm: int, tpm: int) -> None:
        self.rpm = max(1, rpm)
        self.tpm = max(1, tpm)
        self.requests: deque[float] = deque()
        self.tokens: deque[tuple[float, int]] = deque()

    def wait(self, estimated_tokens: int) -> None:
        now = time.monotonic()
        window = 60.0

        while self.requests and now - self.requests[0] >= window:
            self.requests.popleft()
        while self.tokens and now - self.tokens[0][0] >= window:
            self.tokens.popleft()

        token_sum = sum(tokens for _, tokens in self.tokens)
        wait_until = now

        if len(self.requests) >= self.rpm and self.requests:
            wait_until = max(wait_until, self.requests[0] + window)
        if token_sum + estimated_tokens > self.tpm and self.tokens:
            wait_until = max(wait_until, self.tokens[0][0] + window)

        delay = wait_until - now
        if delay > 0:
            time.sleep(delay)

        stamp = time.monotonic()
        self.requests.append(stamp)
        self.tokens.append((stamp, estimated_tokens))


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_api_key(env_path: Path) -> str:
    env = read_env(env_path)
    api_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(
            f"Missing API key. Add GEMINI_API_KEY=... or GOOGLE_API_KEY=... to {env_path}"
        )
    return api_key


def normalize_article_no(raw: str) -> str:
    return re.sub(r"\s+", "", raw).replace("－", "-").replace("—", "-")


def slug_article_id(title: str) -> str:
    normalized = normalize_article_no(title)
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", normalized).strip("-").lower()
    return f"article-{normalized or 'unknown'}"


def chapter_id(index: int) -> str:
    return f"chapter-{index + 1}"


def law_id(title: str, filename: str) -> str:
    if title in KNOWN_LAW_IDS:
        return KNOWN_LAW_IDS[title]
    fallback = re.sub(r"\.[^.]+$", "", filename)
    fallback = re.sub(r"\s+", "-", fallback)
    fallback = re.sub(r"[^\w-]+", "", fallback).lower()
    return fallback or "law"


def looks_like_chapter(line: str) -> bool:
    return bool(re.match(r"^第\s*[一二三四五六七八九十百零0-9]+\s*章", line.strip()))


def looks_like_article(line: str) -> bool:
    return bool(re.match(r"^第\s*[一二三四五六七八九十百零0-9\-－—]+\s*條\s*(?:（刪除）|\(刪除\))?\s*$", line.strip()))


def parse_law_file(path: Path, source_root: Path) -> Law:
    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = source.split("\n")
    first_non_empty = next((line.strip() for line in lines if line.strip()), "")
    has_title = bool(first_non_empty) and not looks_like_chapter(first_non_empty) and not looks_like_article(first_non_empty)
    title = first_non_empty if has_title else path.stem
    body_lines = lines[1:] if has_title else lines

    law = Law(
        id=law_id(title, path.name),
        title=title,
        source_file=str(path.relative_to(ROOT)).replace("\\", "/"),
        summary=DEFAULT_SUMMARIES.get(
            title,
            [
                "本整理包含完整法條與 AI 產生的解釋，可依法律與章節篩選閱讀。",
                "建議先掌握總則、主管機關與罰則，再回頭整理細節。",
            ],
        ),
    )

    current_chapter: Chapter | None = None
    current_article: Article | None = None
    mode = "text"

    def push_article() -> None:
        nonlocal current_chapter, current_article
        if not current_article:
            return
        current_article.text = current_article.text.strip()
        current_article.explanation = current_article.explanation.strip()
        if not current_chapter:
            current_chapter = Chapter(chapter_id(len(law.chapters)), "", "未分章")
            law.chapters.append(current_chapter)
        current_chapter.articles.append(current_article)
        current_article = None

    for raw_line in body_lines:
        line = raw_line.strip()
        if not line:
            continue

        chapter_match = re.match(r"^第\s*([一二三四五六七八九十百零0-9]+)\s*章\s*(.*)$", line)
        if chapter_match:
            push_article()
            mode = "text"
            no = chapter_match.group(1)
            suffix = chapter_match.group(2).strip()
            current_chapter = Chapter(
                id=chapter_id(len(law.chapters)),
                no=no,
                title=f"第 {no} 章{(' ' + suffix) if suffix else ''}",
            )
            law.chapters.append(current_chapter)
            continue

        article_match = re.match(r"^第\s*([一二三四五六七八九十百零0-9\-－—]+)\s*條\s*(?:（刪除）|\(刪除\))?\s*$", line)
        if article_match:
            push_article()
            no = normalize_article_no(article_match.group(1))
            current_article = Article(id=slug_article_id(line), no=no, title=line)
            mode = "text"
            continue

        explanation_match = re.match(r"^解釋[：:]\s*(.*)$", line)
        if explanation_match and current_article:
            mode = "explanation"
            if explanation_match.group(1).strip():
                current_article.explanation += explanation_match.group(1).strip() + "\n"
            continue

        if not current_article:
            continue
        if mode == "explanation":
            current_article.explanation += line + "\n"
        else:
            current_article.text += line + "\n"

    push_article()
    return law


def article_count(law: Law) -> int:
    return sum(len(chapter.articles) for chapter in law.chapters)


def is_deleted_article(article: Article) -> bool:
    text = re.sub(r"\s+", "", article.text)
    return text in {"（刪除）", "(刪除)", "刪除", "（删除）", "(删除)", "删除"}


def deleted_explanation() -> str:
    return "本條已刪除，現行法中沒有實質規範內容。閱讀時只需要知道這個條號曾經存在，但目前不需要背誦條文內容或適用要件。"


def builtin_explanation(article: Article) -> str:
    text = re.sub(r"\s+", "", article.text)
    if is_deleted_article(article):
        return deleted_explanation()
    if re.fullmatch(r"本法施行細則[，,]?由中央主管機關定之。?", text):
        return "本條是授權規定，意思是這部法律比較細的執行辦法，可以由中央主管機關另外訂定施行細則。閱讀時重點是知道母法只定原則，實際操作細節會放在施行細則裡。"
    if re.fullmatch(r"本法自公布日施行。?", text):
        return "本條是施行日期規定，意思是這部法律從正式公布那天開始生效。這類條文通常不涉及實體權利義務，閱讀時只要知道它是在交代法律何時開始適用即可。"
    return ""


def law_to_json(law: Law) -> dict[str, Any]:
    return {
        "id": law.id,
        "title": law.title,
        "sourceFile": law.source_file,
        "summary": law.summary,
        "chapters": [
            {
                "id": chapter.id,
                "no": chapter.no,
                "title": chapter.title,
                "articles": [
                    {
                        "id": article.id,
                        "no": article.no,
                        "title": article.title,
                        "text": article.text,
                        "explanation": article.explanation,
                    }
                    for article in chapter.articles
                ],
            }
            for chapter in law.chapters
        ],
        "chapterCount": len(law.chapters),
        "articleCount": article_count(law),
    }


def write_law_txt(law: Law, out_path: Path) -> None:
    lines: list[str] = [law.title, ""]
    for chapter in law.chapters:
        lines += [chapter.title, ""]
        for article in chapter.articles:
            lines += [article.title, article.text, "", "解釋：", article.explanation, ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def cache_key(law: Law, chapter: Chapter, article: Article, model: str) -> str:
    payload = json.dumps(
        {
            "promptVersion": PROMPT_VERSION,
            "model": model,
            "law": law.title,
            "chapter": chapter.title,
            "article": article.title,
            "text": article.text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_builtin_articles(laws: list[Law]) -> int:
    count = 0
    for law in laws:
        for chapter in law.chapters:
            for article in chapter.articles:
                explanation = builtin_explanation(article)
                if explanation:
                    article.explanation = explanation
                    count += 1
    return count


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estimate_tokens(text: str) -> int:
    # Conservative enough for rate limiting without an extra tokenizer dependency.
    return max(1, len(text) // 2)


SYSTEM_PROMPT = """你是台灣法條白話解釋助手。請把法條改寫成一般人看得懂的繁體中文，輸出 2 到 3 句純文字。

輸出風格：
- 用一般人容易理解的說法，不要只是把原文換幾個字。
- 可以把長句拆短、重組，但不能改變法律意思。
- 保留必要的法律關鍵字，例如主管機關、核准、核定、公告、前條、罰金、罰鍰。
- 如果是罰則條文，要保留刑罰名稱、金額、期限與後續處分，但用白話整理，不要整段照抄。

硬性限制：
- 只能根據本條原文解釋，不要補法條外的目的、效果、罰則、政策理由或例子。
- 不要把法律強度改掉；原文是「得」就寫「可以」，原文是「應」才寫「必須」。
- 不要把「罰金」和「罰鍰」互換。
- 遇到「前條」時，不要自行展開前條內容；需要時只提醒前條內容要另外參照。
- 只輸出解釋本身，不要 JSON、Markdown、標題或換行。

句型範例：
原文：水為天然資源，屬於國家所有，不因人民取得土地所有權而受影響。
輸出：水是國家的天然資源，不是誰買了土地就能一起擁有。人民取得土地所有權，並不會影響水屬於國家所有這件事。

原文：本法所稱主管機關：在中央為經濟部；在直轄市為直轄市政府；在縣（市）為縣（市）政府。
輸出：這條是在說水利法由哪些機關負責管理。中央層級是經濟部，直轄市是直轄市政府，縣（市）則是縣（市）政府。

原文：中央主管機關按全國水道之天然形勢，劃分水利區，報請行政院核定公告之。
輸出：中央主管機關會依照全國水道的自然情況來劃分水利區。劃分後，還要報請行政院核定並公告。

原文：水利區涉及二縣（市）以上或關係重大縣（市）難以興辦者，其水利事業，得由中央主管機關設置水利機關辦理之。
輸出：如果某個水利區牽涉到兩個以上縣（市），或事情太重大，縣（市）政府自己很難推動，中央就可以出面處理。具體來說，中央主管機關可以設置水利機關來辦理這項水利事業。

原文：直轄市或縣（市）政府辦理水利事業，其利害涉及二直轄市、縣（市）以上者，應經中央主管機關核准。
輸出：地方政府辦理水利事業時，如果影響範圍牽涉到兩個以上直轄市或縣（市），就不能自己決定。直轄市或縣（市）政府必須先取得中央主管機關核准。

原文：引用一水系之水，移注另一水系，以發展該另一水系之水利事業，適用前條之規定。
輸出：如果要把一個水系的水引到另一個水系，用來發展另一水系的水利事業，就要適用前條規定。前條內容需要另外參照。

原文：各級主管機關為辦理水利工程，得向受益人徵工；其辦法應報經上級主管機關核准，並報中央主管機關。
輸出：各級主管機關為了辦理水利工程，可以要求受益人出工協助。徵工辦法必須報經上級主管機關核准，並報中央主管機關。

原文：違反命令者，處一年以下有期徒刑、拘役或科或併科新臺幣十萬元以上五十萬元以下罰金。
輸出：這條是在處罰不遵守命令的人。違反者可能會被判一年以下有期徒刑或拘役，也可能被科或併科新臺幣十萬元以上五十萬元以下罰金。
"""


def build_prompt(law: Law, chapter: Chapter, article: Article) -> str:
    return f"""現在請改寫以下法條：
法律名稱：{law.title}
章節名稱：{chapter.title}
條號：{article.title}
法條原文：
{article.text}
"""


def extract_response_text(data: dict[str, Any]) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Unexpected API response: {json.dumps(data, ensure_ascii=False)[:800]}")


def parse_explanation(text: str) -> str:
    cleaned = text.strip()
    if "<channel|>" in cleaned:
        cleaned = cleaned.rsplit("<channel|>", 1)[-1].strip()
    cleaned = re.sub(r"<\|channel\>thought.*?(?:<channel\|>|$)", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
        explanation = str(payload.get("explanation", "")).strip()
        if explanation:
            return explanation
    except json.JSONDecodeError:
        pass
    for marker in ("改寫後：", "改寫後:", "輸出：", "輸出:"):
        if marker in cleaned:
            cleaned = cleaned.rsplit(marker, 1)[-1].strip()
    cleaned = re.sub(r"^\s*(解釋|白話解釋)\s*[:：]\s*", "", cleaned).strip()
    return re.sub(r"\s*\n+\s*", " ", cleaned).strip()


def has_penalty_term(text: str, term: str) -> bool:
    if term == "罰金":
        # Avoid treating phrases like "裁罰金額" as the criminal penalty term "罰金".
        return bool(re.search(r"(?<!裁)罰金(?!額)", text))
    return term in text


def missing_money_ranges(source: str, explanation: str) -> list[str]:
    ranges = re.findall(r"新臺幣[^，。；、\s]+以上[^，。；、\s]+以下", source)
    return [money for money in dict.fromkeys(ranges) if money not in explanation]


def repair_explanation(article: Article, explanation: str) -> str:
    source = article.text
    repaired = explanation.strip()
    additions: list[str] = []

    source_has_fine = has_penalty_term(source, "罰金")
    source_has_admin_fine = has_penalty_term(source, "罰鍰")

    if "科或併科" in source and "科或併科" not in repaired:
        additions.append("原文用語是「科或併科」，表示可以單獨科罰金，也可以和其他刑罰一起併科。")
    if source_has_fine and not has_penalty_term(repaired, "罰金"):
        additions.append("原文的處罰種類是罰金。")
    if source_has_admin_fine and not has_penalty_term(repaired, "罰鍰"):
        additions.append("原文的處罰種類是罰鍰。")

    money = missing_money_ranges(source, repaired)
    if money:
        additions.append(f"原文金額區間為：{'、'.join(money)}。")

    if additions:
        repaired = f"{repaired} {' '.join(additions)}".strip()
    return repaired


def validate_explanation(article: Article, explanation: str, strict: bool = False) -> list[str]:
    source = article.text
    errors: list[str] = []
    warnings: list[str] = []

    source_has_fine = has_penalty_term(source, "罰金")
    source_has_admin_fine = has_penalty_term(source, "罰鍰")
    explanation_has_fine = has_penalty_term(explanation, "罰金")
    explanation_has_admin_fine = has_penalty_term(explanation, "罰鍰")

    if source_has_fine and not source_has_admin_fine and explanation_has_admin_fine and not explanation_has_fine:
        errors.append("source uses 罰金 but explanation appears to use 罰鍰 instead")
    if source_has_admin_fine and not source_has_fine and explanation_has_fine and not explanation_has_admin_fine:
        errors.append("source uses 罰鍰 but explanation appears to use 罰金 instead")

    checks = [
        ("科或併科", "科或併科" in source, "科或併科" in explanation),
        ("有期徒刑", "有期徒刑" in source, "有期徒刑" in explanation),
        ("拘役", "拘役" in source, "拘役" in explanation),
        ("罰金", source_has_fine, explanation_has_fine),
        ("罰鍰", source_has_admin_fine, explanation_has_admin_fine),
    ]
    warnings += [f"missing protected term: {term}" for term, in_source, in_explanation in checks if in_source and not in_explanation]
    warnings += [f"missing exact money range: {money}" for money in missing_money_ranges(source, explanation)]

    if errors or (strict and warnings):
        raise ValueError("; ".join(errors + warnings))
    return warnings


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    article: Article,
    max_output_tokens: int,
    temperature: float,
    thinking_level: str,
    strict_validation: bool,
    timeout: int,
) -> tuple[str, dict[str, Any], list[str]]:
    model_path = model if model.startswith("models/") else f"models/{model}"
    endpoint = f"{API_BASE}/{model_path}:generateContent?{urllib.parse.urlencode({'key': api_key})}"
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if thinking_level != "none":
        generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "generationConfig": generation_config,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = extract_response_text(data)
    explanation = repair_explanation(article, parse_explanation(text))
    warnings = validate_explanation(article, explanation, strict=strict_validation)
    return explanation, data.get("usageMetadata", {}), warnings


def should_retry(status: int | None) -> bool:
    return status in {None, 408, 409, 429, 500, 502, 503, 504}


def generate_with_retry(
    *,
    api_key: str,
    model: str,
    prompt: str,
    article: Article,
    limiter: RateLimiter,
    max_retries: int,
    max_output_tokens: int,
    temperature: float,
    thinking_level: str,
    strict_validation: bool,
    timeout: int,
) -> tuple[str, dict[str, Any], list[str]]:
    estimated_tokens = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(prompt) + max_output_tokens
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        limiter.wait(estimated_tokens)
        try:
            if attempt > 0:
                print(f"  retry {attempt}/{max_retries}...", flush=True)
            return call_gemini(
                api_key=api_key,
                model=model,
                prompt=prompt,
                article=article,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                thinking_level=thinking_level,
                strict_validation=strict_validation,
                timeout=timeout,
            )
        except urllib.error.HTTPError as exc:
            last_error = exc
            body = exc.read().decode("utf-8", errors="replace")
            if not should_retry(exc.code) or attempt >= max_retries:
                raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:1000]}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            print(f"  HTTP {exc.code}; waiting {delay:.1f}s", flush=True)
        except ValueError as exc:
            last_error = exc
            if attempt >= max_retries:
                raise RuntimeError(f"Gemini validation failed: {exc}") from exc
            delay = 1 + attempt
            print(f"  validation failed: {exc}; retrying after {delay:.1f}s", flush=True)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise RuntimeError(f"Gemini request failed: {exc}") from exc
            delay = 2 ** attempt
            print(f"  request failed: {exc}; waiting {delay:.1f}s", flush=True)

        time.sleep(delay + random.uniform(0, 0.5))

    raise RuntimeError(f"Gemini request failed: {last_error}")


def check_model_available(api_key: str, model: str, timeout: int) -> None:
    model_path = model if model.startswith("models/") else f"models/{model}"
    endpoint = f"{API_BASE}/{model_path}?{urllib.parse.urlencode({'key': api_key})}"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Model check failed HTTP {exc.code}: {body[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Model check failed: {exc}") from exc

    supported = data.get("supportedGenerationMethods", [])
    if "generateContent" not in supported:
        raise RuntimeError(f"Model {model} does not list generateContent support: {supported}")


def iter_law_files(source_dir: Path) -> list[Path]:
    files = sorted(
        [path for path in source_dir.glob("*.txt")],
        key=lambda p: (
            LAW_ORDER.index(p.name) if p.name in LAW_ORDER else 999,
            p.name,
        ),
    )
    if not files:
        raise SystemExit(f"No .txt files found in {source_dir}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate full law explanations with Gemini.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rpm", type=int, default=4000)
    parser.add_argument("--tpm", type=int, default=4_000_000)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.15)
    parser.add_argument(
        "--thinking-level",
        choices=["none", "minimal", "low", "medium", "high"],
        default="minimal",
        help="Gemini 3 thinking level. Use none to omit thinkingConfig.",
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Retry when protected legal terms or exact money ranges are omitted.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only process N missing explanations.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without calling the API.")
    parser.add_argument("--skip-model-check", action="store_true", help="Skip the model metadata check.")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Regenerate explanations even when the source already has one.",
    )
    args = parser.parse_args()

    api_key = "" if args.dry_run else get_api_key(args.env)
    source_dir = args.source_dir.resolve()
    laws = [parse_law_file(path, source_dir) for path in iter_law_files(source_dir)]
    builtin_articles = normalize_builtin_articles(laws)
    total_articles = sum(article_count(law) for law in laws)
    missing_articles = sum(
        1
        for law in laws
        for chapter in law.chapters
        for article in chapter.articles
        if not builtin_explanation(article)
        and (args.refresh_existing or not article.explanation.strip())
    )

    print(f"Model: {args.model}")
    print(f"Rate limit: RPM={args.rpm}, TPM={args.tpm}")
    print(f"Thinking level: {args.thinking_level}")
    print(f"Timeout: {args.timeout}s")
    print(
        f"Parsed laws: {len(laws)}, articles: {total_articles}, "
        f"builtin: {builtin_articles}, to generate: {missing_articles}"
    )
    for law in laws:
        print(f"- {law.title}: {len(law.chapters)} 章 / {article_count(law)} 條")

    if args.dry_run:
        return

    if not args.skip_model_check:
        print(f"Checking model availability: {args.model}", flush=True)
        check_model_available(api_key, args.model, args.timeout)
        print("Model check OK", flush=True)

    cache = load_cache(args.cache)
    limiter = RateLimiter(args.rpm, args.tpm)
    generated = 0

    for law in laws:
        for chapter in law.chapters:
            for article in chapter.articles:
                if builtin_explanation(article):
                    continue
                if article.explanation.strip() and not args.refresh_existing:
                    continue
                if args.limit and generated >= args.limit:
                    break

                key = cache_key(law, chapter, article, args.model)
                if key in cache and cache[key].get("explanation"):
                    article.explanation = repair_explanation(article, parse_explanation(cache[key]["explanation"]))
                    if article.explanation != cache[key]["explanation"]:
                        cache[key]["explanation"] = article.explanation
                    print(f"[cache] {law.title} {article.title}")
                    continue

                prompt = build_prompt(law, chapter, article)
                print(f"[api] {law.title} {article.title}", flush=True)
                try:
                    explanation, usage, validation_warnings = generate_with_retry(
                        api_key=api_key,
                        model=args.model,
                        prompt=prompt,
                        article=article,
                        limiter=limiter,
                        max_retries=args.max_retries,
                        max_output_tokens=args.max_output_tokens,
                        temperature=args.temperature,
                        thinking_level=args.thinking_level,
                        strict_validation=args.strict_validation,
                        timeout=args.timeout,
                    )
                except KeyboardInterrupt:
                    save_cache(args.cache, cache)
                    print("\nInterrupted. Cache saved; rerun the same command to continue.", flush=True)
                    raise SystemExit(130)
                article.explanation = explanation
                cache[key] = {
                    "law": law.title,
                    "chapter": chapter.title,
                    "article": article.title,
                    "model": args.model,
                    "promptVersion": PROMPT_VERSION,
                    "thinkingLevel": args.thinking_level,
                    "validationWarnings": validation_warnings,
                    "explanation": explanation,
                    "usage": usage,
                    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
                generated += 1
                save_cache(args.cache, cache)

            if args.limit and generated >= args.limit:
                break
        if args.limit and generated >= args.limit:
            break

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for law in laws:
        write_law_txt(law, args.out_dir / f"{law.title}.txt")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps([law_to_json(law) for law in laws], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    save_cache(args.cache, cache)

    print(f"Wrote text output: {args.out_dir}")
    print(f"Wrote JSON output: {args.json_out}")
    print(f"Wrote cache: {args.cache}")


if __name__ == "__main__":
    main()
