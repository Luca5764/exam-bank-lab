import sys
import json
import os
import re
import fitz  # PyMuPDF
from PIL import Image
from pathlib import Path
from dotenv import load_dotenv

# 確保套件存在
try:
    import torch
    from transformers import pipeline
except ImportError as e:
    print(f"請先安裝必要套件: pip install transformers torch accelerate qwen-vl-utils torchvision PyMuPDF pillow\n錯誤: {e}")
    sys.exit(1)

# 強制終端機使用 UTF-8 輸出，避免 Windows 預設 CP950 報錯
sys.stdout.reconfigure(encoding='utf-8')

# 載入 .env 裡面的 HF_TOKEN
load_dotenv("../.env")
load_dotenv(".env")
hf_token = os.environ.get("HF_TOKEN")

# 模型設定 (改用 4B 輕量化視覺模型)
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
    print("✅ 模型載入完成！")
    return pipe

def pdf_to_images(pdf_path, dpi=200):
    """將 PDF 每頁轉成高畫質 PIL.Image。若為橫向雙欄排版，會自動切成兩頁直式圖片。"""
    print(f"正在將 PDF 轉為圖片: {pdf_path}")
    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 判斷是否為橫向雙頁 (寬度大於高度)
        if img.width > img.height:
            # 切割成左右兩半
            mid_x = img.width // 2
            left_img = img.crop((0, 0, mid_x, img.height))
            right_img = img.crop((mid_x, 0, img.width, img.height))
            images.extend([left_img, right_img])
        else:
            images.append(img)
    
    doc.close()
    print(f"✅ 成功渲染並裁切出 {len(images)} 頁圖片。")
    return images

def post_process_questions(questions):
    """後處理：用正規表達式精準提取答案、移除題號，並清理選項標號"""
    cleaned_questions = []
    for q in questions:
        question_text = q.get("question", "").strip()
        raw_options = q.get("options", [])  # 保留原始選項供尾綴比對用
        
        # 1. 移除不小心黏在題目尾巴的選項文字（必須在清理題號與選項標號之前做）
        # 有些 LLM 會把整個選項列都塞進 question 中，例如 "題目... ①選項一②選項二..."
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
                        # 往前檢查是否有選項標記 (例如 ① 或 (A) )，有的話一併移除
                        prefix = question_text[max(0, idx-5):idx]
                        match = re.search(r'[\(（]?[A-Da-d1-4①②③④][\)）]?\s*[.．、]?\s*$', prefix)
                        if match:
                            cut_idx -= len(match.group(0))
                        question_text = question_text[:cut_idx].strip()
        
        # 2. 提取答案與清理題號
        # 支援格式: "【2】43. 題目", "(B) 43. 題目", "【1.2】 43. 題目", "【A或B】 43. 題目"
        ans_match = re.match(r'^【?\(?([1234ABCDabcd\.,、或和]+)\)?】?\s*\d+\s*[.．、]\s*(.*)', question_text)
        if ans_match:
            ans_str = ans_match.group(1).upper()
            first_valid = re.search(r'[1234ABCD]', ans_str)
            if first_valid:
                char = first_valid.group(0)
                if char in ['1', 'A']:
                    q["answer"] = 0
                elif char in ['2', 'B']:
                    q["answer"] = 1
                elif char in ['3', 'C']:
                    q["answer"] = 2
                elif char in ['4', 'D']:
                    q["answer"] = 3
            else:
                q["answer"] = 0
            q["question"] = ans_match.group(2).strip()
        else:
            # 若只匹配題號沒有答案，例如 "43. 題目"
            num_match = re.match(r'^\d+\s*[.．、]\s*(.*)', question_text)
            if num_match:
                q["question"] = num_match.group(1).strip()
            else:
                q["question"] = question_text
            
            # 若未匹配到正確答案，但 LLM 有猜測則保留，否則預設為 0
            if "answer" not in q or not isinstance(q["answer"], int) or q["answer"] not in [0, 1, 2, 3]:
                q["answer"] = 0
                
        # 3. 清理選項標號
        cleaned_options = []
        for opt in raw_options:
            opt = str(opt)
            # 移除選項前方的標號，例如 "(A)", "A.", "1.", "①", "A "
            # 要求後面要有符號或空白，或者被括號包圍，避免誤刪 "100萬元" 的 "1"
            opt = re.sub(r'^[\(（][A-Da-d1-4][\)）]\s*', '', opt) # (A) 或 (1)
            opt = re.sub(r'^[A-Da-d1-4]\s*[.．、]\s*', '', opt)   # A. 或 1. 或 1、
            opt = re.sub(r'^[A-Da-d]\s+', '', opt)                # A 
            opt = re.sub(r'^[①②③④]\s*', '', opt)                # ①
            cleaned_options.append(opt.strip())
        q["options"] = cleaned_options
        
        cleaned_questions.append(q)
    return cleaned_questions

def extract_json_from_response(response_text):
    """從 LLM 的回覆中精準擷取 JSON 陣列"""
    try:
        # 如果模型回傳空陣列 (代表該頁沒有選擇題)
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
        print("已將 LLM 原始輸出存入 error_response.txt 供除錯用。")
        return []
    except Exception as e:
        print(f"⚠️ JSON 解析失敗: {e}")
        with open("error_response.txt", "w", encoding="utf-8") as f:
            f.write(response_text)
        return []

def ask_qwen_vision(pipe, image):
    system_prompt = """你是一個專業的考題解析 AI，具備強大的視覺排版理解能力。
請仔細閱讀圖片中的考卷，並依照人類的閱讀順序由左至右、由上至下，將裡面的「單一選擇題」萃取出來，並轉換成嚴格的 JSON 陣列格式。

重要規則：
1. **只擷取選擇題**（有明確的 4 個選項可選的題目）。
   - 完全忽略：問答題、申論題、計算題、填充題、公文題、簡答題、配合題等非選擇題。
   - 也忽略考試說明、注意事項、頁首頁尾等非題目內容。

2. 每個物件必須包含以下欄位：
   - "question": 題目敘述（字串，請「一字不漏」照抄圖片上的題目文字，包含最前面的題號和括號答案，例如 "【2】43. 下列何者錯誤？"）
   - "options": 選項陣列（字串陣列，包含 4 個選項文字）
   - "answer": 預設填 0 即可（後續會由程式自動處理）

3. 如果遇到「以上皆是」、「以上皆非」、「選項(A)和(B)」這類交叉引用其他選項的內容，請加上 "noShuffle": true。

4. 只輸出 JSON 陣列，不要輸出任何其他說明文字！"""

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
    
    # 清除 thinking tags
    response = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()
    return response

def process_one_pdf(pdf_path, pipe):
    images = pdf_to_images(pdf_path, dpi=200)
    if not images:
        return 0
        
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

    for i, img in enumerate(images):
        print(f"  👁️ 正在解析第 {i+1}/{len(images)} 頁圖片...")
        response = ask_qwen_vision(pipe, img)
        questions = extract_json_from_response(response)
        
        if questions:
            # 進行後處理：清理題號、標記與答案對應
            questions = post_process_questions(questions)
            
            print(f"  ✅ 從本頁萃取出 {len(questions)} 題")
            all_questions.extend(questions)
            save_progress()
            print(f"  💾 已寫入 {out_path.resolve()} (累計 {len(all_questions)} 題)")
        else:
            print(f"  ⚠️ 本頁未萃取出任何題目")
            
    print(f"  📄 {Path(pdf_path).name} → {len(all_questions)} 題\n")
    return len(all_questions)

def collect_pdfs(args):
    """從命令列參數收集所有 PDF 檔案路徑"""
    pdf_files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            pdf_files.extend(sorted(p.rglob("*.pdf")))
        elif p.is_file() and p.suffix.lower() == ".pdf":
            pdf_files.append(p)
        else:
            print(f"⚠️ 跳過: {arg}")
    return pdf_files

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python parse_pdf_vision.py <pdf檔案路徑>           # 處理單一檔案")
        print("  python parse_pdf_vision.py <資料夾路徑>             # 處理資料夾內所有 PDF")
        sys.exit(1)
        
    pdf_files = collect_pdfs(sys.argv[1:])
    if not pdf_files:
        print("❌ 找不到任何 PDF 檔案！")
        sys.exit(1)

    pipe = load_pipeline()
    
    total_questions = 0
    for i, pdf_path in enumerate(pdf_files):
        print(f"{'='*60}")
        print(f"📖 [{i+1}/{len(pdf_files)}] {pdf_path.name}")
        print(f"{'='*60}")
        count = process_one_pdf(str(pdf_path), pipe)
        total_questions += count

    print(f"\n{'='*60}")
    print(f"🎉 全部完成！共處理 {len(pdf_files)} 個 PDF，解析出 {total_questions} 題。")
    print(f"結果已儲存至: {Path('../questions').resolve()}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
