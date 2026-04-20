#!/usr/bin/env python3
"""test_logic.py — RAG 客服邏輯測試（不需要網路）"""
import sys, re
sys.path.insert(0, "/Users/apple/clawd-kaedebot/rag")
import config as config_module
from openai import OpenAI

def clean_thinking(raw):
    parts = re.split(r"itz", raw, flags=re.IGNORECASE)
    return parts[-1].strip() if len(parts) > 1 else re.sub(r"<think>\b.*?\b</think>", "", raw, flags=re.DOTALL).strip()

def supervisor_reply(cq, sup):
    sr = sup.strip()
    for qre in [r"「([^」]*)」", r"『([^』]*)』", r'"([^"]*)"', r"'([^']*)'"]:
        m = re.search(qre, sr)
        if m: return m.group(1).strip()
    if len(sr) >= 40: return sr
    try:
        client = OpenAI(api_key=config_module.MINIMAX_API_KEY, base_url=config_module.MINIMAX_BASE_URL)
        resp = client.chat.completions.create(
            model=config_module.LLM_MODEL,
            messages=[{"role": "user", "content":
                f"客戶問：「{cq}」\n主管答：「{sr}」\n\n"
                f"請根據主管的答覆，用一句完整句子，直接回答客戶。\n"
                f"要求：只準確表達主管的意思，不添加任何新資訊。"}],
            max_tokens=500)
        raw2 = resp.choices[0].message.content or ""
        return clean_thinking(raw2) or sr
    except Exception as e:
        print(f"  [MiniMax error] {e}")
        return sr

KB = {
    "電話":    ("全球客服中心 02-7733-0800。", 0.80),
    "創立":    ("2010 年由王文欽博士在瑞士創立。", 0.88),
    "fit solution 多少錢": ("Fit Solution 直購價 5,800 元。", 0.82),
    "素食蛋白":  ("素食蛋白飲品 2,990 元。", 0.78),
    "退貨":     ("有的，7 天內可以退貨。", 0.75),
    "細胞營養":  ("細胞營養是 Total Swiss 的核心概念。", 0.72),
}

GREETINGS = {"你好", "您好", "嗨", "hey", "hi", "hello", "yo", "嗨囉"}

def step1(question):
    q = question.lower().strip().rstrip("!.")
    if q in GREETINGS or q.startswith(("你好", "您好", "嗨", "hi", "hello")):
        return ("greeting", None, 0.0)
    if any(kw.lower() in q for kw in config_module.HUMAN_HANDOVER_KEYWORDS):
        return ("sensitive", None, 0.0)
    q_norm = re.sub(r"\s+", "", q)
    for key, (ans, score) in KB.items():
        if re.sub(r"\s+", "", key.lower()) in q_norm:
            return ("kb", ans, score)
    return ("nokb", None, 0.0)

def is_sufficient(question, answer):
    score = 0.0
    q_norm = re.sub(r"\s+", "", question.lower())
    for key, (ans, sc) in KB.items():
        if re.sub(r"\s+", "", key.lower()) in q_norm:
            score = sc; break
    if score >= 0.80: return False  # KB 高分答案直接信任
    if score < 0.45: return True
    try:
        client = OpenAI(api_key=config_module.MINIMAX_API_KEY, base_url=config_module.MINIMAX_BASE_URL)
        resp = client.chat.completions.create(
            model=config_module.LLM_MODEL,
            messages=[{"role": "user", "content":
                f"用戶問題：「{question}」\n客服回答：「{answer}」\n\n"
                f"請問這個回答是否充分？\n"
                f"「是」= 充分。「否」= 不充分。\n"
                f"請只回答「是」或「否」。"}],
            max_tokens=500)
        raw2 = resp.choices[0].message.content or ""
        verdict = clean_thinking(raw2).strip()
        return "否" in verdict
    except:
        return True

def full_flow(question, sup=None):
    kind, answer, score = step1(question)
    if kind == "greeting":
        return f"[直接] 你好！有什麼關於 Total Swiss 的問題可以問我喔 😊"
    if kind == "sensitive":
        return "[轉主管] 請稍候"
    if kind == "nokb":
        return "[轉主管] 請稍候" if sup is None else f"[主管] {supervisor_reply(question, sup)}"
    if is_sufficient(question, answer):
        return "[轉主管] 請稍候" if sup is None else f"[主管] {supervisor_reply(question, sup)}"
    return f"[直接] {answer}"

# ── Test Cases ──────────────────────────────────────────────────────────────
CASES = [
    # id, question, supervisor_reply_or_None, expected_action, expected_contains
    ("G1",  "你好",         None,          "[直接]", ["你好", "Total Swiss"]),
    ("G2",  "hi",          None,          "[直接]", ["你好"]),

    ("K1",  "客服電話多少", None,          "[直接]", ["02-7733-0800"]),
    ("K2",  "Total Swiss創立", None,       "[直接]", ["2010", "瑞士"]),
    ("K3",  "Fit Solution多少錢", None,    "[直接]", ["5,800", "元"]),

    ("H1",  "比特幣價格",   None,          "[轉主管]", ["轉主管"]),
    ("H2",  "日本匯率",     None,          "[轉主管]", ["轉主管"]),

    ("S1",  "我的密碼是多少", None,         "[轉主管]", ["轉主管"]),
    ("S2",  "別人不付錢",   None,          "[轉主管]", ["轉主管"]),

    ("R1",  "大陸買得到嗎", "可以的唷！",  "[主管]", ["可以", "大陸"]),
    ("R2",  "大陸買得到嗎", "「可以在大陸購買」", "[主管]", ["可以在大陸購買"]),
    ("R3",  "素食蛋白多少錢", "2990元",    "[主管]", ["2990"]),
    ("R4",  "退貨政策",     "7天內可以退貨",  "[主管]", ["7天", "退貨"]),
    ("R5",  "這個產品有嗎", "不行喔缺貨中",  "[主管]", ["缺貨"]),
]

print("=" * 60)
print("RAG 客服邏輯測試")
print("=" * 60)

passed = failed = 0
for case_id, question, sup, expected_action, expected_contains in CASES:
    print(f"\n── {case_id} ──")
    print(f"  Q: {question}")
    if sup: print(f"  主管: {sup}")

    result = full_flow(question, sup)
    print(f"  →: {result}")

    ok = result.startswith(expected_action)
    ok_contains = all(phrase in result for phrase in expected_contains)
    ok_final = ok and ok_contains

    for phrase in expected_contains:
        print(f"  {'✅' if phrase in result else '❌'} 含：「{phrase}」")

    if ok_final:
        print(f"  ✅ {case_id} 通過")
        passed += 1
    else:
        print(f"  ❌ {case_id} 失敗 (expected startswith={expected_action})")
        failed += 1

print(f"\n{'='*60}")
print(f"結果：✅ {passed}  ❌ {failed}")
print(f"{'='*60}")
