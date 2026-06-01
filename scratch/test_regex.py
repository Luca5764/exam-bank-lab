import re

lines = [
    "（  124  ）",
    "6.  行駛之汽車與汽車或其他障礙物體衝撞時，其衝撞力之大小",
    "與何者有關？ (1)車重 (2)車速 (3)汽車性能 (4)兩車衝",
    "撞開始至結束移動的距離。"
]

ANSWER_ONLY_RE = re.compile(
    r"^\s*[（]\s*(?:[○╳OX×]|\d[\s、,，.\d]*)\s*[）]\s*$"
)

print("Line 0 matches:", bool(ANSWER_ONLY_RE.match(lines[0])))

# Let's trace join_continued_lines:
merged = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    if line and ANSWER_ONLY_RE.match(line) and i + 1 < len(lines):
        merged.append(line + " " + lines[i + 1].strip())
        i += 2
    else:
        merged.append(line)
        i += 1

print("Merged lines:")
for idx, l in enumerate(merged):
    print(f"  {idx}: {l}")

# Let's see NEW_QUESTION_MULTI_RE
NEW_QUESTION_MULTI_RE = re.compile(
    r"^\s*[（]\s*.*?\s*[）]\s*\d{1,2}\s*[.．]"
)

print("NEW_QUESTION_MULTI_RE matches merged[0]:", bool(NEW_QUESTION_MULTI_RE.match(merged[0])))
