import re

# Question text with mixed parens answer and normal options
text = "（ 3 ) 7. 大型重型機車，除「道路交通管理處罰條例」另有規定外，比照 (1) 普通重型機車 (2)輕型機車"
text_free_score = "（送分） 8. 麥花臣式前懸吊系統又名 (1)整體式 (2)獨立式"

# Upgraded anchored regexes
SINGLE_ANSWER_RE = re.compile(r"^\s*[（(]\s*(\d)\s*[）)]")

def parse_single_answer(t: str) -> int | None:
    match = SINGLE_ANSWER_RE.search(t)
    if match:
        n = int(match.group(1))
        if 1 <= n <= 4:
            return n - 1
    return None

print("Parsed Answer for Q7:", parse_single_answer(text))
print("Parsed Answer for Q8 (free score):", parse_single_answer(text_free_score))
