"""
Amendment Audit Pipeline v2 — 3-stage funnel for 100% recall
Stage 0: Consolidate multi-version amendments into latest-per-article
Stage 1: Deterministic multi-signal matching (no top-N limit)
Stage 2: Gemma4 12B high-recall LLM filter (dual inference OR consensus)
Output : JSON for Stage 3 Claude final review
"""

import json
import os
import re
import sys
import math
import time
import requests
import threading
import concurrent.futures
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
TRAFFIC_AMENDMENTS = os.path.join(ROOT, "data", "traffic_law_amendments.json")
SAFETY_AMENDMENTS  = os.path.join(ROOT, "data", "safety_law_amendments.json")
MERGED_QUESTIONS   = os.path.join(ROOT, "scratch", "merged_traffic_law_questions.json")
OVERRIDES_FILE     = os.path.join(ROOT, "data", "overrides.json")
CACHE_FILE         = os.path.join(ROOT, "scratch", "audit_v2_cache.json")
STAGE1_CACHE_FILE  = os.path.join(ROOT, "scratch", "audit_v2_stage1_cache.json")
CLAUDE_REVIEW_FILE = os.path.join(ROOT, "scratch", "claude_review_input.json")
AUDIT_LOG_FILE     = os.path.join(ROOT, "scratch", "audit_v2_log.txt")

# ── LLM config ─────────────────────────────────────────────────────────────
LLM_URL   = "http://127.0.0.1:1234/v1/chat/completions"
LLM_MODEL = "gemma-4-12b-it"  # Adjust to your actual model name in LM Studio
LLM_WORKERS = 1  # 12B Q8 on single GPU, keep at 1 for stable VRAM

# ── Load data ──────────────────────────────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

traffic_raw = load_json(TRAFFIC_AMENDMENTS)
safety_raw  = load_json(SAFETY_AMENDMENTS)
questions   = load_json(MERGED_QUESTIONS)

for a in traffic_raw:
    a["law_name"] = "道路交通管理處罰條例"
for a in safety_raw:
    a["law_name"] = "道路交通安全規則"

all_amendments_raw = traffic_raw + safety_raw

print(f"Loaded {len(traffic_raw)} traffic + {len(safety_raw)} safety amendments = {len(all_amendments_raw)} total")
print(f"Loaded {len(questions)} questions")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 0: Consolidate amendments — one entry per (law, article), latest text
# ══════════════════════════════════════════════════════════════════════════════

def consolidate_amendments(raw_amendments):
    """Merge multiple versions of the same article into one record."""
    grouped = defaultdict(list)
    for a in raw_amendments:
        key = (a["law_name"], a["article_no"])
        grouped[key].append(a)

    consolidated = []
    for (law, art), versions in grouped.items():
        versions.sort(key=lambda x: x["date_roc"])
        latest = versions[-1]
        earliest = versions[0]

        all_reasons = []
        all_dates = []
        for v in versions:
            all_dates.append(v["date_roc"])
            reason = v["reason"].strip()
            if reason and reason not in ("修正通過。", "照協商條文通過。", "照協商條文通過。,"):
                all_reasons.append(f"[{v['date_roc']}修正] {reason}")

        # If no meaningful reasons found, still include the latest
        if not all_reasons and latest["reason"].strip():
            all_reasons.append(latest["reason"].strip())

        consolidated.append({
            "law_name": law,
            "article_no": art,
            "latest_date": latest["date_roc"],
            "earliest_date": earliest["date_roc"],
            "earliest_year": int(earliest["date_roc"].split('/')[0]),
            "latest_year": int(latest["date_roc"].split('/')[0]),
            "text": latest["text"],  # Always use latest version
            "reason": "\n".join(all_reasons) if all_reasons else latest["reason"],
            "amendment_count": len(versions),
            "amendment_dates": all_dates,
        })

    return consolidated

consolidated = consolidate_amendments(all_amendments_raw)
print(f"\nStage 0: Consolidated {len(all_amendments_raw)} raw → {len(consolidated)} unique (law, article) entries")

multi = [c for c in consolidated if c["amendment_count"] > 1]
if multi:
    print(f"  Articles with multiple versions: {len(multi)}")
    for c in multi:
        law_short = "處罰" if "處罰" in c["law_name"] else "安全"
        print(f"    [{law_short}] 第{c['article_no']}條: {c['amendment_count']}次 ({', '.join(c['amendment_dates'])})")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: Deterministic multi-signal matching
# ══════════════════════════════════════════════════════════════════════════════

# ── Deprecated term dictionary (old term → new term) ───────────────────────
DEPRECATED_TERMS = {
    "電動自行車": "微型電動二輪車",
    "地方法院行政訴訟庭": "高等行政法院地方行政訴訟庭",
    "地方法院簡易庭": "高等行政法院地方行政訴訟庭",
}

# ── Known penalty amount changes: (old_amount, article, law) ───────────────
PENALTY_CHANGES = [
    # (old text pattern, article_no, law_name_contains)
    ("3,600元", "45", "處罰"),      # 不避讓緊急車輛 3600→3600~18000
    ("1,000元", "31-1", "處罰"),    # 手持電話 1000→1200
    ("1,200元", "56-1", "處罰"),    # 開車門肇事 1200~3600→2400~4800
    ("3,600元", "56-1", "處罰"),    # 同上
    ("180公分", "41", "安全"),       # 大客車高度 180→185
    ("50公斤", "39-2", "安全"),      # 輕型機車 50→70
    ("60公里", "43", "處罰"),        # 嚴重超速 60→40
]

# ── Stage 1 cache check ────────────────────────────────────────────────────
def get_bank_year(bank_name):
    match = re.search(r"(\d+)", bank_name)
    return int(match.group(1)) if match else 110

def normalize_stem(text):
    return re.sub(r"[^\w一-龥]", "", text).strip().lower()

# ── Group questions for repeat detection ────────────────────────────────────
grouped_q = defaultdict(list)
for q in questions:
    norm = normalize_stem(q["question"])
    grouped_q[norm].append(q)

repeats_map = {}
for norm, qlist in grouped_q.items():
    if len(norm) < 10 or norm in ("下列敘述何者正確", "下列何者正確", "下列何者為非", "下列敘述何者錯誤"):
        continue
    bank_names = sorted(set(q["_bank_name"] for q in qlist))
    if len(bank_names) > 1:
        for q in qlist:
            repeats_map[(q["_bank_file"], str(q["id"]))] = bank_names

print("\n── Stage 1: Embedding + Reranker + Deterministic matching ──")

if os.path.exists(STAGE1_CACHE_FILE):
    print(f"  Loading Stage 1 cache from {STAGE1_CACHE_FILE}")
    stage1_data = load_json(STAGE1_CACHE_FILE)
    candidates = stage1_data["candidates"]
    auto_safe = stage1_data["auto_safe"]
    reranker_pairs_total = stage1_data.get("reranker_pairs_total", 0)
    print(f"  Loaded {len(candidates)} candidates from cache (auto_safe={auto_safe})")
else:
    # ── Embedding + Reranker infrastructure ──────────────────────────────────
    import numpy as np
    from sentence_transformers import SentenceTransformer, CrossEncoder

    EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
    RERANK_MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"
    EMBED_TOP_K = 20
    RERANK_THRESHOLD = 0.3

    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {DEVICE}")

    print("  Loading embedding model...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME, trust_remote_code=True, device=DEVICE)
    print(f"  Loading reranker model...")
    reranker = CrossEncoder(RERANK_MODEL_NAME, trust_remote_code=True, device=DEVICE)

    amend_texts = [f"{c['law_name']} 第{c['article_no']}條 {c['text']}" for c in consolidated]
    amend_index = consolidated

    print(f"  Encoding {len(amend_texts)} amendment documents...")
    amend_embeddings = embed_model.encode(amend_texts, normalize_embeddings=True, show_progress_bar=False)

    q_texts = []
    q_meta = []
    for q in questions:
        q_year = get_bank_year(q["_bank_name"])
        q_full_text = f"{q['question']} {' '.join(q['options'])}"
        q_texts.append(q_full_text)
        q_meta.append({"q": q, "year": q_year, "full_text": q_full_text})

    print(f"  Encoding {len(q_texts)} question texts...")
    q_embeddings = embed_model.encode(q_texts, normalize_embeddings=True, show_progress_bar=True)

    amend_latest_years = np.array([c["latest_year"] for c in amend_index])

    candidates = []
    auto_safe = 0
    reranker_pairs_total = 0

    for qi, qm in enumerate(q_meta):
        q = qm["q"]
        q_year = qm["year"]
        q_full_text = qm["full_text"]

        newer_mask = amend_latest_years > q_year
        if not newer_mask.any():
            auto_safe += 1
            continue

        newer_indices = np.where(newer_mask)[0]

        sims = q_embeddings[qi] @ amend_embeddings[newer_indices].T
        top_k = min(EMBED_TOP_K, len(newer_indices))
        top_k_local = np.argsort(sims)[-top_k:][::-1]
        top_k_global = newer_indices[top_k_local]

        strong_amendments = {}
        for gi in newer_indices:
            c = amend_index[gi]
            signals = []
            art_mentions = re.findall(
                r'(?:道路交通管理處罰條例|處罰條例|道路交通安全規則|安全規則)?\s*第\s*(\d+(?:[\-之]\d+)?)\s*條',
                q_full_text
            )
            art_normalized = [a.replace('之', '-') for a in art_mentions]
            if c["article_no"] in art_normalized:
                signals.append("article_mention")
            for old_term, new_term in DEPRECATED_TERMS.items():
                if old_term in q_full_text and new_term in c["text"]:
                    signals.append(f"deprecated_term={old_term}")
            for old_amt, art, law_key in PENALTY_CHANGES:
                if old_amt in q_full_text and c["article_no"] == art and law_key in c["law_name"]:
                    signals.append(f"penalty={old_amt}→art{art}")
            if signals:
                strong_amendments[gi] = signals

        all_candidate_indices = set(top_k_global.tolist()) | set(strong_amendments.keys())

        rerank_pairs = []
        rerank_indices = []
        for gi in all_candidate_indices:
            c = amend_index[gi]
            amend_text = f"{c['law_name']} 第{c['article_no']}條 {c['text'][:500]}"
            rerank_pairs.append((q_full_text, amend_text))
            rerank_indices.append(gi)

        reranker_pairs_total += len(rerank_pairs)

        if not rerank_pairs:
            auto_safe += 1
            continue

        rerank_scores = reranker.predict(rerank_pairs, show_progress_bar=False)

        matched_amendments = []
        for ri, gi in enumerate(rerank_indices):
            c = amend_index[gi]
            score = 1.0 / (1.0 + math.exp(-float(rerank_scores[ri])))
            embed_sim = float(sims[np.where(newer_indices == gi)[0][0]]) if gi in set(top_k_global) else 0.0
            signals = list(strong_amendments.get(gi, []))
            if gi in set(top_k_global):
                signals.append(f"embed={embed_sim:.3f}")
            signals.append(f"rerank={score:.3f}")
            has_strong = gi in strong_amendments
            if score >= RERANK_THRESHOLD or has_strong:
                matched_amendments.append({
                    "law_name": c["law_name"],
                    "article_no": c["article_no"],
                    "latest_date": c["latest_date"],
                    "earliest_year": c["earliest_year"],
                    "text": c["text"],
                    "reason": c["reason"],
                    "amendment_count": c["amendment_count"],
                    "signals": signals,
                    "similarity": score,
                })

        if matched_amendments:
            matched_amendments.sort(key=lambda x: x["similarity"], reverse=True)
            candidates.append({
                "bank_file": q["_bank_file"],
                "bank_name": q["_bank_name"],
                "id": str(q["id"]),
                "question": q["question"],
                "options": q["options"],
                "correct_idx": q["answer"],
                "q_year": q_year,
                "matched_amendments": matched_amendments,
            })
        else:
            auto_safe += 1

        if (qi + 1) % 100 == 0:
            print(f"  Processed {qi+1}/{len(q_meta)} questions, {len(candidates)} candidates so far...")

    save_json(STAGE1_CACHE_FILE, {
        "candidates": candidates,
        "auto_safe": auto_safe,
        "reranker_pairs_total": reranker_pairs_total,
    })
    print(f"  Stage 1 cache saved → {STAGE1_CACHE_FILE}")

    # Free GPU VRAM before Stage 2 LLM calls
    del embed_model, reranker, amend_embeddings, q_embeddings
    import gc; gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("  GPU memory freed")

print(f"\nStage 1 complete:")
print(f"  Candidates for LLM review: {len(candidates)}")
print(f"  Auto-safe (no newer or below threshold): {auto_safe}")
print(f"  Total reranker pairs scored: {reranker_pairs_total}")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2: Gemma4 12B high-recall LLM filter
# ══════════════════════════════════════════════════════════════════════════════

# ── Cache ──────────────────────────────────────────────────────────────────
cache_lock = threading.Lock()
llm_cache = {}
if os.path.exists(CACHE_FILE):
    try:
        llm_cache = load_json(CACHE_FILE)
        bad = [k for k, v in llm_cache.items()
               if any(err in v.get("reason", "") for err in ("API Error", "Failed to parse"))]
        for k in bad:
            del llm_cache[k]
        print(f"\nLoaded cache: {len(llm_cache)} entries, cleared {len(bad)} errors")
    except Exception as e:
        print(f"Cache load failed: {e}")

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(llm_cache, f, ensure_ascii=False, indent=2)

# ── LLM query ─────────────────────────────────────────────────────────────
def extract_json_content(text):
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\{.*?\})", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()

def clean_json_str(s):
    s = re.sub(r"'\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*'\s*:", r'"\1":', s)
    s = re.sub(r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_-]*)\s*:", r'\1"\2":', s)
    s = re.sub(r":\s*'(.*?)'\s*([,}])", r': "\1"\2', s)
    s = re.sub(r",\s*}", "}", s)
    return s

def query_llm(prompt, temperature=0.0):
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 500,
    }
    for attempt in range(3):
        try:
            r = requests.post(LLM_URL, json=payload, timeout=180)
            if r.status_code == 200:
                raw = r.json()["choices"][0]["message"]["content"]
                json_str = extract_json_content(raw)
                json_str = clean_json_str(json_str)
                try:
                    return json.loads(json_str)
                except Exception:
                    affected = bool(re.search(r'"is_affected"\s*:\s*true', json_str, re.I))
                    reason_m = re.search(r'"reason"\s*:\s*"(.*?)"', json_str, re.DOTALL)
                    conf_m = re.search(r'"confidence"\s*:\s*(\d+)', json_str)
                    art_m = re.search(r'"affected_article"\s*:\s*"(.*?)"', json_str)
                    return {
                        "is_affected": affected,
                        "affected_article": art_m.group(1) if art_m else None,
                        "confidence": int(conf_m.group(1)) if conf_m else (70 if affected else 30),
                        "reason": reason_m.group(1).strip() if reason_m else "Parse fallback",
                    }
            else:
                print(f"  API error {r.status_code} (attempt {attempt+1}/3): {r.text[:300]}")
                if attempt < 2:
                    time.sleep(6)
        except Exception as e:
            print(f"  Request error: {e} (attempt {attempt+1}/3)")
            if attempt < 2:
                time.sleep(3)
    return {"is_affected": False, "affected_article": None, "confidence": 0, "reason": "API Error"}

def build_prompt(q_year, q_text, options_text, correct_letter, correct_text, amendments):
    # Always include strong-signal amendments, fill remaining with top reranker scores
    strong = [a for a in amendments if any(
        s.startswith(("article_mention", "deprecated_term", "penalty")) for s in a["signals"]
    )]
    others = [a for a in amendments if a not in strong]
    selected = (strong + others)[:8]  # cap total at 8, strong-signal first

    amend_block = ""
    for i, a in enumerate(selected):
        signals_str = ", ".join(a["signals"])
        amend_block += f"\n修正案{i+1}：{a['law_name']} 第 {a['article_no']} 條（最新修正：民國 {a['latest_date']}，共修正 {a['amendment_count']} 次）\n"
        amend_block += f"匹配信號：{signals_str}\n"
        amend_block += f"最新條文全文：{a['text'][:300]}\n"
        if a["reason"].strip():
            amend_block += f"修正理由：{a['reason'][:150]}\n"

    return f"""你是法律修正案審查員。判斷此考題是否受以下修正案影響。

【重要原則】
- 寧可誤判 (false positive) 也不可遺漏 (false negative)
- 只有當你 100% 確定修法與題目「完全無關」時，才判定 is_affected = false
- 若修法改變了正確答案、使任何選項的描述不再正確、改變了處罰金額/期限/條件、改變了法律名詞定義、或廢除題目涉及的規定，判定 is_affected = true
- 注意：題目的「正確答案」是出題當年的正確答案，修法後可能已經不正確

【考題資訊】
出題年份：民國 {q_year} 年
題目：{q_text}
選項：
{options_text}
當年正確答案：{correct_letter} ({correct_text})

【出題年份之後的相關法條修正案】
{amend_block}

請回覆 JSON（不要加其他文字）：
{{"is_affected": true/false, "affected_article": "第X條" 或 "安全規則第X條" 或 null, "confidence": 0到100的整數, "reason": "繁體中文簡短理由"}}"""

def has_strong_signal(c):
    """Check if candidate has any strong (non-tfidf-only) signal."""
    for a in c["matched_amendments"]:
        for s in a["signals"]:
            if s.startswith(("article_mention", "deprecated_term", "penalty")):
                return True
    return False

def max_similarity(c):
    return max((a["similarity"] for a in c["matched_amendments"]), default=0)

def format_question_for_llm(c):
    options_text = "\n".join(f"({chr(65+i)}) {opt}" for i, opt in enumerate(c["options"]))
    if isinstance(c["correct_idx"], list):
        correct_letter = ",".join(chr(65 + ci) for ci in c["correct_idx"])
        correct_text = ",".join(c["options"][ci] for ci in c["correct_idx"])
    else:
        correct_letter = chr(65 + c["correct_idx"])
        correct_text = c["options"][c["correct_idx"]]
    return options_text, correct_letter, correct_text

def process_candidate_pass1(idx, total, c):
    """First pass: temperature=0 for all candidates."""
    cache_key = f"v4::{c['bank_file']}::{c['id']}"

    with cache_lock:
        if cache_key in llm_cache:
            cached = llm_cache[cache_key]
            print(f"[{idx+1}/{total}] Cache hit: {c['bank_name']} Q{c['id']}")
            return c, cached

    print(f"[{idx+1}/{total}] Pass 1: {c['bank_name']} Q{c['id']} ({len(c['matched_amendments'])} amends)...")

    options_text, correct_letter, correct_text = format_question_for_llm(c)
    prompt = build_prompt(
        c["q_year"], c["question"], options_text,
        correct_letter, correct_text, c["matched_amendments"]
    )

    r1 = query_llm(prompt, temperature=0.0)

    result = {
        "is_affected": r1.get("is_affected", False),
        "affected_article": r1.get("affected_article"),
        "confidence": r1.get("confidence", 0),
        "reason": r1.get("reason", ""),
        "dual_disagreed": False,
        "run1_affected": r1.get("is_affected", False),
        "run1_confidence": r1.get("confidence", 0),
        "needs_pass2": False,
    }

    status = "⚠️ AFFECTED" if result["is_affected"] else "✅ SAFE"
    print(f"  → {status} (conf={result['confidence']}): {result['reason'][:80]}")

    with cache_lock:
        llm_cache[cache_key] = result
        save_cache()

    return c, result

def process_candidate_pass2(idx, total, c, pass1_result):
    """Second pass: temperature=0.3 for borderline cases. OR with pass1."""
    cache_key = f"v4::{c['bank_file']}::{c['id']}"

    # If pass1 already said affected, no need for pass2
    if pass1_result["is_affected"]:
        return c, pass1_result

    # If cache already has a pass2 result (dual_disagreed field or run2 data), use it
    with cache_lock:
        if cache_key in llm_cache and llm_cache[cache_key].get("run2_confidence") is not None:
            cached = llm_cache[cache_key]
            if cached.get("run2_affected") is not None:
                print(f"[{idx+1}/{total}] Cache hit (pass2): {c['bank_name']} Q{c['id']}")
                return c, cached

    print(f"[{idx+1}/{total}] Pass 2: {c['bank_name']} Q{c['id']}...")

    options_text, correct_letter, correct_text = format_question_for_llm(c)
    prompt = build_prompt(
        c["q_year"], c["question"], options_text,
        correct_letter, correct_text, c["matched_amendments"]
    )

    r2 = query_llm(prompt, temperature=0.3)

    # OR consensus
    is_affected = pass1_result["is_affected"] or r2.get("is_affected", False)
    confidence = max(pass1_result["confidence"], r2.get("confidence", 0))
    disagreed = pass1_result["is_affected"] != r2.get("is_affected", False)

    if is_affected and r2.get("is_affected"):
        reason = r2.get("reason", pass1_result["reason"])
        affected_article = r2.get("affected_article", pass1_result["affected_article"])
    else:
        reason = pass1_result["reason"]
        affected_article = pass1_result["affected_article"]

    result = {
        "is_affected": is_affected,
        "affected_article": affected_article,
        "confidence": confidence,
        "reason": reason,
        "dual_disagreed": disagreed,
        "run1_affected": pass1_result["is_affected"],
        "run1_confidence": pass1_result["confidence"],
        "run2_affected": r2.get("is_affected", False),
        "run2_confidence": r2.get("confidence", 0),
    }

    if disagreed:
        print(f"  → DISAGREEMENT: pass1={pass1_result['is_affected']}, pass2={r2.get('is_affected')}")

    with cache_lock:
        llm_cache[cache_key] = result
        save_cache()

    return c, result

# ── Run Stage 2 ────────────────────────────────────────────────────────────
print(f"\n── Stage 2: Gemma4 12B two-pass LLM filter ──")
print(f"Pass 1: Processing all {len(candidates)} candidates (temp=0)...")

pass1_results = []
for i, c in enumerate(candidates):
    c, decision = process_candidate_pass1(i, len(candidates), c)
    pass1_results.append((c, decision))
    if decision.get("reason") != "API Error":
        time.sleep(2)  # let LM Studio reset between calls

# Determine which need pass 2: not-affected in pass1 + (strong signal OR high similarity)
needs_pass2 = []
final_after_pass1 = []
for c, d in pass1_results:
    if d["is_affected"]:
        final_after_pass1.append((c, d))
    elif has_strong_signal(c) or max_similarity(c) > 0.5 or d["confidence"] >= 30:
        needs_pass2.append((c, d))
    else:
        final_after_pass1.append((c, d))

pass1_affected = sum(1 for _, d in pass1_results if d["is_affected"])
print(f"\nPass 1 results: {pass1_affected} affected, {len(needs_pass2)} borderline → pass 2")

if needs_pass2:
    print(f"Pass 2: Re-checking {len(needs_pass2)} borderline cases (temp=0.3)...")
    for i, (c, d) in enumerate(needs_pass2):
        c, decision = process_candidate_pass2(i, len(needs_pass2), c, d)
        final_after_pass1.append((c, decision))
        if decision.get("reason") != "API Error":
            time.sleep(0.5)

stage2_results = final_after_pass1
# Sort results by bank/id for consistent output
stage2_results.sort(key=lambda x: (x[0]["bank_name"], int(x[0]["id"])))

# ══════════════════════════════════════════════════════════════════════════════
# OUTPUT: Prepare Claude review input + overrides
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n── Preparing output ──")

# Classify results
affected = []
safe_for_sampling = []

for c, decision in stage2_results:
    entry = {
        "bank_file": c["bank_file"],
        "bank_name": c["bank_name"],
        "question_id": c["id"],
        "question": c["question"],
        "options": c["options"],
        "correct_idx": c["correct_idx"],
        "q_year": c["q_year"],
        "llm_decision": decision,
        "matched_amendments": [
            {
                "law_name": a["law_name"],
                "article_no": a["article_no"],
                "latest_date": a["latest_date"],
                "signals": a["signals"],
                "text": a["text"],
                "reason": a["reason"][:300],
            }
            for a in c["matched_amendments"]
        ],
    }

    if decision["is_affected"] or decision["confidence"] >= 20:
        affected.append(entry)
    else:
        safe_for_sampling.append(entry)

# Sample 15% of safe questions for QA
import random
random.seed(42)
sample_size = max(1, int(len(safe_for_sampling) * 0.15))
qa_sample = random.sample(safe_for_sampling, min(sample_size, len(safe_for_sampling)))

claude_review = {
    "metadata": {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": len(questions),
        "candidates_checked": len(candidates),
        "auto_safe": auto_safe,
        "llm_flagged": len(affected),
        "qa_sample_size": len(qa_sample),
    },
    "batch_a_review": affected,
    "batch_b_qa_sample": qa_sample,
}

save_json(CLAUDE_REVIEW_FILE, claude_review)
print(f"Claude review input: {CLAUDE_REVIEW_FILE}")
print(f"  Batch A (flagged for review): {len(affected)}")
print(f"  Batch B (QA sample): {len(qa_sample)}")

# ── Write audit log ────────────────────────────────────────────────────────
with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("AMENDMENT AUDIT v2 — 3-STAGE PIPELINE LOG\n")
    f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"Total questions: {len(questions)}\n")
    f.write(f"Consolidated amendments: {len(consolidated)}\n")
    f.write(f"Candidates checked by LLM: {len(candidates)}\n")
    f.write(f"Auto-safe: {auto_safe}\n")
    f.write(f"LLM flagged (affected or conf≥20): {len(affected)}\n")
    f.write(f"QA sample: {len(qa_sample)}\n")
    f.write("=" * 80 + "\n\n")

    f.write("── FLAGGED QUESTIONS ──\n\n")
    for entry in affected:
        d = entry["llm_decision"]
        f.write(f"[{entry['bank_name']} Q{entry['question_id']}] conf={d['confidence']}")
        if d.get("dual_disagreed"):
            f.write(" [DUAL DISAGREED]")
        f.write(f"\n")
        f.write(f"  Q: {entry['question']}\n")
        opts = entry['options']
        for i, o in enumerate(opts):
            marker = "→" if i == entry['correct_idx'] or (isinstance(entry['correct_idx'], list) and i in entry['correct_idx']) else " "
            f.write(f"  {marker} ({chr(65+i)}) {o}\n")
        f.write(f"  Article: {d.get('affected_article', 'N/A')}\n")
        f.write(f"  Reason: {d['reason']}\n")
        amend_signals = [f"{a['law_name']}第{a['article_no']}條({','.join(a['signals'])})" for a in entry['matched_amendments'][:3]]
        f.write(f"  Signals: {'; '.join(amend_signals)}\n")
        f.write("-" * 80 + "\n\n")

    f.write("\n── QA SAMPLE (safe questions for spot-check) ──\n\n")
    for entry in qa_sample:
        d = entry["llm_decision"]
        f.write(f"[{entry['bank_name']} Q{entry['question_id']}] conf={d['confidence']}\n")
        f.write(f"  Q: {entry['question']}\n")
        f.write(f"  Reason: {d['reason']}\n")
        f.write("-" * 80 + "\n\n")

print(f"Audit log: {AUDIT_LOG_FILE}")

# ── Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"STAGE 2 COMPLETE — Summary")
print(f"{'='*60}")
print(f"Total questions:          {len(questions)}")
print(f"Auto-safe (no match):     {auto_safe}")
print(f"Sent to LLM:             {len(candidates)}")
print(f"LLM flagged (Batch A):   {len(affected)}")
print(f"QA sample (Batch B):     {len(qa_sample)}")
print(f"\nNext step: Run Stage 3 (Claude review) on {CLAUDE_REVIEW_FILE}")
print(f"  Batch A: {len(affected)} questions need full review")
print(f"  Batch B: {len(qa_sample)} questions for spot-check")

# Print disagreements for special attention
disagreed_items = [(c, d) for c, d in stage2_results if d.get("dual_disagreed")]
if disagreed_items:
    print(f"\n⚠️  Dual-inference disagreements: {len(disagreed_items)}")
    for c, d in disagreed_items:
        print(f"  {c['bank_name']} Q{c['id']}: run1={d['run1_affected']}(conf={d['run1_confidence']}), run2={d.get('run2_affected','N/A')}(conf={d.get('run2_confidence','N/A')})")
