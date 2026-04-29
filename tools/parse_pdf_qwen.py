import sys
import json
import re
import os
from pathlib import Path

# 確保套件存在 (若無請先 pip install transformers torch accelerate bitsandbytes pdfplumber)
try:
    import pdfplumber
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from dotenv import load_dotenv
except ImportError as e:
    print(f"請先安裝必要套件: pip install transformers torch accelerate bitsandbytes pdfplumber python-dotenv\n錯誤: {e}")
    sys.exit(1)

# 載入 .env 裡面的 HF_TOKEN
load_dotenv("../.env")
load_dotenv(".env")
hf_token = os.environ.get("HF_TOKEN")

# 模型設定
MODEL_ID = "Qwen/Qwen3.5-9B"

# 設定 4-bit 量化，確保 RTX 4080 (16GB VRAM) 跑得動
quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16, # RTX 4080 支援 fp16/bf16
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
)

def load_model():
    print(f"正在載入模型: {MODEL_ID} (4-bit 量化模式以符合 RTX 4080 顯存)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=hf_token)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        device_map="auto",
        quantization_config=quantization_config,
        token=hf_token
    )
    print("✅ 模型載入完成！")
    return model, tokenizer

def extract_text_from_pdf(pdf_path):
    print(f"正在讀取 PDF: {pdf_path}")
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages_text.append(text)
    print(f"✅ 成功讀取 {len(pages_text)} 頁內容。")
    return pages_text

def chunk_text(pages_text, pages_per_chunk=2):
    """將文本以 N 頁為單位進行分塊，避免超出 LLM 的 Context Window 或造成 JSON 輸出不穩"""
    chunks = []
    for i in range(0, len(pages_text), pages_per_chunk):
        chunk = "\n\n--- 換頁 ---\n\n".join(pages_text[i:i+pages_per_chunk])
        chunks.append(chunk)
    return chunks

def strip_thinking(response_text):
    """去除 Qwen3.5 思考模式的 Thinking Process 部分"""
    # 嘗試去除 <think>...</think> 標籤
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', response_text).strip()
    if cleaned:
        return cleaned
    # 嘗試去除 "Thinking Process:" 開頭的部分，找到 JSON 開始處
    json_start = response_text.find('[{')
    if json_start == -1:
        json_start = response_text.find('```json')
    if json_start != -1:
        return response_text[json_start:]
    return response_text

def extract_json_from_response(response_text):
    """從 LLM 回應中強行萃取出 JSON 陣列"""
    # 先去除思考過程
    response_text = strip_thinking(response_text)
    
    try:
        # 尋找 ```json ... ``` 區塊
        match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        if match:
            json_str = match.group(1)
        else:
            # 備案：尋找 [...] 結構
            match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
            if match:
                json_str = match.group(0)
            else:
                raise ValueError("找不到 JSON 結構")
        
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 格式錯誤，嘗試自動修復: {e}")
        # 嘗試修復常見問題：尾端逗號、截斷
        json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)  # 移除尾端逗號
        # 嘗試補全截斷的 JSON
        if not json_str.rstrip().endswith(']'):
            last_brace = json_str.rfind('}')
            if last_brace != -1:
                json_str = json_str[:last_brace+1] + ']'
        try:
            return json.loads(json_str)
        except:
            pass
        with open("error_response.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        print("已將 LLM 原始輸出存入 error_response.txt 供除錯用。")
        return []
    except Exception as e:
        print(f"⚠️ JSON 解析失敗: {e}")
        with open("error_response.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        print("已將 LLM 原始輸出存入 error_response.txt 供除錯用。")
        return []

def ask_qwen(model, tokenizer, text_chunk):
    system_prompt = """你是一個專業的考題解析 AI。
請將以下考試文字內容中的「單一選擇題」萃取出來，並轉換成嚴格的 JSON 陣列格式。

重要規則：
1. **只擷取選擇題**（有明確的 4 個選項可選的題目）。
   - 完全忽略：問答題、申論題、計算題、填充題、公文題、簡答題、配合題等非選擇題。
   - 也忽略考試說明、注意事項、頁首頁尾等非題目內容。

2. 每個物件必須包含以下欄位：
   - "question": 題目敘述（字串，請自動修正因 PDF 轉檔造成的亂碼或排版錯誤）
   - "options": 選項陣列（字串陣列，通常有 4 個選項）
   - "answer": 正確答案的索引值（整數，從 0 開始）

3. **正確答案的判定方式**（按優先順序）：
   - 如果題號前面有【數字】標記，例如「【4】1.下列何者錯誤？」，那個數字就是正確答案。
     注意：【1】代表第1個選項 → answer=0，【2】代表第2個選項 → answer=1，【3】→ answer=2，【4】→ answer=3。
   - 如果有「答案：A」或解答表，則按照對應的選項填入。
   - 如果都沒有，則根據你的專業知識判斷，無法判斷則填 0。

4. 如果遇到「以上皆是」、「以上皆非」、「選項(A)和(B)」這類交叉引用其他選項的內容，請加上 "noShuffle": true。

5. 只輸出 JSON 陣列，不要輸出任何其他說明文字！

範例格式：
```json
[
  {
    "question": "農田水利法的主管機關為何？",
    "options": ["內政部", "農業部", "環境部", "經濟部"],
    "answer": 1
  }
]
```"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"以下是 PDF 內容片段：\n\n{text_chunk}"}
    ]
    
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False  # 關閉思考模式，讓模型直接輸出 JSON
    )
    
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=8192,  # 加大以容納完整 JSON 輸出
            do_sample=True,
            temperature=0.1,  # 降低溫度以確保 JSON 格式穩定
            top_p=0.9,
            repetition_penalty=1.05
        )
    
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]
    
    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    return response

def process_one_pdf(pdf_path, model, tokenizer):
    """處理單一 PDF 檔案"""
    pages_text = extract_text_from_pdf(pdf_path)
    if not pages_text:
        print(f"⚠️ {pdf_path} 沒有可讀取的文字，跳過。")
        return 0

    chunks = chunk_text(pages_text, pages_per_chunk=2)

    all_questions = []

    out_dir = Path("../questions")
    out_dir.mkdir(exist_ok=True)
    pdf_stem = Path(pdf_path).stem
    out_path = out_dir / f"{pdf_stem}.json"

    def save_progress():
        for idx, q in enumerate(all_questions):
            q["id"] = idx + 1
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_questions, f, ensure_ascii=False, indent=2)

    for i, chunk in enumerate(chunks):
        print(f"  正在處理第 {i+1}/{len(chunks)} 區塊 (字數: {len(chunk)})...")
        if len(chunk.strip()) < 50:
            print("  區塊字數過少，跳過。")
            continue

        response = ask_qwen(model, tokenizer, chunk)
        questions = extract_json_from_response(response)

        if questions:
            print(f"  ✅ 從本區塊萃取出 {len(questions)} 題")
            all_questions.extend(questions)
            save_progress()
            print(f"  💾 已寫入 {out_path.resolve()} (累計 {len(all_questions)} 題)")
        else:
            print(f"  ⚠️ 本區塊未萃取出任何題目")

    print(f"  📄 {Path(pdf_path).name} → {len(all_questions)} 題\n")
    return len(all_questions)


def collect_pdfs(args):
    """從命令列參數收集所有 PDF 檔案路徑"""
    pdf_files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            # 遞迴搜尋資料夾內所有 PDF
            pdf_files.extend(sorted(p.rglob("*.pdf")))
        elif p.is_file() and p.suffix.lower() == ".pdf":
            pdf_files.append(p)
        else:
            print(f"⚠️ 跳過: {arg}")
    return pdf_files


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python parse_pdf_qwen.py <pdf檔案路徑>           # 處理單一檔案")
        print("  python parse_pdf_qwen.py <資料夾路徑>             # 處理資料夾內所有 PDF")
        print("  python parse_pdf_qwen.py file1.pdf file2.pdf ... # 處理多個檔案")
        sys.exit(1)

    pdf_files = collect_pdfs(sys.argv[1:])
    if not pdf_files:
        print("❌ 找不到任何 PDF 檔案！")
        sys.exit(1)

    print(f"📚 找到 {len(pdf_files)} 個 PDF 檔案：")
    for f in pdf_files:
        print(f"   - {f.name}")
    print()

    # 模型只載入一次！
    model, tokenizer = load_model()

    total_questions = 0
    for i, pdf_path in enumerate(pdf_files):
        print(f"{'='*60}")
        print(f"📖 [{i+1}/{len(pdf_files)}] {pdf_path.name}")
        print(f"{'='*60}")
        count = process_one_pdf(str(pdf_path), model, tokenizer)
        total_questions += count

    print(f"\n{'='*60}")
    print(f"🎉 全部完成！共處理 {len(pdf_files)} 個 PDF，解析出 {total_questions} 題。")
    print(f"結果已儲存至: {Path('../questions').resolve()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
