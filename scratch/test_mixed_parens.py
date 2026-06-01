import re

# Mixed parentheses line
line = "（ 3 ) 7. 大型重型機車，除「道路交通管理處罰條例」另有規定外"

# Current regex
NEW_QUESTION_OLD = re.compile(r"^\s*[（]\s*.*?\s*[）]\s*\d{1,2}\s*[.．]")

# Proposed regex (supports mixed parenthesis types)
NEW_QUESTION_NEW = re.compile(r"^\s*[（(]\s*.*?\s*[）)]\s*\d{1,2}\s*[.．]")

print("Matches with OLD regex:", bool(NEW_QUESTION_OLD.match(line)))
print("Matches with NEW regex:", bool(NEW_QUESTION_NEW.match(line)))
