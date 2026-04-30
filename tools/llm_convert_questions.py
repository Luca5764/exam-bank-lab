import argparse
import difflib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from opencc import OpenCC


POSTPROCESS_REPLACEMENTS = {
    "覈": "核",
    "爲": "為",
    "裏": "裡",
    "麪": "麵",
}


SYSTEM_PROMPT = (
    "You are a Traditional Chinese proofreading assistant. "
    "Your only task is to convert Simplified Chinese characters in quiz text "
    "to Traditional Chinese. Do not rewrite wording, tone, order, punctuation, "
    "numbers, answer options, proper nouns, legal terms, or accounting terms. "
    "If the input is already Traditional Chinese, keep it unchanged. "
    "Return JSON only, with no extra explanation."
)


USER_TEMPLATE = """Convert Simplified Chinese characters in the following JSON to Traditional Chinese.
Preserve every other detail exactly.

Input JSON:
{payload}

Return only this JSON shape:
{{"question":"...","options":["...","..."]}}"""


def ollama_chat(model: str, payload: dict[str, Any], host: str) -> dict[str, Any]:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False))},
        ],
        "options": {
            "temperature": 0,
            "top_p": 0.1,
        },
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["message"]["content"]
    return json.loads(content)


def should_process(item: dict[str, Any], cc: OpenCC) -> bool:
    texts = [item.get("question", "")]
    texts.extend(item.get("options", []))
    return any(isinstance(t, str) and cc.convert(t) != t for t in texts)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def postprocess_text(text: str) -> str:
    for old, new in POSTPROCESS_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def still_has_convertible_simplified(text: str, cc: OpenCC) -> bool:
    converted = postprocess_text(cc.convert(text))
    return converted != postprocess_text(text)


def looks_too_different(original: str, candidate: str, baseline: str) -> bool:
    base_ratio = difflib.SequenceMatcher(a=original, b=baseline).ratio()
    cand_ratio = difflib.SequenceMatcher(a=original, b=candidate).ratio()
    return cand_ratio + 0.02 < base_ratio


def validate_result(original: dict[str, Any], converted: dict[str, Any], cc: OpenCC) -> dict[str, Any]:
    question = converted.get("question", original["question"])
    options = converted.get("options", original["options"])

    if not isinstance(question, str):
        question = original["question"]
    if not isinstance(options, list) or len(options) != len(original["options"]):
        options = original["options"]

    cleaned_options = []
    for idx, opt in enumerate(options):
        if not isinstance(opt, str):
            cleaned_options.append(original["options"][idx])
            continue
        cleaned_options.append(opt)

    result = {
        "question": question,
        "options": cleaned_options,
    }

    # Safety rail: never allow the LLM to diverge beyond the OpenCC-s2t target.
    baseline = {
        "question": postprocess_text(cc.convert(original["question"])),
        "options": [postprocess_text(cc.convert(opt)) for opt in original["options"]],
    }

    if (
        normalize_text(result["question"]) == ""
        or still_has_convertible_simplified(result["question"], cc)
        or looks_too_different(original["question"], result["question"], baseline["question"])
    ):
        result["question"] = baseline["question"]
    else:
        result["question"] = postprocess_text(result["question"])

    fixed_options = []
    for old_opt, new_opt, base_opt in zip(original["options"], result["options"], baseline["options"]):
        if (
            normalize_text(new_opt) == ""
            or still_has_convertible_simplified(new_opt, cc)
            or looks_too_different(old_opt, new_opt, base_opt)
        ):
            fixed_options.append(base_opt)
        else:
            fixed_options.append(postprocess_text(new_opt))
    result["options"] = fixed_options
    return result


def process_file(path: Path, model: str, host: str, cc: OpenCC) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    candidates = 0

    for item in data:
        if not should_process(item, cc):
            continue
        candidates += 1
        original = {
            "question": item["question"],
            "options": item["options"],
        }
        converted = ollama_chat(model, original, host)
        validated = validate_result(original, converted, cc)
        if validated["question"] != item["question"] or validated["options"] != item["options"]:
            item["question"] = validated["question"]
            item["options"] = validated["options"]
            changed += 1

    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return candidates, changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--questions-dir", default="questions")
    parser.add_argument("--glob", default="*.json")
    args = parser.parse_args()

    cc = OpenCC("s2t")
    qdir = Path(args.questions_dir)
    total_candidates = 0
    total_changed = 0

    for path in sorted(qdir.glob(args.glob)):
        candidates, changed = process_file(path, args.model, args.host, cc)
        if candidates:
            print(f"{path.name}: candidates={candidates}, changed={changed}")
        total_candidates += candidates
        total_changed += changed

    print(f"TOTAL candidates={total_candidates}, changed={total_changed}")


if __name__ == "__main__":
    main()
