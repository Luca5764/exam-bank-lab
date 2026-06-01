import re

# Question text body
text = "(1)50 至 100 (2)101 至 150 (3)151 至 200 (4)201 至 250 公尺處，設置車輛故障標誌警示之。"

# Extract options like in import_traffic_questions
OPTION_RE = re.compile(
    r"(?:[([（［\]]\s*([1-4])\s*[)\]^）］]?|[([（［\]]?\s*([1-4])\s*[)\]^）］])"
)

markers = list(OPTION_RE.finditer(text))
first_marker = next(m for m in markers if (m.group(1) or m.group(2)) == "1")

# Extract initial options
option_positions = []
expected = 1
for m in markers:
    digit = m.group(1) or m.group(2)
    n = int(digit)
    if n == expected:
        option_positions.append((m.start(), m.end(), n))
        expected += 1
        if expected > 4:
            break

options = []
for i, (start, end, _) in enumerate(option_positions):
    if i + 1 < len(option_positions):
        opt_text = text[end:option_positions[i + 1][0]]
    else:
        opt_text = text[end:]
    opt_text = opt_text.strip().rstrip("。.，,；")
    opt_text = re.sub(r"\s+", " ", opt_text).strip()
    options.append(opt_text)

print("Original Options:")
print(options)
print()

# Run splitting logic
avg_len = sum(len(opt) for opt in options[:3]) / 3
print("Average Length of first 3 options:", avg_len)

# 1. Clean for suffix
def clean_for_suffix(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]", "", s)

cleaned_opts = [clean_for_suffix(opt) for opt in options[:3]]
print("Cleaned Options for Suffix:", cleaned_opts)

suffix = ""
if all(cleaned_opts):
    min_l = min(len(s) for s in cleaned_opts)
    for idx in range(1, min_l + 1):
        char = cleaned_opts[0][-idx]
        if all(s[-idx] == char for s in cleaned_opts):
            suffix = char + suffix
        else:
            break

print("Detected Suffix:", repr(suffix))

# PROPOSED FIX: Reject purely numeric suffixes
is_valid_suffix = suffix and not suffix.isdigit()
print("Is Valid Suffix (non-numeric):", is_valid_suffix)

best_opt = options[3]
best_q = ""

if is_valid_suffix:
    suffix_match = re.search(re.escape(suffix), options[3])
    if suffix_match:
        split_idx = suffix_match.end()
        best_opt = options[3][:split_idx].strip()
        best_q = options[3][split_idx:].strip()

# Whitespace fallback
if not best_q:
    min_diff = float("inf")
    for match in re.finditer(r"\s+", options[3]):
        start = match.start()
        opt_part = options[3][:start].strip()
        q_part = options[3][match.end():].strip()
        if not opt_part or not q_part:
            continue
        diff = abs(len(opt_part) - avg_len)
        if diff < min_diff:
            min_diff = diff
            best_opt = opt_part
            best_q = q_part

print("\nAfter Split Logic:")
print("  Option 4:", repr(best_opt))
print("  Question Stem Trailing:", repr(best_q))
