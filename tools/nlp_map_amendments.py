import json
import os
import re
import sys
import math

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
amendments_file = os.path.join(root_dir, "data", "traffic_law_amendments.json")
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

if not os.path.exists(amendments_file) or not os.path.exists(merged_file):
    print("Required data files not found!")
    sys.exit(1)

with open(amendments_file, "r", encoding="utf-8") as f:
    amendments = json.load(f)

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

print(f"Loaded {len(amendments)} amendments and {len(questions)} questions.")

# 1. Chinese text tokenizer (character unigrams + bigrams)
def get_ngrams(text):
    # Clean text to keep alphanumeric and CJK characters
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    tokens = []
    # Unigrams
    tokens.extend(list(text))
    # Bigrams
    for i in range(len(text) - 1):
        tokens.append(text[i:i+2])
    return tokens

# 2. Build TF-IDF for the 83 amendments
corpus = []
for idx, a in enumerate(amendments):
    # Combine article info, text, and reason
    doc_text = f"{a['article_raw']} {a['text']} {a['reason']}"
    corpus.append({
        "index": idx,
        "article_no": a["article_no"],
        "date_roc": a["date_roc"],
        "text": doc_text,
        "ngrams": get_ngrams(doc_text)
    })

# Compute Document Frequency (DF)
df = {}
for doc in corpus:
    unique_tokens = set(doc["ngrams"])
    for token in unique_tokens:
        df[token] = df.get(token, 0) + 1

N = len(corpus)
idf = {}
for token, count in df.items():
    idf[token] = math.log((N + 1) / (count + 0.5)) + 1 # smoothed idf

# Compute TF-IDF vectors for documents
doc_vectors = []
for doc in corpus:
    tf = {}
    for token in doc["ngrams"]:
        tf[token] = tf.get(token, 0) + 1
    
    # L2 normalize
    vector = {}
    length_sq = 0.0
    for token, val in tf.items():
        w = val * idf.get(token, 0.0)
        vector[token] = w
        length_sq += w * w
    length = math.sqrt(length_sq)
    
    # Normalize vector
    if length > 0:
        for token in vector:
            vector[token] /= length
            
    doc_vectors.append({
        "article_no": doc["article_no"],
        "date_roc": doc["date_roc"],
        "vector": vector
    })

# 3. Vectorize queries and calculate cosine similarity
mapped_count = 0
matches_report = []

for q in questions:
    q_text = f"{q['question']} {' '.join(q['options'])}"
    q_ngrams = get_ngrams(q_text)
    
    # Compute query TF
    q_tf = {}
    for token in q_ngrams:
        q_tf[token] = q_tf.get(token, 0) + 1
        
    # L2 normalize query vector
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
            
    # Calculate similarity with all documents
    scores = []
    for doc in doc_vectors:
        similarity = 0.0
        # Dot product
        for token, w in q_vector.items():
            if token in doc["vector"]:
                similarity += w * doc["vector"][token]
        scores.append((similarity, doc["article_no"], doc["date_roc"]))
        
    scores.sort(key=lambda x: x[0], reverse=True)
    top_score, top_art, top_date = scores[0]
    
    # If similarity is strong, record match
    if top_score > 0.22: # Cosine similarity threshold
        mapped_count += 1
        matches_report.append({
            "bank": q["_bank_name"],
            "id": q["id"],
            "question": q["question"],
            "matched_article": top_art,
            "matched_date": top_date,
            "score": top_score
        })

print(f"Mapped {mapped_count} questions using TF-IDF Cosine Similarity.")

# Write report to check matches
report_path = os.path.join(root_dir, "scratch", "nlp_mapping_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(matches_report, f, ensure_ascii=False, indent=2)

print(f"NLP mapping report written to {report_path}")
