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
DEFAULT_MODEL = "gemini-3.1-flash-lite"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

LAW_ORDER = ["水利法.txt", "水利法施行細則.txt", "水污染防治法.txt"]
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


def parse_law_file(path: Path, source_root: Path) -> Law:
    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = source.split("\n")
    first_non_empty = next((line.strip() for line in lines if line.strip()), "")
    has_title = bool(first_non_empty) and not looks_like_chapter(first_non_empty)
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

        article_match = re.match(r"^第\s*([一二三四五六七八九十百零0-9\-－—]+)\s*條", line)
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


def build_prompt(law: Law, chapter: Chapter, article: Article) -> str:
    return f"""你是台灣法規白話解釋助手。請根據輸入的法規名稱、章節、條號與法條原文，產生適合一般民眾與考生閱讀的繁體中文白話解釋。

請嚴格輸出 JSON：
{{"explanation":"..."}}

風格要求：
1. explanation 使用繁體中文。
2. 口語、直接、好懂，但不要玩笑化，也不要過度隨便。
3. 用白話說明這條在管什麼、誰需要注意、實務上代表什麼。
4. 若是考試常見重點，可以自然點出，但不要寫成條列。
5. 不要改寫或重複輸出法條原文。
6. 不要使用 Markdown，不要條列。
7. 長度以 100 到 180 字為主；複雜條文可稍長。
8. 不得編造法條沒有寫的罰鍰數字、期限、條件、例外或主管機關。

以下是解釋風格範例，請學習口吻與密度：

=== 範例 1 ===
輸入：
法規：水污染防治法
章節：第 一 章 總則
條號：第 1 條
法條：
為防治水污染，確保水資源之清潔，以維護生態體系，改善生活環境，增進國民健康，特制定本法。本法未規定者，適用其他法令之規定。

輸出：
{{"explanation":"本條是在說《水污染防治法》為什麼存在。重點就是避免水被污染，讓河川、湖泊、地下水等水資源維持乾淨，也同時保護生態、生活環境和人民健康。如果遇到本法沒有寫清楚的事情，就會再回去適用其他相關法律。"}}

=== 範例 2 ===
輸入：
法規：水污染防治法
章節：第 二 章 基本措施
條號：第 7 條
法條：
事業、污水下水道系統或建築物污水處理設施，排放廢（污）水於地面水體者，應符合放流水標準。

輸出：
{{"explanation":"這條是水污染管制很核心的規定。工廠、事業單位、污水下水道系統或大樓污水處理設施，如果要把廢水排進河川、湖泊這類地面水體，排出去的水就必須達到政府訂的放流水標準。也就是說，不是不能排，而是不能把沒處理好、沒達標的水直接排出去。"}}

=== 範例 3 ===
輸入：
法規：水污染防治法
章節：第 四 章 罰則
條號：第 34 條
法條：
違反第七條第一項或第八條規定者，處新臺幣六萬元以上二千萬元以下罰鍰，並通知限期改善，屆期仍未完成改善者，按次處罰；情節重大者，得令其停工或停業；必要時，並得廢止其水污染防治許可證（文件）或勒令歇業。

輸出：
{{"explanation":"這條是在說排放廢水沒有符合標準時，後果會很重。違規者不只會被罰錢，主管機關還會要求限期改善；如果期限到了還沒改善，可以一直按次處罰。情節嚴重時，甚至可能被要求停工、停業，或被廢止水污染防治相關許可，最後可能到勒令歇業的程度。"}}

=== 任務 ===
法規：{law.title}
章節：{chapter.title}
條號：{article.title}
法條：
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
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
        explanation = str(payload.get("explanation", "")).strip()
        if explanation:
            return explanation
    except json.JSONDecodeError:
        pass
    return cleaned


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    model_path = model if model.startswith("models/") else f"models/{model}"
    endpoint = f"{API_BASE}/{model_path}:generateContent?{urllib.parse.urlencode({'key': api_key})}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
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
    return parse_explanation(text), data.get("usageMetadata", {})


def should_retry(status: int | None) -> bool:
    return status in {None, 408, 409, 429, 500, 502, 503, 504}


def generate_with_retry(
    *,
    api_key: str,
    model: str,
    prompt: str,
    limiter: RateLimiter,
    max_retries: int,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    estimated_tokens = estimate_tokens(prompt) + max_output_tokens
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
                max_output_tokens=max_output_tokens,
                temperature=temperature,
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
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=20)
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
                    article.explanation = cache[key]["explanation"]
                    print(f"[cache] {law.title} {article.title}")
                    continue

                prompt = build_prompt(law, chapter, article)
                print(f"[api] {law.title} {article.title}", flush=True)
                try:
                    explanation, usage = generate_with_retry(
                        api_key=api_key,
                        model=args.model,
                        prompt=prompt,
                        limiter=limiter,
                        max_retries=args.max_retries,
                        max_output_tokens=args.max_output_tokens,
                        temperature=args.temperature,
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
