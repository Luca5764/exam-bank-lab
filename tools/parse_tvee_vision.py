import os
import json
import sys
import re
from pathlib import Path

# 強制將 stdout 編碼設為 utf-8，避免 Windows 終端機 (CP950) 顯示錯誤
sys.stdout.reconfigure(encoding='utf-8')

import torch
from transformers import pipeline
import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

load_dotenv(".env")
hf_token = os.environ.get("HF_TOKEN")

# 模型設定 (統測專二專用)
MODEL_ID = "Qwen/Qwen3.5-4B"

def load_pipeline():
    print(f"正在載入視覺管線: {MODEL_ID} (FP16 模式)...")
    pipe = pipeline(
        "image-text-to-text",
        model=MODEL_ID,
        device_map="auto",
        torch_dtype=torch.float16,
        token=hf_token
    )
    print("✅ 模型載入完成！\n" + "="*60)
    return pipe

def extract_tvee_answers(ans_pdf_path):
    """解析統測的 答.pdf 並回傳 {題號: 答案索引(1-4)} 的字典"""
    doc = fitz.open(ans_pdf_path)
    answers = {}
    for page in doc:
        text = page.get_text("text")
        words = text.split()
        for i, w in enumerate(words):
            if w.isdigit() and 0 < int(w) <= 100:
                if i + 1 < len(words) and words[i+1] in ['A', 'B', 'C', 'D']:
                    answers[int(w)] = {'A': 0, 'B': 1, 'C': 2, 'D': 3}[words[i+1]]
    doc.close()
    return answers

def pdf_to_images(pdf_path, dpi=200):
    print(f"正在將 PDF 轉為圖片: {pdf_path}")
    doc = fitz.open(pdf_path)
    images = []
    
    # 從第二頁開始讀取，因為第一頁通常是考試說明（統測特性）
    start_page = 1 if len(doc) > 1 else 0
    
    for page_num in range(start_page, len(doc)):
        page = doc.load_page(page_num)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 統測通常是直式 A4，若有橫向可加入裁切邏輯
        if img.width > img.height:
            # 切割橫向 A3 為兩張 A4
            mid_x = img.width // 2
            left_img = img.crop((0, 0, mid_x, img.height))
            right_img = img.crop((mid_x, 0, img.width, img.height))
            images.extend([left_img, right_img])
        else:
            images.append(img)
            
    doc.close()
    print(f"✅ 成功渲染出 {len(images)} 頁題目圖片。")
    return images

def post_process_tvee_questions(questions, answers_dict):
    """後處理：合併答案，清理題號與選項標號"""
    cleaned_questions = []
    for q in questions:
        q_id = q.get("id", 0)
        
        # 確保 id 為整數（模型可能吐出字串 "7"）
        if isinstance(q_id, str) and q_id.isdigit():
            q_id = int(q_id)
            q["id"] = q_id
        
        # 合併真實答案
        if isinstance(q_id, int) and q_id in answers_dict:
            q["answer"] = answers_dict[q_id]
        else:
            q["answer"] = 0  # 找不到答案時預設給 0
            print(f"  ⚠️ 題號 {q_id} 在答案本中找不到對應解答，預設為 0")
            
        question_text = str(q.get("question", "")).strip()
        raw_options = q.get("options", [])  # 保留原始選項供尾綴比對用
        
        # 移除不小心黏在題目尾巴的選項文字（必須在清理選項標號之前做）
        if len(raw_options) >= 3:
            opt0 = str(raw_options[0]).strip()
            opt1 = str(raw_options[1]).strip()
            opt_last = str(raw_options[-1]).strip()
            if opt0 and opt1 and opt_last:
                idx = question_text.rfind(opt0)
                if idx != -1:
                    tail = question_text[idx:]
                    if opt1 in tail and opt_last in tail:
                        cut_idx = idx
                        prefix = question_text[max(0, idx-5):idx]
                        match = re.search(r'[\(（]?[A-Da-d1-4①②③④][\)）]?\s*[.．、]?\s*$', prefix)
                        if match:
                            cut_idx -= len(match.group(0))
                        question_text = question_text[:cut_idx].strip()
        
        # 清除題號 (例如 "43. 題目" 或 "12 題目")
        question_text = re.sub(r'^\d+\s*[.．、]\s*', '', question_text)
        question_text = re.sub(r'^\d+\s+', '', question_text)
        q["question"] = question_text
                
        # 清理選項標號
        cleaned_options = []
        for opt in raw_options:
            opt = str(opt)
            opt = re.sub(r'^[\(（][A-Da-d1-4][\)）]\s*', '', opt)
            opt = re.sub(r'^[A-Da-d1-4]\s*[.．、]\s*', '', opt)
            opt = re.sub(r'^[A-Da-d]\s+', '', opt)
            opt = re.sub(r'^[①②③④]\s*', '', opt)
            cleaned_options.append(opt.strip())
        q["options"] = cleaned_options
            
        cleaned_questions.append(q)
    return cleaned_questions

def extract_json_from_response(response_text):
    """從 LLM 的回覆中精準擷取 JSON 陣列"""
    try:
        if re.search(r'\[\s*\]', response_text):
            return []
            
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response_text)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_match = re.findall(r'\{[\s\S]*?\}', response_text)
            if json_match:
                json_str = "[\n" + ",\n".join(json_match) + "\n]"
            else:
                raise ValueError("找不到 JSON 結構")

        json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
        try:
            return json.loads(json_str)
        except:
            pass
        
        with open("error_response.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        print("  ⚠️ JSON 解析失敗，已將 LLM 原始輸出存入 error_response.txt 供除錯用。")
        return []
    except Exception as e:
        print(f"  ⚠️ JSON 解析失敗: {e}")
        with open("error_response.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        return []

def ask_qwen_vision(pipe, image):
    system_prompt = """你是一個專業的考題解析 AI，具備強大的視覺排版理解能力。
請仔細閱讀圖片中的考卷，並依照人類的閱讀順序由上至下，將裡面的「單一選擇題」萃取出來，並轉換成嚴格的 JSON 陣列格式。

重要規則：
1. **只擷取選擇題**。
   - 完全忽略：問答題、申論題、計算題、填充題、頁首頁尾等非題目內容。
   - **請注意，這份考卷沒有印上解答，你不必尋找答案。**

2. 每個物件必須包含以下欄位：
   - "id": 題號（整數，請務必正確抓取題目最前面的數字，例如 "1. 下列何者..." 則 id 為 1）
   - "question": 題目敘述（字串，請一字不漏照抄題目文字，包含最前面的題號，例如 "1. 下列何者錯誤？"）
   - "options": 選項陣列（字串陣列，包含 4 個選項文字）
   - "context": 若該題屬於「情境題組」（例如「依據下文回答第 N 題至 N+3 題」），請將**共用的情境文字**或**情境表格**完整填入此欄位。若是獨立題目則可省略此欄位或填空字串。

3. **特別注意：表格與題組**
   - 如果題目敘述或情境說明中包含「表格」，請務必將其轉換為標準的 **Markdown 表格語法**（例如 `|欄位1|欄位2|\n|---|---|`），並放入對應的 `question` 或 `context` 欄位中。
   - 對於屬於同一個題組的連續多個子題，請在每一個子題的 "context" 欄位中，都**重複填入**該題組完整的情境說明。

4. 如果遇到「以上皆是」、「以上皆非」、「選項(A)和(B)」這類交叉引用其他選項的內容，請加上 "noShuffle": true。

5. 只輸出 JSON 陣列，不要輸出任何其他說明文字！"""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": system_prompt + "\n\n請解析這張考卷圖片中的選擇題："}
            ]
        }
    ]
    
    # 執行推論 (給足 token 讓模型思考完再輸出 JSON)
    out = pipe(messages, max_new_tokens=32768, return_full_text=False)
    response = out[0]['generated_text']
    response = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()
    return response

def process_tvee_pdf(q_pdf_path, a_pdf_path, pipe):
    out_dir = Path("../questions")
    out_dir.mkdir(exist_ok=True)
    
    # 決定輸出檔名 (例如 109.json)
    base_name = q_pdf_path.stem.split("-")[0]
    out_path = out_dir / f"{base_name}_統測專二.json"
    
    # 解析答案本
    print(f"📖 正在解析解答本: {a_pdf_path.name}")
    answers_dict = extract_tvee_answers(a_pdf_path)
    print(f"✅ 成功萃取出 {len(answers_dict)} 題解答。")
    
    # 渲染題目本
    images = pdf_to_images(q_pdf_path, dpi=200)
    if not images:
        return
        
    all_questions = []
    
    def save_progress():
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(all_questions, f, ensure_ascii=False, indent=2)

    for i, img in enumerate(images):
        print(f"  👁️ 正在解析第 {i+1}/{len(images)} 頁圖片...")
        response = ask_qwen_vision(pipe, img)
        questions = extract_json_from_response(response)
        
        if questions:
            # 進行後處理：合併答案與清理
            questions = post_process_tvee_questions(questions, answers_dict)
            
            print(f"  ✅ 從本頁萃取出 {len(questions)} 題")
            all_questions.extend(questions)
            save_progress()
            print(f"  💾 已寫入 {out_path.resolve()} (累計 {len(all_questions)} 題)")
        else:
            print(f"  ⚠️ 本頁未萃取出任何題目")
            
    print(f"🎉 全部完成！共解析出 {len(all_questions)} 題。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python parse_tvee_vision.py <資料夾路徑>")
        print("範例: python parse_tvee_vision.py ..\\統測專二\\109")
        sys.exit(1)
        
    target_path = Path(sys.argv[1])
    
    # 尋找該資料夾內的 -題.pdf 與 -答.pdf
    q_pdfs = list(target_path.glob("*-題.pdf"))
    if not q_pdfs:
        print(f"錯誤：在 {target_path} 找不到 *-題.pdf")
        sys.exit(1)
        
    pipe = load_pipeline()
    
    for q_pdf in q_pdfs:
        base_name = q_pdf.stem.split("-")[0]
        a_pdf = target_path / f"{base_name}-答.pdf"
        
        if not a_pdf.exists():
            print(f"⚠️ 找不到對應的答案本 {a_pdf.name}，將跳過 {q_pdf.name}")
            continue
            
        print(f"\n{'='*60}\n▶ 處理組別: {base_name}\n{'='*60}")
        process_tvee_pdf(q_pdf, a_pdf, pipe)
