import re

# Problematic questions extracted from PDFs (including new full-width parens cases)
texts = [
    # Q20 in 113-3
    "汽車軸距愈長，輪距愈寬，在轉彎時（1）最小迴轉半徑愈小（2）最小迴轉半徑愈大（3）內外輪差愈小（4）內外輪差不變。",
    # Q21 in 113-3
    "一般人在靜止狀態下，雙眼實際能辨別色彩之範圍只有（1)70度（2)120度（3)150度（4)180度。",
    # Q21 in 113-4
    "一般人在正常狀態下，視野約有 (1)70 度[2)120 度[3)160 度[4)200 度。",
    # ID 27
    "其主要行車性能包括下列各種性能(1)行駛性能(2)阻力性能(3)行車安全性能(4)附著性。",
    # ID 41 (115)
    "使用安全帶，下列敘述何者有誤？[1)可以扭曲或反裝[2)孕婦使用三點式[3)有損傷應換新[4)不可多人合用。"
]

# We want to match markers where the digit is 1-4.
# We include full-width opening parenthesis （ and full-width closing parenthesis ）
# We also include full-width brackets if needed.
OPTION_RE_PROPOSED = re.compile(
    r"(?:[([（［\]]\s*([1-4])\s*[)\]^）］]?|[([（［\]]?\s*([1-4])\s*[)\]^）］])"
)

def test():
    print("--- PROPOSED REGEX ---")
    for idx, t in enumerate(texts):
        matches = list(OPTION_RE_PROPOSED.finditer(t))
        digits = []
        for m in matches:
            d = m.group(1) or m.group(2)
            digits.append(d)
        print(f"Text {idx+1}: Found {len(matches)} matches: {digits}")
        if len(matches) != 4 or digits != ['1', '2', '3', '4']:
            print("  WARNING: Incorrect match!")

if __name__ == "__main__":
    test()
