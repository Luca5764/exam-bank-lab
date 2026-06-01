import re

def clean_cjk_spaces(text: str) -> str:
    pattern = re.compile(
        r"(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffee])"
        r"\s+"
        r"(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffee])"
    )
    return pattern.sub("", text)

input_str = "逾 3 公尺"
output_str = clean_cjk_spaces(input_str)
print("Input:", repr(input_str))
print("Output:", repr(output_str))
