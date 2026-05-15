#!/usr/bin/env python3
"""
Generate display-only layout blocks for law explanations with Gemini.

Input:
  data/laws.json

Output:
  data/law-explanation-layouts.json

Environment:
  GEMINI_API_KEY=...
  or GOOGLE_API_KEY=...
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_INPUT = ROOT / "data" / "laws.json"
DEFAULT_OUTPUT = ROOT / "data" / "law-explanation-layouts.json"
DEFAULT_CACHE = ROOT / ".tmp" / "law_explanation_layouts_gemini" / "cache.json"
PROMPT_VERSION = "law-layout-v1"

SYSTEM_PROMPT = """你是台灣法條解釋的閱讀排版助手。
你的任務只有「把既有白話解釋切成適合閱讀的排版 blocks」，不得重新解釋法條、不得補充新資訊、不得改變原意。

請只輸出 JSON，格式如下：
{
  "blocks": [
    { "type": "paragraph", "text": "一段自然文字" },
    { "type": "definitionList", "items": [
      { "term": "名詞", "text": "名詞說明" }
    ] },
    { "type": "bulletList", "items": ["重點一", "重點二"] },
    { "type": "steps", "items": ["第一步", "第二步"] }
  ]
}

規則：
1. 只使用輸入的「白話解釋」內容，不要加入法條外資訊。
2. 儘量保留原文字句，不要改寫成另一種說法。
3. 一般敘述用 paragraph。
4. 多個名詞定義用 definitionList。
5. 多個並列重點用 bulletList。
6. 明顯流程或順序用 steps。
7. 不要輸出 Markdown、標題、註解或 JSON 以外文字。
"""


class RateLimiter:
    def __init__(self, rpm: int, tpm: int) -> None:
        self.rpm = max(1, rpm)
        self.tpm = max(1, tpm)
        self.requests: deque[float] = deque()
        self.tokens: deque[tuple[float, int]] = deque()

    def wait(self, estimated_tokens: int) -> None:
        while True:
            now = time.time()
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            while self.tokens and now - self.tokens[0][0] >= 60:
                self.tokens.popleft()
            used_tokens = sum(tokens for _, tokens in self.tokens)
            if len(self.requests) < self.rpm and used_tokens + estimated_tokens <= self.tpm:
                self.requests.append(now)
                self.tokens.append((now, estimated_tokens))
                return
            waits = []
            if self.requests:
                waits.append(60 - (now - self.requests[0]))
            if self.tokens:
                waits.append(60 - (now - self.tokens[0][0]))
            time.sleep(max(0.2, min(waits or [1.0])))


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_api_key(env_path: Path) -> str:
    env = read_env(env_path)
    api_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(f"Missing API key. Add GEMINI_API_KEY=... or GOOGLE_API_KEY=... to {env_path}")
    return api_key


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def source_key(law: dict[str, Any], article: dict[str, Any]) -> str:
    return f"{law['id']}::{article['id']}"


def cache_key(source: str, explanation: str, model: str) -> str:
    payload = json.dumps(
        {
            "promptVersion": PROMPT_VERSION,
            "model": model,
            "source": source,
            "explanation": explanation,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iter_articles(laws: list[dict[str, Any]]):
    for law in laws:
        for chapter in law.get("chapters", []):
            for article in chapter.get("articles", []):
                yield law, chapter, article


def build_prompt(law: dict[str, Any], chapter: dict[str, Any], article: dict[str, Any]) -> str:
    return f"""請替下面這段白話解釋產生閱讀排版 blocks。

法規：{law.get("title", "")}
章節：{chapter.get("title", "")}
條號：{article.get("title", "")}

白話解釋：
{article.get("explanation", "").strip()}
"""


def extract_response_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
    return json.loads(text)


def normalize_blocks(value: Any) -> list[dict[str, Any]]:
    raw_blocks = value.get("blocks") if isinstance(value, dict) else value
    if not isinstance(raw_blocks, list):
        raise ValueError("missing blocks array")

    blocks: list[dict[str, Any]] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            continue
        block_type = raw.get("type")
        if block_type == "paragraph":
            text = str(raw.get("text", "")).strip()
            if text:
                blocks.append({"type": "paragraph", "text": text})
        elif block_type == "definitionList":
            items = []
            for item in raw.get("items", []):
                if not isinstance(item, dict):
                    continue
                term = str(item.get("term", "")).strip()
                text = str(item.get("text", "")).strip()
                if term and text:
                    items.append({"term": term, "text": text})
            if items:
                blocks.append({"type": "definitionList", "items": items})
        elif block_type in {"bulletList", "steps"}:
            items = [str(item).strip() for item in raw.get("items", []) if str(item).strip()]
            if items:
                blocks.append({"type": block_type, "items": items})
    if not blocks:
        raise ValueError("empty normalized blocks")
    return blocks


def fallback_layout(explanation: str) -> list[dict[str, Any]]:
    return [{"type": "paragraph", "text": explanation.strip()}] if explanation.strip() else []


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model_path = model if model.startswith("models/") else f"models/{model}"
    endpoint = f"{API_BASE}/{model_path}:generateContent?{urllib.parse.urlencode({'key': api_key})}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
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
    blocks = normalize_blocks(parse_json_object(text))
    return blocks, data.get("usageMetadata", {})


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    estimated_tokens = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(prompt) + max_output_tokens
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt:
            print(f"  retry {attempt}/{max_retries}...", flush=True)
        limiter.wait(estimated_tokens)
        try:
            return call_gemini(
                api_key=api_key,
                model=model,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout=timeout,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {body[:800]}")
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_retries:
                wait = min(30.0, 1.5 * (attempt + 1))
                print(f"  HTTP {exc.code}; waiting {wait:.1f}s", flush=True)
                time.sleep(wait)
                continue
            break
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
            ConnectionError,
            OSError,
            http.client.RemoteDisconnected,
        ) as exc:
            last_error = exc
            if attempt < max_retries:
                wait = min(30.0, 1.5 * (attempt + 1))
                print(f"  {type(exc).__name__}: {exc}; waiting {wait:.1f}s", flush=True)
                time.sleep(wait)
                continue
            break
    raise RuntimeError(f"Gemini layout generation failed: {last_error}") from last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate display-only law explanation layouts with Gemini.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rpm", type=int, default=4000)
    parser.add_argument("--tpm", type=int, default=4_000_000)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    laws = json.loads(args.input.read_text(encoding="utf-8"))
    cache = load_cache(args.cache)
    api_key = "" if args.dry_run else get_api_key(args.env)
    limiter = RateLimiter(args.rpm, args.tpm)

    articles = [
        (law, chapter, article)
        for law, chapter, article in iter_articles(laws)
        if article.get("explanation", "").strip()
    ]
    total = len(articles)
    selected_articles = articles[: args.limit] if args.limit else articles
    print(f"Model: {args.model}")
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Articles with explanations: {total}, selected: {len(selected_articles)}")

    layouts: list[dict[str, Any]] = []
    generated = 0

    for law, chapter, article in selected_articles:
        explanation = article.get("explanation", "").strip()

        source = source_key(law, article)
        key = cache_key(source, explanation, args.model)
        if not args.refresh and key in cache and cache[key].get("blocks"):
            blocks = normalize_blocks(cache[key]["blocks"])
            print(f"[cache] {law['title']} {article['title']}")
        elif args.dry_run:
            blocks = fallback_layout(explanation)
            print(f"[dry] {law['title']} {article['title']}")
            generated += 1
        else:
            prompt = build_prompt(law, chapter, article)
            print(f"[api] {law['title']} {article['title']}", flush=True)
            try:
                blocks, usage = generate_with_retry(
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
            cache[key] = {
                "source": source,
                "law": law.get("title", ""),
                "article": article.get("title", ""),
                "model": args.model,
                "promptVersion": PROMPT_VERSION,
                "blocks": blocks,
                "usage": usage,
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            generated += 1
            save_cache(args.cache, cache)

        layouts.append(
            {
                "source": source,
                "lawTitle": law.get("title", ""),
                "articleTitle": article.get("title", ""),
                "blocks": blocks,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(layouts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_cache(args.cache, cache)
    print(f"Wrote layouts: {args.output}")
    print(f"Wrote cache: {args.cache}")


if __name__ == "__main__":
    main()
