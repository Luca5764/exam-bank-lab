#!/usr/bin/env python3
"""偵測題庫「選項夾帶題幹尾段」的切題錯誤（免 PDF，可在 CI 執行）。

背景
----
題庫由 PDF 解析匯入，偶爾會把題幹尾段（例如「…逾期 6 個月以上者，註銷其
牌照」）誤切進某個選項，造成該選項異常超長、夾帶句讀與條文尾語，且正解
位移。這類錯誤過去反覆出現。`tools/check_traffic_banks.py` 能用原始 PDF 逐
題比對抓出來，但需要 `交通部/` 下的 PDF，無法在 GitHub Actions 上執行。

本腳本只做「結構偵測」，不需 PDF：在『選項多為簡短數值/單位答案』的填空
題中，若某一選項異常超長且夾帶句讀或條文尾語關鍵字，幾乎可確定是被切進
來的題幹尾段。描述型題目（四個選項都是長句）不會被誤判，因為它不符合
「其餘選項都很短」這個前提。

用法
----
    python tools/check_split_errors.py            # 掃描 questions/*.json
    python tools/check_split_errors.py --selftest # 自測偵測器是否仍有效

偵測到問題時以 exit code 1 結束，供 CI 擋下部署。
"""
import argparse
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# 題幹尾段常見的條文尾語／動作詞：正常的「答案」選項極少出現這些字
TAIL_MARKERS = (
    "以上者", "註銷", "吊扣", "吊銷", "扣繳", "至檢驗合格", "發還",
    "禁止其行駛", "沒入", "處汽車所有人",
)

# 數值/單位答案：純粹的「3 個月」「0.25 毫克」「20」之類，作為「填空題」的判準
_UNITS = "個月|年|公尺|公分|公里|公噸|分鐘|小時|秒|歲|點|次|毫克|元|日|張|人|倍|度|%"
NUMERIC_ANSWER = re.compile(rf"^\d[\d,\.]*\s*(?:{_UNITS})?$")
NUMERIC_PREFIX = re.compile(rf"^\d[\d,\.]*\s*(?:{_UNITS})")

LONG = 14   # 視為「異常超長選項」的字數下限


def _is_numeric_answer(o):
    return bool(NUMERIC_ANSWER.match(o.strip()))


def find_leak(options):
    """回傳 (index, option)：偵測到被切進選項的題幹尾段；否則 None。

    高精準度判準（鎖定反覆出現的數值填空題切題）：
      1. 其餘選項（至少 n-1 個）都是純數值/單位答案 → 這是填空題。
      2. 剩下那個選項異常超長，且「以數值/單位開頭」後接句讀或條文尾語
         —— 也就是「正確答案 token＋被切進來的題幹尾段」的典型樣態。
    描述型題目（選項是詞句而非數值）不符前提 1，不會被誤判。
    """
    if not isinstance(options, list) or len(options) < 3:
        return None
    if not all(isinstance(o, str) for o in options):
        return None
    numeric_short = sum(1 for o in options if _is_numeric_answer(o))
    if numeric_short < len(options) - 1:
        return None
    for i, o in enumerate(options):
        s = o.strip()
        if _is_numeric_answer(s):
            continue
        if (len(s) >= LONG and NUMERIC_PREFIX.match(s)
                and ("，" in s or any(m in s for m in TAIL_MARKERS))):
            return (i, o)
    return None


def scan(paths):
    problems = []
    for fn in paths:
        try:
            data = json.load(open(fn, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            problems.append((fn, None, f"無法解析 JSON：{e}"))
            continue
        if not isinstance(data, list):
            continue
        for q in data:
            if not isinstance(q, dict):
                continue
            hit = find_leak(q.get("options"))
            if hit:
                idx, opt = hit
                problems.append(
                    (fn, q.get("id"), f"選項[{idx}] 夾帶疑似題幹尾段：「{opt}」")
                )
    return problems


def selftest():
    bad = [
        "1 個月", "3 個月", "6 個月",
        "1 年以上者，同時吊扣其牌照，至檢驗合格後發還，逾期 6 個月",
    ]
    good_numeric = ["1 個月", "3 個月", "6 個月", "1 年"]
    good_descriptive = [
        "大型車不得超過 15 公分，小型車不得超過 10 公分",
        "大型車不得超過 10 公分，小型車不得超過 15 公分",
        "大、小型車均不得超過 10 公分",
        "大、小型車均不得超過 15 公分",
    ]
    # 數值短選項 + 一個長的「非數值開頭」描述選項：合法的干擾選項，不可誤判
    good_mixed = [
        "1 年", "2 年", "3 年",
        "患有癲癇疾病者不得申請駕駛執照考驗",
    ]
    cases = {
        "切題（應抓到）": find_leak(bad) is not None,
        "純數值選項（不應誤判）": find_leak(good_numeric) is None,
        "描述型選項（不應誤判）": find_leak(good_descriptive) is None,
        "數值＋長描述干擾選項（不應誤判）": find_leak(good_mixed) is None,
    }
    for name, ok in cases.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    passed = all(cases.values())
    print("selftest:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="自測偵測器")
    ap.add_argument("--glob", default=None, help="自訂掃描範圍（預設 questions/*.json）")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = args.glob or os.path.join(base, "questions", "*.json")
    paths = sorted(glob.glob(pattern))
    problems = scan(paths)
    if not problems:
        print(f"OK：掃描 {len(paths)} 個題庫，未發現切題錯誤。")
        sys.exit(0)
    print(f"發現 {len(problems)} 個疑似切題錯誤：")
    for fn, qid, msg in problems:
        print(f"  {os.path.basename(fn)} 第 {qid} 題：{msg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
