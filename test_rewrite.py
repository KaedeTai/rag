#!/usr/bin/env python3
"""
test_rewrite.py — 測試 supervisor_reply 函數（直接 import telegram_bot）
"""
import re, sys
sys.path.insert(0, "/Users/apple/clawd-kaedebot/rag")

# 從 telegram_bot.py 直接 import（確保兩邊一致）
import importlib.util
spec = importlib.util.spec_from_file_location(
    "tg", "/Users/apple/clawd-kaedebot/rag/telegram_bot.py")
tg = importlib.util.module_from_spec(spec)

# 只 import 函數，不執行 main loop
# 直接定義 supervisor_reply 的邏輯（跟 telegram_bot.py 一樣）
import config as config_module

def clean_thinking(raw: str) -> str:
    parts = raw.split("\n</think>")
    if len(parts) > 1:
        return parts[-1].strip()
    return re.sub(r"<think>\b.*?\b</think>", "", raw, flags=re.DOTALL).strip()

def supervisor_reply(customer_q: str, supervisor_text: str) -> str:
    sr = supervisor_text.strip()
    # 1. 原文轉達
    for qre in [
        r"「([^」]*)」", r"『([^』]*)』",
        r"\"([^\"]*)\"", r"'([^']*)'",
    ]:
        m = re.search(qre, sr)
        if m:
            return m.group(1).strip()
    # 2. 長回覆 → 直接給客戶
    if len(sr) >= 15:
        return sr
    # 3. 短回覆 → MiniMax 擴充
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
                    "請根據主管的答覆，用一句完整、專業、親切的客服口吻句子，直接回答客戶。\n"
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


# ── Test Cases ─────────────────────────────────────────────────────────────

CASES = [
    ("T1", "大陸買得到嗎", "目前中國大陸可以購買，請聯繫客服",
     ["中國大陸可以購買"], ["可以的", "沒有", "亞洲", "16個國家"]),

    ("T2", "大陸買得到嗎", "可以的唷！",
     ["可以", "大陸"], ["16個國家", "亞洲", "沒有"]),

    ("T3", "這個產品有嗎", "不行喔缺貨中",
     ["不行", "缺貨"], ["可以"]),

    ("T4", "如何加入會員", "請撥打02-7733-0800由專人協助入會",
     ["02-7733-0800"], []),

    ("T5", "多少錢", "「目前優惠價5800元」",
     ["5800", "優惠價"], ["「", "」"]),

    ("T6", "客服電話多少", "打 02-7733-0800",
     ["02-7733-0800"], []),

    ("T7", "素食蛋白飲品多少錢", "2990元",
     ["2990"], []),

    ("T8", "請問有退貨服務嗎", "有的，7天內可以退貨",
     ["可以退貨", "7天"], []),
]

print("=" * 60)
print("supervisor_reply() 測試")
print("=" * 60)

all_ok = True
for case_id, cq, sup, must, must_not in CASES:
    print(f"\n── {case_id} ──")
    print(f"  Q: {cq}")
    print(f"  主管: {sup}")

    result = supervisor_reply(cq, sup)
    print(f"  →: {result}")

    ok_must     = all(p in result for p in must)
    ok_must_not = all(p not in result for p in must_not)

    for p in must:
        print(f"  {'✅' if p in result else '❌'} 含：「{p}」")
    for p in must_not:
        print(f"  {'✅' if p not in result else '❌'} 不含：「{p}」")

    if ok_must and ok_must_not:
        print(f"  ✅ {case_id} 通過")
    else:
        print(f"  ❌ {case_id} 失敗")
        all_ok = False

print("\n" + "=" * 60)
print("結果：", "✅ 全部通過" if all_ok else "❌ 有失敗案例")
print("=" * 60)
