#!/usr/bin/env python3
"""
test_full_flow.py — RAG 客服完整流程測試（不需 Telegram）
"""
import sys, os, re
sys.path.insert(0, "/Users/apple/clawd-kaedebot/rag")
import config as config_module

# ══════════════════════════════════════════════════════════════════
# 從 telegram_bot.py 來的關鍵函數
# ══════════════════════════════════════════════════════════════════

def clean_thinking(raw: str) -> str:
    import re
    parts = re.split(r"itz", raw, flags=re.IGNORECASE)
    if len(parts) > 1:
        return parts[-1].strip()
    return re.sub(r"<think>\b.*?\b</think>", "", raw, flags=re.DOTALL).strip()

def supervisor_reply(customer_q: str, supervisor_text: str) -> str:
    """主管回覆 → 給客戶的答案。"""
    sr = supervisor_text.strip()
    for qre in [
        r"「([^」]*)」", r"『([^』]*)』",
        r"\"([^\"]*)\"", r"'([^']*)'",
    ]:
        m = re.search(qre, sr)
        if m:
            return m.group(1).strip()

    if len(sr) >= 15:
        return sr

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config_module.MINIMAX_API_KEY,
            base_url=config_module.MINIMAX_BASE_URL,
        )
        resp = client.chat.completions.create(
            model=config_module.LLM_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "客戶問：「" + customer_q + "」\n"
                    "主管答：「" + sr + "」\n\n"
                    "請根據主管的答覆，用一句完整句子，直接回答客戶。\n"
                    "要求：只準確表達主管的意思，不添加任何新資訊。"
                ),
            }],
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        final = clean_thinking(raw)
        return final if final else sr
    except Exception as e:
        print(f"  [MiniMax error] {e}")
        return sr


def is_answer_sufficient(question: str, answer: str) -> bool:
    """用 MiniMax 判斷答案是否充分。回 True = 需要轉主管。"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config_module.MINIMAX_API_KEY,
            base_url=config_module.MINIMAX_BASE_URL,
        )
        resp = client.chat.completions.create(
            model=config_module.LLM_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "用戶問題：「" + question + "」\n"
                    "客服回答：「" + answer + "」\n\n"
                    "請問這個回答是否充分？\n"
                    "「是」= 充分，不需要轉主管。\n"
                    "「否」= 不充分、需要主管確認。\n"
                    "請只回答「是」或「否」。"
                ),
            }],
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        verdict = clean_thinking(raw).strip()
        return "否" in verdict
    except Exception as e:
        print(f"  [is_answer_sufficient error] {e}")
        return True


# ══════════════════════════════════════════════════════════════════
# Mock RAG API
# ══════════════════════════════════════════════════════════════════

KB = {
    "total swiss電話":   {"answer": "Total Swiss 客服電話是 02-7733-0800。",     "score": 0.85},
    "電話":               {"answer": "全球客服中心電話是 02-7733-0800。",           "score": 0.80},
    "創立":              {"answer": "Total Swiss 由王文欽博士於 2010 年在瑞士創立。", "score": 0.90},
    "fit solution多少錢": {"answer": "Fit Solution 細胞營養套組直購價 5,800 元。",   "score": 0.80},
    "fit solution 價格": {"answer": "Fit Solution 細胞營養套組 5,800 元。",        "score": 0.80},
    "旗艦產品":          {"answer": "Fit Solution 是 Total Swiss 的旗艦產品。",      "score": 0.75},
    "素食蛋白":          {"answer": "素食蛋白飲品 2,990 元。",                     "score": 0.78},
    "細胞營養":          {"answer": "細胞營養素是 Total Swiss 的核心概念。",       "score": 0.72},
}

GREETINGS = {"hi", "hello", "嗨", "你好", "您好", "hey", "yo"}


def rag_api(question: str) -> dict:
    """Mock RAG API 回傳。"""
    q = question.lower().strip()
    if q in GREETINGS or q.rstrip("!.") in GREETINGS:
        return {"answer": None}  # 問候

    for key, val in KB.items():
        if key in q:
            return {"answer": val["answer"], "score": val["score"]}

    # 知識庫沒有
    return {"answer": "目前沒有這個資料。", "score": 0.0}


# ══════════════════════════════════════════════════════════════════
# 完整流程
# ══════════════════════════════════════════════════════════════════

def full_flow(question: str) -> dict:
    """
    模擬 Bot 收到問題 → 回覆/轉主管。
    回傳 {"action": "answer"/"handover", "text": str, "reason": str}
    """
    q = question.lower().strip().rstrip("!.")
    if q in GREETINGS:
        return {"action": "answer", "text": "你好！有什麼關於 Total Swiss 的問題可以問我喔 😊", "reason": "問候"}

    rag = rag_api(question)
    answer = rag.get("answer")
    score = rag.get("score", 0.0)

    # 敏感關鍵字 → 轉
    if any(kw.lower() in question.lower() for kw in config_module.HUMAN_HANDOVER_KEYWORDS):
        return {"action": "handover", "text": "這個問題我需要確認一下，請稍候，我會通知專人回覆您。", "reason": "敏感關鍵字"}

    # 知識庫沒有（分數0） → 轉
    if score == 0.0:
        return {"action": "handover", "text": "這個問題我需要確認一下，請稍候，我會通知專人回覆您。", "reason": "知識庫無資料"}

    # 分數不夠 → 轉
    if score < 0.45:
        return {"action": "handover", "text": "這個問題我需要確認一下，請稍候，我會通知專人回覆您。", "reason": f"分數不足({score:.2f}<0.45)"}

    # MiniMax 判斷答案是否充分
    if is_answer_sufficient(question, answer):
        return {"action": "handover", "text": "這個問題我需要確認一下，請稍候，我會通知專人回覆您。", "reason": "答案不充分(MiniMax)"}

    return {"action": "answer", "text": answer, "reason": "直接回覆"}


# ══════════════════════════════════════════════════════════════════
# Test Cases
# ══════════════════════════════════════════════════════════════════

FLOW_CASES = [
    # id, question, expected_action, must_contain, must_NOT_contain
    ("F-G1", "你好",    "answer", ["你好"], []),
    ("F-G2", "hi",     "answer", ["你好"], []),
    ("F-G3", "嗨",     "answer", ["你好"], []),
    ("F-K1", "Total Swiss電話",  "answer", ["02-7733-0800"], ["請稍候"]),
    ("F-K2", "Total Swiss創立",  "answer", ["2010", "瑞士"], ["請稍候"]),
    ("F-K3", "Fit Solution多少錢", "answer", ["5,800", "元"], ["請稍候"]),
    ("F-K4", "素食蛋白多少錢",     "answer", ["2,990"], ["請稍候"]),
    ("F-H1", "大陸買得到嗎", "handover", ["請稍候"], []),
    ("F-H2", "比特幣價格",  "handover", ["請稍候"], []),
    ("F-S1", "我的密碼是多少", "handover", ["請稍候"], []),
    ("F-S2", "信用卡號",   "handover", ["請稍候"], []),
]

SUPERVISOR_CASES = [
    # id, question, supervisor_reply, must_contain, must_NOT_contain
    ("S-R1", "大陸買得到嗎", "可以的唷！",
     ["可以", "大陸"], ["16個", "亞洲", "請稍候"]),

    ("S-R2", "大陸買得到嗎", "「可以在大陸購買」",
     ["可以在大陸購買"], ["請稍候"]),

    ("S-R3", "Fit Solution多少錢", "5800元",
     ["5800", "元"], ["請稍候"]),

    ("S-R4", "退貨政策", "有的，7天內可以退貨",
     ["7天", "退貨"], []),

    ("S-R5", "客服電話", "打02-7733-0800",
     ["02-7733-0800"], ["請稍候"]),

    ("S-R6", "這個產品有嗎", "不行喔缺貨中",
     ["缺貨"], ["可以"]),

    ("S-R7", "你叫什麼名字", "我叫哆啦A夢",
     ["哆啦A夢"], []),
]

# ══════════════════════════════════════════════════════════════════
print("=" * 65)
print("RAG 客服完整流程測試")
print("=" * 65)

total_passed = total_failed = 0

# ── 主流程測試 ──────────────────────────────────────────────
print("\n【主流程測試】")
for case_id, question, expected_action, must, must_not in FLOW_CASES:
    print(f"\n── {case_id} ──")
    print(f"  Q: {question}")

    result = full_flow(question)
    print(f"  → {result['action']} | {result['reason']}")

    ok_action = result["action"] == expected_action
    if not ok_action:
        print(f"  ❌ action={result['action']} 預期={expected_action}")
        total_failed += 1
        continue

    if result["action"] == "answer":
        text = result["text"]
        ok_must     = all(p in text for p in must)
        ok_must_not = all(p not in text for p in must_not)
        for p in must:
            print(f"  {'✅' if p in text else '❌'} 含：「{p}」")
        for p in must_not:
            print(f"  {'✅' if p not in text else '❌'} 不含：「{p}」")
        if ok_must and ok_must_not:
            print(f"  ✅ {case_id} 通過")
            total_passed += 1
        else:
            print(f"  ❌ {case_id} 失敗")
            total_failed += 1
    else:
        # handover
        ok_must_not = all(p not in result["text"] for p in must_not)
        if ok_must_not:
            print(f"  ✅ {case_id} 通過")
            total_passed += 1
        else:
            print(f"  ❌ {case_id} 失敗")
            total_failed += 1

# ── 主管回覆測試 ──────────────────────────────────────────
print("\n\n【主管回覆測試】")
for case_id, question, sup_reply, must, must_not in SUPERVISOR_CASES:
    print(f"\n── {case_id} ──")
    print(f"  Q: {question}")
    print(f"  主管: {sup_reply}")

    result = supervisor_reply(question, sup_reply)
    print(f"  →: {result}")

    ok_must     = all(p in result for p in must)
    ok_must_not = all(p not in result for p in must_not)
    for p in must:
        print(f"  {'✅' if p in result else '❌'} 含：「{p}」")
    for p in must_not:
        print(f"  {'✅' if p not in result else '❌'} 不含：「{p}」")
    if ok_must and ok_must_not:
        print(f"  ✅ {case_id} 通過")
        total_passed += 1
    else:
        print(f"  ❌ {case_id} 失敗")
        total_failed += 1

print("\n" + "=" * 65)
print(f"結果：✅ {total_passed}  ❌ {total_failed}")
print("=" * 65)
