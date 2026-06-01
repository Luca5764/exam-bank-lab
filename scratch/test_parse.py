import sys
from pathlib import Path

# Add the tools directory to path
sys.path.append(str(Path("g:/User/Downloads/TS/Code/Irrigation_Quiz/tools").resolve()))

import import_traffic_questions as parser

lines = [
    "（  124  ）",
    "6.  行駛之汽車與汽車或其他障礙物體衝撞時，其衝撞力之大小",
    "與何者有關？ (1)車重 (2)車速 (3)汽車性能 (4)兩車衝",
    "撞開始至結束移動的距離。"
]

joined = parser.join_continued_lines(lines, "multi")
print("Joined line:")
print(joined[0])
print()

# Now parse it as multi question
parsed_qs = parser.parse_multi_questions(lines)
if parsed_qs:
    q = parsed_qs[0]
    print("Parsed Question:")
    print("  ID:", q.id)
    print("  Question:", q.question)
    print("  Options:", q.options)
    print("  Answer:", q.answer)
    print("  Warnings:", q.warnings)
else:
    print("Failed to parse as multi-choice question!")
