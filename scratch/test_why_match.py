import re

line_17_opt = "(2)3 (3)3.5 (4)4 公尺。"
line_actual_q = "（ 3 ) 7. 大型重型機車，除「道路交通管理處罰條例」另有規定外"

# Upgraded regex with negative lookahead for decimal points
NEW_QUESTION_SINGLE_RE_NEW = re.compile(r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．](?!\d)")

print("--- NEW REGEX TEST ---")
print("Matches option line:", bool(NEW_QUESTION_SINGLE_RE_NEW.match(line_17_opt)))
print("Matches question line:", bool(NEW_QUESTION_SINGLE_RE_NEW.match(line_actual_q)))
