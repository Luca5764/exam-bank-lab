import re

line_114_2 = "（ 4 ）17. 汽缸總排氣量550 立方公分以上之機車，全長不得超過 (1)2.5  (2)3 (3)3.5 (4)4 公尺。"

# Our anchored regex
SINGLE_ANSWER_RE = re.compile(r"^\s*[（(]\s*(\d)\s*[）)]")

match = SINGLE_ANSWER_RE.search(line_114_2)
print("Line matches SINGLE_ANSWER_RE:", bool(match))
if match:
    print("Matched answer:", match.group(1))

# What about NEW_QUESTION_SINGLE_RE?
NEW_QUESTION_SINGLE_RE = re.compile(r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．]")
print("Line matches NEW_QUESTION_SINGLE_RE:", bool(NEW_QUESTION_SINGLE_RE.match(line_114_2)))
