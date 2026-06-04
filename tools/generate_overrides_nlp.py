import json
import os
import re
import sys
import math
import time
import requests
import threading
import concurrent.futures

# Ensure UTF-8 output on Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
traffic_amendments_file = os.path.join(root_dir, "data", "traffic_law_amendments.json")
safety_amendments_file = os.path.join(root_dir, "data", "safety_law_amendments.json")
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")
overrides_file = os.path.join(root_dir, "data", "overrides.json")
cache_file = os.path.join(root_dir, "scratch", "llm_audit_cache_v2.json")
audit_log_file = os.path.join(root_dir, "scratch", "nlp_mapping_audit_v2.txt")

LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
# Using Gemma since it returns direct answers without verbose reasoning token limits
LLM_MODEL = "gemma-4-26b-a4b-it-apex"

if not os.path.exists(traffic_amendments_file) or not os.path.exists(safety_amendments_file) or not os.path.exists(merged_file):
    print("Required data files not found!")
    sys.exit(1)

with open(traffic_amendments_file, "r", encoding="utf-8") as f:
    traffic_amendments = json.load(f)
for a in traffic_amendments:
    a["law_name"] = "道路交通管理處罰條例"

with open(safety_amendments_file, "r", encoding="utf-8") as f:
    safety_amendments = json.load(f)
for a in safety_amendments:
    a["law_name"] = "道路交通安全規則"

amendments = traffic_amendments + safety_amendments

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Load LLM cache
llm_cache = {}
if os.path.exists(cache_file):
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            llm_cache = json.load(f)
        # Clear any failed/error cache entries so they can be re-run
        keys_to_delete = [
            k for k, v in llm_cache.items() 
            if "API Error" in v.get("reason", "") or "Failed to parse" in v.get("reason", "") or "Gemma non-standard" in v.get("reason", "")
        ]
        for k in keys_to_delete:
            del llm_cache[k]
        print(f"Loaded cache, cleared {len(keys_to_delete)} error entries.")
    except Exception as e:
        print("Warning: Failed to load LLM cache, starting fresh.", e)

# 1. Chinese text tokenizer (character unigrams + bigrams)
def get_ngrams(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    tokens = []
    tokens.extend(list(text))
    for i in range(len(text) - 1):
        tokens.append(text[i:i+2])
    return tokens

# 2. Build TF-IDF for all amendments
corpus = []
for idx, a in enumerate(amendments):
    doc_text = f"{a['law_name']} {a['article_raw']} {a['text']} {a['reason']}"
    corpus.append({
        "index": idx,
        "article_no": a["article_no"],
        "law_name": a["law_name"],
        "date_roc": a["date_roc"],
        "text": doc_text,
        "ngrams": get_ngrams(doc_text),
        "raw_text": a["text"],
        "raw_reason": a["reason"]
    })

df = {}
for doc in corpus:
    unique_tokens = set(doc["ngrams"])
    for token in unique_tokens:
        df[token] = df.get(token, 0) + 1

N = len(corpus)
idf = {}
for token, count in df.items():
    idf[token] = math.log((N + 1) / (count + 0.5)) + 1

doc_vectors = []
for doc in corpus:
    tf = {}
    for token in doc["ngrams"]:
        tf[token] = tf.get(token, 0) + 1
    
    vector = {}
    length_sq = 0.0
    for token, val in tf.items():
        w = val * idf.get(token, 0.0)
        vector[token] = w
        length_sq += w * w
    length = math.sqrt(length_sq)
    
    if length > 0:
        for token in vector:
            vector[token] /= length
            
    doc_vectors.append({
        "article_no": doc["article_no"],
        "law_name": doc["law_name"],
        "date_roc": doc["date_roc"],
        "vector": vector,
        "raw_text": doc["raw_text"],
        "raw_reason": doc["raw_reason"]
    })

# 3. Group questions to find duplicates (repeats)
def normalize_stem(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    return text.strip().lower()

grouped = {}
for q in questions:
    norm = normalize_stem(q["question"])
    grouped.setdefault(norm, []).append(q)

repeats_map = {}
for norm, list_q in grouped.items():
    if len(norm) < 10 or norm in ["下列敘述何者正確", "下列何者正確", "下列何者為非", "下列敘述何者錯誤"]:
        continue
    bank_names = sorted(list(set(q["_bank_name"] for q in list_q)))
    if len(bank_names) > 1:
        for q in list_q:
            key = (q["_bank_file"], str(q["id"]))
            repeats_map[key] = bank_names

# 4. Warnings dictionary for major amended articles
ARTICLE_WARNINGS = {
    # 處罰條例
    "7-1": "⚠️ 本題涉及民眾檢舉項目（條例第 7 條之 1）。該條文於民國 110 年及 113 年進行了兩次大幅限縮修正，已刪除人行道與黃線臨停等部分檢舉項目，請以最新修正之現行條文為準。",
    "7-2": "⚠️ 本題涉及逕行舉發（條例第 7 條之 2），該條文於 110 年 12 月配合民眾檢舉新制進行了條文調整與對應，請注意最新規定。",
    "12": "⚠️ 本題涉及牌照違規處罰（條例第 12 條），該條文於 112 年 4 月修正加重了使用吊銷/註銷牌照行駛之處罰，並增列扣繳牌照或當場沒入車輛之規定。",
    "29": "⚠️ 本題涉及車輛裝載規定（條例第 29 條）。該條文於 110 年 5 月修正，處罰額度調整為新臺幣 3,000 元以上 18,000 元以下罰鍰，並記違規紀錄與記點。",
    "31": "⚠️ 本題涉及安全帶與安全椅規定（條例第 31 條）。該條文於 110 年 11 月及 112 年 4 月修正，明定大型車乘載四歲以上乘客未繫安全帶之處罰，以及幼童安置與留置兒童處罰。",
    "33": "⚠️ 本題涉及高快速公路違規（條例第 33 條），該條文於 112 年 4 月修正提高未依規定車道行駛、違規超車或未保持安全距離等之處罰額度，請以最新規定為準。",
    "35": "⚠️ 本題涉及酒駕相關規定（條例第 35 條）。酒駕新制於 111 年及 112 年多次加重處罰，包含提高同車乘客罰鍰至 6,000 ~ 15,000 元、累犯累計年限延長至 10 年、公布姓名照片、吊扣牌照二年等。",
    "35-1": "⚠️ 本題涉及酒精鎖規定（條例第 35 條之 1），該條文於 111 年 1 月修正，大幅加重了未依規定駕駛配備車輛點火自動鎖定裝置汽車之處罰（提高至 6 萬至 12 萬元）。",
    "43": "⚠️ 本題涉及危險駕駛與嚴重超速處罰（條例第 43 條）。自民國 112 年 6 月 30 日起，『嚴重超速』定義由原本的『超過最高時速 60 公里』調降為『超過最高時速 40 公里』，並加重罰鍰及吊扣牌照期限，請注意新法規定。",
    "56": "⚠️ 本題涉及停車處罰（條例第 56 條）。該條文於 114 年 10 月修正，將併排停車第二項罰鍰由定額 2,400 元修正為 1,800 元以上 3,000 元以下，並調整交岔路口與通學區停車規定。",
    "63": "⚠️ 本題涉及違規記點與吊扣駕照制度（條例第 63 條）。記點新制於民國 112 年 6 月 30 日起全面改版，由原本的『6 個月內達 6 點吊扣 1 個月』修正為『1 年內記滿 12 點者，吊扣駕駛執照 2 個月；2 年內經吊扣 2 次再犯者吊銷』。",
    "69": "⚠️ 本題涉及慢車規定更名（條例第 69 條）。自民國 111 年 11 月 30 日起，『電動自行車』正式更名為『微型電動二輪車』，且規定須型式審驗合格、登記領牌、投保強制險並年滿 14 歲始得行駛道路。",
    "69-1": "⚠️ 本題涉及微型電動二輪車新制（條例第 69 條之 1），微型電動二輪車自民國 111 年 11 月 30 日起已強制要求登記、領牌並投保強制保險始得行駛道路，請注意最新規定。",
    "90": "⚠️ 本題涉及舉發期限（條例第 90 條）。舉發期限已於民國 109 年 12 月修正，從行為終了之日起『逾三個月』縮短為『逾二個月』不得舉發（部分涉及肇事逃逸等情形除外）。",
    
    # 安全規則
    "道路交通安全規則::39": "⚠️ 本題涉及汽車申請牌照檢驗之項目及基準（安全規則第 39 條）。該條文於近年多次修正，針對輪胎胎面磨耗、車輛配備（如行車紀錄器、反光識別材料）等檢驗標準進行了調整，請以最新規定為準。",
    "道路交通安全規則::39-1": "⚠️ 本題涉及汽車定期檢驗之項目及基準（安全規則第 39 條之 1）。該條文近年多次修正，針對大客車車重限制、行車視野輔助系統、輪胎規格等檢驗項目有最新規定，請以最新規定為準。",
    "道路交通安全規則::64": "⚠️ 本題涉及駕駛人體格檢查與體能測驗標準（安全規則第 64 條），特別是涉及身心障礙者或特殊疾病（如癲癇症）報考駕照之放寬及定期換照規定，請注意最新修正之規定。",
    "道路交通安全規則::64-1": "⚠️ 本題涉及高齡（60歲以上）職業駕駛人換發駕駛執照之體檢及加註規定（安全規則第 64 條之 1），近年配合駕駛人年齡限制與回訓制度有相關微調，請以最新規定為準。",
    "道路交通安全規則::88": "⚠️ 本題涉及機車裝載行駛規定（安全規則第 88 條），包含機車附載人員、物品寬度、高度限制與佩戴安全帽等規定，請以最新現行法規為準。",
    "道路交通安全規則::102": "⚠️ 本題涉及汽車行駛至交岔路口之行進與轉彎規定（安全規則第 102 條），包含支線道讓幹線道、左轉彎車讓直行車、圓環行車路權等核心安全規定，請注意最新規定與路權判定原則。"
}

# Manual verification exclusions
EXCLUSIONS = {}

MANUAL_CORRECTIONS = {
    "questions/交通部111-1-道路交通法規.json": {
        "11": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 31 條之 1 修正，機車駕駛人手持使用電話罰鍰已由 1,000 元提高至 1,200 元，原選項無正確答案。"
        }
    },
    "questions/交通部111-3-道路交通法規.json": {
        "16": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 31 條之 1 修正，機車駕駛人手持使用電話罰鍰已由 1,000 元提高至 1,200 元，原選項無正確答案。"
        }
    },
    "questions/交通部111-道路交通法規.json": {
        "9": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 56 條之 1 修正，開啟車門未留心因而肇事罰鍰已由 1,200~3,600 元調整為 2,400~4,800 元，原選項無正確答案。"
        }
    },
    "questions/交通部112-1-道路交通法規.json": {
        "17": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：行政訴訟法及行政法院組織法修正，原本由地方刑事庭管轄之簡易訴訟改由高等行政法院地方行政訴訟庭管轄，原選項無正確答案。"
        }
    },
    "questions/交通部113-1-道路交通法規.json": {
        "15": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：行政訴訟法及行政法院組織法修正，原本由地方刑事庭管轄之簡易訴訟改由高等行政法院地方行政訴訟庭管轄，原選項無正確答案。"
        }
    }
}

# Parse ROC year from bank name
def get_bank_year(bank_name):
    match = re.search(r"(\d+)", bank_name)
    if match:
        return int(match.group(1))
    return 110

def extract_json_content(text):
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def clean_json_keys(json_str):
    json_str = re.sub(r"'\s*([a-zA-Z0-9_-]+)\s*'\s*:", r'"\1":', json_str)
    json_str = re.sub(r"([{,]\s*)([a-zA-Z0-9_-]+)\s*:", r'\1"\2":', json_str)
    json_str = re.sub(r':\s*\'(.*?)\'\s*([,}])', r': "\1"\2', json_str)
    json_str = re.sub(r",\s*}", "}", json_str)
    return json_str

def query_local_llm_multi(q_year, q_text, options, correct_letter, correct_text, amendment_list):
    """Query LLM with multiple amendments at once. Each item in amendment_list is a dict
    with keys: law_name, article_no, amend_year, text, reason, similarity."""
    amendments_block = ""
    for i, a in enumerate(amendment_list):
        text_trunc = a["text"][:250] + ("..." if len(a["text"]) > 250 else "")
        reason_trunc = a["reason"][:100] + ("..." if len(a["reason"]) > 100 else "")
        amendments_block += f"\n修正案{i+1}：{a['law_name']} 第 {a['article_no']} 條（民國 {a['amend_year']} 年修正）\n"
        amendments_block += f"新條文：{text_trunc}\n"
        amendments_block += f"修正理由：{reason_trunc}\n"

    prompt = f"""分析此考題是否受以下任何修正案影響。
若任何一條修法改變了正確答案、使選項不再正確、廢除題目涉及的規定或詞彙，判定 is_affected = true。
若修法與題目無關，判定 is_affected = false。

【題目】
年份：民國 {q_year} 年
題目：{q_text}
選項：
{options}
正確答案：{correct_letter} ({correct_text})

【以下為該題出題年份之後的相關法條修正案】
{amendments_block}
請直接回覆 JSON：
{{"is_affected": true/false, "affected_article": "第X條" 或 "安全規則第X條" 或 null, "reason": "繁體中文簡短理由"}}
"""
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 400
    }
    for attempt in range(3):
        try:
            r = requests.post(LLM_URL, json=payload, timeout=120)
            if r.status_code == 200:
                res_data = r.json()
                raw_content = res_data["choices"][0]["message"]["content"]
                json_str = extract_json_content(raw_content)
                json_str = clean_json_keys(json_str)
                try:
                    return json.loads(json_str)
                except Exception:
                    is_affected = bool(re.search(r'"is_affected"\s*:\s*true', json_str, re.IGNORECASE))
                    reason_match = re.search(r'"reason"\s*:\s*"(.*?)"', json_str, re.DOTALL)
                    reason = reason_match.group(1).strip() if reason_match else "Gemma non-standard format."
                    art_match = re.search(r'"affected_article"\s*:\s*"(.*?)"', json_str)
                    affected_art = art_match.group(1) if art_match else None
                    return {"is_affected": is_affected, "affected_article": affected_art, "reason": reason}
            else:
                print(f" Error: API status {r.status_code} (attempt {attempt+1}/3)")
                if attempt < 2:
                    time.sleep(3)
        except Exception as e:
            print(f" Error: {e} (attempt {attempt+1}/3)")
            if attempt < 2:
                time.sleep(3)
    return {"is_affected": False, "affected_article": None, "reason": "API Error"}

# 5. Pipeline execution — FULL COVERAGE (zero threshold, top-5 amendments)
cache_lock = threading.Lock()
candidates = []
total_skipped_no_newer = 0

for q in questions:
    filepath = q["_bank_file"]
    qid_str = str(q["id"])
    
    if (filepath, qid_str) in EXCLUSIONS:
        continue
        
    q_text = f"{q['question']} {' '.join(q['options'])}"
    q_year = get_bank_year(q["_bank_name"])
    
    # Compute query TF-IDF vector
    q_ngrams = get_ngrams(q_text)
    q_tf = {}
    for token in q_ngrams:
        q_tf[token] = q_tf.get(token, 0) + 1
        
    q_vector = {}
    q_length_sq = 0.0
    for token, val in q_tf.items():
        w = val * idf.get(token, 0.0)
        q_vector[token] = w
        q_length_sq += w * w
    q_length = math.sqrt(q_length_sq)
    
    if q_length > 0:
        for token in q_vector:
            q_vector[token] /= q_length
            
    # Calculate similarity with ALL newer amendments (zero threshold)
    newer_scores = []
    for i_doc, doc in enumerate(doc_vectors):
        try:
            amend_year = int(doc["date_roc"].split('/')[0])
            if amend_year > q_year:
                similarity = 0.0
                for token, w in q_vector.items():
                    if token in doc["vector"]:
                        similarity += w * doc["vector"][token]
                newer_scores.append({
                    "similarity": similarity,
                    "article_no": doc["article_no"],
                    "law_name": doc["law_name"],
                    "date_roc": doc["date_roc"],
                    "text": doc["raw_text"],
                    "reason": doc["raw_reason"],
                    "amend_year": amend_year
                })
        except Exception:
            pass
    
    if not newer_scores:
        total_skipped_no_newer += 1
        continue
    
    # Sort by similarity descending, take top-5
    newer_scores.sort(key=lambda x: x["similarity"], reverse=True)
    top_amendments = newer_scores[:5]
    top_art_keys = {(a["law_name"], a["article_no"]) for a in top_amendments}
    
    # Keyword matching: extract article numbers from question text
    art_mentions_with_law = re.findall(r'(道路交通管理處罰條例|處罰條例|道路交通安全規則|安全規則)?\s*第\s*(\d+(?:[\-之]\d+)?)\s*條', q_text)
    for law_pref, art_ref in art_mentions_with_law:
        art_normalized = art_ref.replace('之', '-')
        target_law = None
        if law_pref in ["道路交通管理處罰條例", "處罰條例"]:
            target_law = "道路交通管理處罰條例"
        elif law_pref in ["道路交通安全規則", "安全規則"]:
            target_law = "道路交通安全規則"
            
        for ns in newer_scores:
            if ns["article_no"] == art_normalized:
                if target_law is None or ns["law_name"] == target_law:
                    if (ns["law_name"], ns["article_no"]) not in top_art_keys:
                        top_amendments.append(ns)
                        top_art_keys.add((ns["law_name"], ns["article_no"]))
                        break
    
    candidates.append({
        "bank_file": filepath,
        "bank_name": q["_bank_name"],
        "id": qid_str,
        "question": q["question"],
        "options": q["options"],
        "correct_idx": q["answer"],
        "q_year": q_year,
        "top_amendments": top_amendments,
        "top_score": newer_scores[0]["similarity"]
    })

print(f"Questions with newer amendments (ALL sent to LLM): {len(candidates)}")
print(f"Questions with NO newer amendments (auto-safe): {total_skipped_no_newer}")

# Thread-safe LLM query helper for multi-amendment evaluation
def process_candidate(idx, c):
    # Check if this candidate contains any Safety Rules amendments
    has_safety = any(a["law_name"] == "道路交通安全規則" for a in c["top_amendments"])
    
    cache_key_v3 = f"v3::{c['bank_file']}::{c['id']}"
    cache_key_v2 = f"v2::{c['bank_file']}::{c['id']}"
    
    decision = None
    with cache_lock:
        if cache_key_v3 in llm_cache:
            decision = llm_cache[cache_key_v3]
            print(f"[{idx+1}/{len(candidates)}] Cache Hit (v3) for ID {c['id']} ({c['bank_name']})")
        elif not has_safety and cache_key_v2 in llm_cache:
            decision = llm_cache[cache_key_v2]
            print(f"[{idx+1}/{len(candidates)}] Cache Hit (v2 fallback) for ID {c['id']} ({c['bank_name']})")
            
    if decision is not None:
        return c, decision
        
    print(f"[{idx+1}/{len(candidates)}] Querying LLM for ID {c['id']} of {c['bank_name']} ({len(c['top_amendments'])} amendments, has_safety={has_safety})...")
    options_text = "\n".join([f"({chr(65+i)}) {opt}" for i, opt in enumerate(c["options"])])
    
    if isinstance(c["correct_idx"], list):
        correct_letter = ",".join([chr(65 + ci) for ci in c["correct_idx"]])
        correct_text = ",".join([c["options"][ci] for ci in c["correct_idx"]])
    else:
        correct_letter = chr(65 + c["correct_idx"])
        correct_text = c["options"][c["correct_idx"]]
    
    decision = query_local_llm_multi(
        q_year=c["q_year"],
        q_text=c["question"],
        options=options_text,
        correct_letter=correct_letter,
        correct_text=correct_text,
        amendment_list=c["top_amendments"]
    )
    
    store_key = cache_key_v3 if has_safety else cache_key_v2
    with cache_lock:
        llm_cache[store_key] = decision
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(llm_cache, f, ensure_ascii=False, indent=2)
            
    return c, decision

overrides = {}
audit_report = []
total_affected = 0

# Run LLM validation in parallel (2 threads)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(process_candidate, i, c) for i, c in enumerate(candidates)]
    for f in concurrent.futures.as_completed(futures):
        c, decision = f.result()
        is_affected = decision.get("is_affected", False)
        reason = decision.get("reason", "")
        affected_article = decision.get("affected_article", None)
        
        # Determine which law and article were affected
        matched_amend = None
        if is_affected:
            if affected_article:
                m = re.search(r'(\d+(?:-\d+)?)', str(affected_article))
                art_no_str = m.group(1) if m else None
                if art_no_str:
                    for a in c["top_amendments"]:
                        if a["article_no"] == art_no_str:
                            matched_amend = a
                            break
            if not matched_amend and c["top_amendments"]:
                matched_amend = c["top_amendments"][0]
        
        audit_report.append({
            "bank_file": c["bank_file"],
            "bank_name": c["bank_name"],
            "id": c["id"],
            "question": c["question"],
            "num_amendments_checked": len(c["top_amendments"]),
            "top_score": c["top_score"],
            "is_affected": is_affected,
            "affected_article": affected_article,
            "reason": reason
        })
        
        if is_affected and matched_amend:
            total_affected += 1
            law_name = matched_amend["law_name"]
            art_no = matched_amend["article_no"]
            
            warning_key = f"{law_name}::{art_no}"
            warning_msg = ARTICLE_WARNINGS.get(warning_key) or ARTICLE_WARNINGS.get(art_no)
            
            if not warning_msg:
                if law_name == "道路交通管理處罰條例":
                    warning_msg = f"⚠️ 本題涉及的條例第 {art_no} 條在您考卷的年份之後曾經進行過法律修正，請以最新規定為準。"
                else:
                    warning_msg = f"⚠️ 本題涉及的安全規則第 {art_no} 條在您考卷的年份之後曾經進行過安全規則修正，請以最新規定為準。"
            
            custom_warning = f"{warning_msg}\n【地端模型分析影響原因】：{reason}"
            overrides.setdefault(c["bank_file"], {}).setdefault(c["id"], {})["warning"] = custom_warning

# Apply repeats (independent of LLM)
for key, bank_names in repeats_map.items():
    filepath, qid_str = key
    overrides.setdefault(filepath, {}).setdefault(qid_str, {})["repeats"] = bank_names

# Apply manual corrections
for bank_file, qid_patches in MANUAL_CORRECTIONS.items():
    for qid_str, patch in qid_patches.items():
        overrides.setdefault(bank_file, {}).setdefault(qid_str, {}).update(patch)

# Write overrides to overrides.json
os.makedirs(os.path.dirname(overrides_file), exist_ok=True)
with open(overrides_file, "w", encoding="utf-8") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

# Sort audit report by bank name and question ID for neat output
audit_report.sort(key=lambda r: (r["bank_name"], int(r["id"])))

# Write human-readable audit log
with open(audit_log_file, "w", encoding="utf-8") as f:
    f.write("========================================================================\n")
    f.write("FULL COVERAGE AUDIT LOG - Combined Act + Safety Rules Amendments\n")
    f.write(f"Total Questions Checked by LLM: {len(candidates)}\n")
    f.write(f"Questions Auto-Safe (no newer amendments): {total_skipped_no_newer}\n")
    f.write(f"LLM Approved Affected Questions: {total_affected}\n")
    f.write("========================================================================\n\n")
    
    for r in audit_report:
        status = '⚠️ AFFECTED' if r['is_affected'] else '✅ NOT AFFECTED'
        f.write(f"[{r['bank_name']} ID {r['id']}] Checked {r['num_amendments_checked']} amendments (Top similarity: {r['top_score']:.3f})\n")
        f.write(f"  Q: {r['question']}\n")
        f.write(f"  Decision: {status}")
        if r['is_affected'] and r.get('affected_article'):
            f.write(f" → {r['affected_article']}")
        f.write(f"\n")
        f.write(f"  Reason: {r['reason']}\n")
        f.write("-" * 80 + "\n\n")

print(f"\nSuccess! Full coverage audit complete.")
print(f"  Total questions: {len(questions)}")
print(f"  Checked by LLM: {len(candidates)}")
print(f"  Auto-safe (no newer amendments): {total_skipped_no_newer}")
print(f"  Marked affected: {total_affected}")
print(f"  Manual corrections: {sum(len(v) for v in MANUAL_CORRECTIONS.values())}")
print(f"  Override entries (total): {sum(len(v) for v in overrides.values())}")
print(f"  Audit log: {audit_log_file}")
