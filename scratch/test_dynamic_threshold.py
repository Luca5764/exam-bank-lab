import re

# Test cases for short options
tests = [
    {
        "text": "(1)1 (2)2 (3)3 (4)4 付為限。",
        "options": ["1", "2", "3", "4 付為限"]
    },
    {
        "text": "(1)1 (2)2 (3)3 (4)4 噸以下。",
        "options": ["1", "2", "3", "4 噸以下"]
    }
]

def test():
    for idx, t in enumerate(tests):
        options = list(t["options"])
        avg_len = sum(len(opt) for opt in options[:3]) / 3
        print(f"Test {idx+1}:")
        print("  Options:", options)
        print("  Average length:", avg_len)
        
        # Calculate dynamic threshold
        if avg_len <= 2:
            diff_threshold = 2
        elif avg_len <= 5:
            diff_threshold = 3
        else:
            diff_threshold = 5
            
        print("  Threshold:", avg_len + diff_threshold)
        
        # Check condition
        should_split = len(options[3]) > avg_len + diff_threshold
        print("  Should Split:", should_split)
        
        if should_split:
            # 1. Clean for suffix
            def clean_for_suffix(s: str) -> str:
                return re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]", "", s)
            
            cleaned_opts = [clean_for_suffix(opt) for opt in options[:3]]
            suffix = ""
            if all(cleaned_opts):
                min_l = min(len(s) for s in cleaned_opts)
                for idx_char in range(1, min_l + 1):
                    char = cleaned_opts[0][-idx_char]
                    if all(s[-idx_char] == char for s in cleaned_opts):
                        suffix = char + suffix
                    else:
                        break
            
            is_valid_suffix = suffix and not suffix.isdigit()
            best_opt = options[3]
            best_q = ""
            
            if is_valid_suffix:
                suffix_match = re.search(re.escape(suffix), options[3])
                if suffix_match:
                    split_idx = suffix_match.end()
                    best_opt = options[3][:split_idx].strip()
                    best_q = options[3][split_idx:].strip()
            
            # 2. Whitespace split fallback
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
            
            print("  Parsed Option 4:", repr(best_opt))
            print("  Parsed Stem Trailing:", repr(best_q))
        print()

if __name__ == "__main__":
    test()
