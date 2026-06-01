import re

def normalize_spacing(text: str) -> str:
    if not text:
        return text
    
    # 1. Insert space between CJK and Alphanumeric
    # Lookbehind for CJK character, lookahead for Alphanumeric
    text = re.sub(
        r"(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffee])(?=[A-Za-z0-9])",
        " ",
        text
    )
    
    # 2. Insert space between Alphanumeric and CJK
    # Lookbehind for Alphanumeric, lookahead for CJK character
    text = re.sub(
        r"(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffee])",
        " ",
        text
    )
    
    # 3. Clean up any accidental double spaces created
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()

test_cases = [
    "逾3公尺",
    "逾3.5公尺",
    "逾 3 公尺",
    "逾3.5 公尺",
    "50至100",
    "50 至 100",
    "新臺幣3,600元",
    "新臺幣 3,600 元",
    "5年內違反本規定2次以上者",
    "ABS作用可防止車輪鎖住",
    "TCS系統在濕滑路面起步"
]

def test():
    print("--- SPACING NORMALIZER TEST ---")
    for t in test_cases:
        out = normalize_spacing(t)
        print(f"Input : {repr(t)}")
        print(f"Output: {repr(out)}")
        print("-" * 50)

if __name__ == "__main__":
    test()
