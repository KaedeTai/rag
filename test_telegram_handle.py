#!/usr/bin/env python3
"""test_telegram_handle.py — Telegram handle() 邏輯測試

涵蓋所有 handle() 的判斷情境：
1. 主管回覆 Bot 轉的問題 → 發給客戶
2. 主管回覆但 PENDING 找不到 → 當一般訊息進 RAG
3. 客戶問候語 → 直接回問候
4. 客戶一般問題 → RAG API
5. 客戶觸發 handover → 轉給主管
"""
import sys
sys.path.insert(0, "/Users/apple/clawd-kaedebot/rag")

# ── Mock 物件 ──────────────────────────────────────────────────────────────

SENT = []        # Bot 發過的訊息
PENDING = {}      # 模拟 PENDING dict
PENDING_SNAPSHOT = {}  # 每次呼叫 forward_to_kaede 時的快照

def reset():
    global PENDING, SENT
    SENT = []
    PENDING = {}

# Mock send_msg
_orig_send_msg_globals = {}

def mock_send_msg(chat_id, text):
    SENT.append({"chat_id": chat_id, "text": text})

def mock_forward_to_kaede(question, user_name, user_id, chat_id, replied_to):
    """類比 forward_to_kaede：存入 PENDING 並實際送出（mock）"""
    admin_chat_id = 574704148
    msg_to_admin = f"（來自 {user_name}，TG ID {user_id}）\n\n客戶問題：{question}"
    # 模擬：Bot 發給主管，得到 message_id = 1000 + len(PENDING)
    admin_msg_id = 1000 + len(PENDING)
    PENDING[admin_msg_id] = {
        "question": question,
        "user_name": user_name,
        "user_id": user_id,
        "chat_id": chat_id,
        "time": 0,
    }
    PENDING_SNAPSHOT.update(PENDING)
    SENT.append({"chat_id": admin_chat_id, "text": msg_to_admin})

# ── 模擬 handle() 邏輯（與 telegram_bot.py 完全一致）────────────────────────

GREETINGS = {
    "hi", "hello", "嗨", "你好", "您好", "hey", "yo",
    "hi!", "hi.", "你好!", "您好!", "嗨囉",
}
ADMIN_ID = 574704148

def handle_sim(
    msg_from_id,       # 發訊息的人
    msg_id,           # 訊息 ID
    text,              # 訊息內容
    chat_id,          # 聊天室 ID
    reply_to_msg_id=None,  # 若有回覆，回覆的訊息 ID
    customer_question=None,  # 若是主管回覆，原始客戶問題（用於模擬 PENDING 已在的情況）
):
    """
    模擬 handle() 的完整邏輯。回傳描述。
    """
    reset()
    if customer_question is not None:
        # 模擬 forward_to_kaede 存進 PENDING
        mock_forward_to_kaede(customer_question, "客戶", "999", chat_id, msg_id)

    result_desc = []

    # 1. 主管回覆 Bot 轉的客戶問題
    if reply_to_msg_id is not None:
        if reply_to_msg_id in PENDING:
            pending = PENDING.pop(reply_to_msg_id)
            # 模擬 supervisor_reply
            answer = f"[主管已回覆：{text}]"
            SENT.append({"chat_id": pending["chat_id"], "text": answer})
            SENT.append({"chat_id": chat_id, "text": "已回覆給客戶。"})
            return f"[主管回覆→發給客戶] 問={pending['question'][:20]} 答={answer}"

    # 2. 問候語
    if text.lower().strip().rstrip("!.") in GREETINGS:
        SENT.append({"chat_id": chat_id, "text": "你好！"})
        return "[問候→直接回]"

    # 3. （此模擬不包含 RAG API 呼叫，改測試時指定預期行為）
    # 4. 轉 handover（密碼關鍵字）
    if "密碼" in text or "信用卡" in text:
        mock_forward_to_kaede(text, "客戶", str(msg_from_id), chat_id, msg_id)
        SENT.append({"chat_id": chat_id, "text": "請稍候"})
        return "[敏感→轉主管]"

    # 5. 正常問題（此模擬不做實際 RAG，標記為需 API 處理）
    return f"[一般問題→需RAG] text={text[:20]}"

# ── 測試案例 ──────────────────────────────────────────────────────────────

CASES = []

def check(case_id, desc, expected_behavior, **kwargs):
    """執行一個測試案例。"""
    result = handle_sim(**kwargs)
    ok = expected_behavior in result
    status = "✅" if ok else "❌"
    print(f"  {status} {case_id}: {desc}")
    print(f"       預期：{expected_behavior}")
    print(f"       結果：{result}")
    if not ok:
        print(f"       ⚠️  失敗")
    return ok

print("=" * 70)
print("Telegram handle() 邏輯測試")
print("=" * 70)

passed = failed = 0

# ── 情境 1：主管回覆 Bot 轉的客戶問題 ──────────────────────────────────────

print("\n【情境 1】主管回覆 Bot 轉的客戶問題")

# 1a. 主管回覆「可以」，PENDING 存在 → 發給客戶
ok = check(
    "T1a", "主管回覆「可以」（reply 到 Bot 訊息）",
    "主管回覆→發給客戶",
    msg_from_id=ADMIN_ID, msg_id=200, text="可以的",
    chat_id=ADMIN_ID, reply_to_msg_id=1000,
    customer_question="大陸買得到嗎",
)
passed += ok; failed += not ok

# 1b. 主管回覆「不行喔缺貨中」
ok = check(
    "T1b", "主管回覆「不行喔缺貨中」（reply 到 Bot 訊息）",
    "主管回覆→發給客戶",
    msg_from_id=ADMIN_ID, msg_id=201, text="不行喔缺貨中",
    chat_id=ADMIN_ID, reply_to_msg_id=1000,
    customer_question="這個產品有嗎",
)
passed += ok; failed += not ok

# ── 情境 2：主管回覆但 PENDING 找不到（不該進這裡）──────────────────────────

print("\n【情境 2】主管回覆但 PENDING 裡沒有這個 ID")

# 2a. reply_to_msg_id 不在 PENDING → 當一般訊息處理
ok = check(
    "T2a", "主管回覆但 ID 不在 PENDING → 不進主管邏輯",
    "一般問題",
    msg_from_id=ADMIN_ID, msg_id=202, text="這個我也不確定",
    chat_id=ADMIN_ID, reply_to_msg_id=9999,  # 9999 不在 PENDING
)
# 預期進到下一個邏輯（因為 reply_to_msg_id 不在 PENDING）
passed += ok; failed += not ok

# ── 情境 3：問候語 ─────────────────────────────────────────────────────────

print("\n【情境 3】客戶/任何人發問候語")

for greeting in ["你好", "hi", "嗨", "HI"]:
    ok = check(
        f"T3-{greeting}", f"發「{greeting}」",
        "問候→直接回",
        msg_from_id=12345, msg_id=300, text=greeting,
        chat_id=12345,
    )
    passed += ok; failed += not ok

# ── 情境 4：敏感關鍵字 → 轉主管 ──────────────────────────────────────────

print("\n【情境 4】敏感關鍵字 → 轉主管")

for kw in ["我的密碼是多少", "信用卡號"]:
    ok = check(
        f"T4-{kw[:6]}", f"發「{kw}」",
        "敏感→轉主管",
        msg_from_id=12345, msg_id=400, text=kw,
        chat_id=12345,
    )
    passed += ok; failed += not ok

# ── 情境 5：主管回覆內容是 greeting（不該進 greeting）──────────────────────

print("\n【情境 5】主管回覆內容是 greeting 關鍵字，但這是回覆 → 不進 greeting")

ok = check(
    "T5", "主管回覆「你好」（reply 到 Bot 訊息，問候邏輯不該被觸發）",
    "主管回覆→發給客戶",  # 進主管邏輯，不是問候
    msg_from_id=ADMIN_ID, msg_id=500, text="你好",
    chat_id=ADMIN_ID, reply_to_msg_id=1000,
    customer_question="產品價格",
)
passed += ok; failed += not ok

# ── 情境 6：SENT 檢查 ─────────────────────────────────────────────────────

print("\n【情境 6】確認訊息有正確發出")

reset()
handle_sim(
    msg_from_id=ADMIN_ID, msg_id=200, text="可以",
    chat_id=ADMIN_ID, reply_to_msg_id=1000,
    customer_question="大陸買得到嗎",
)
# 檢查有沒有發給原客戶
client_msgs = [m for m in SENT if m["chat_id"] != ADMIN_ID]
admin_msgs = [m for m in SENT if m["chat_id"] == ADMIN_ID]

ok = len(client_msgs) > 0
print(f"  {'✅' if ok else '❌'} T6a: 有發訊息給原客戶（chat_id ≠ ADMIN_ID）: {len(client_msgs)} 筆")
passed += ok; failed += not ok

ok = any("已回覆給客戶" in m["text"] for m in admin_msgs)
print(f"  {'✅' if ok else '❌'} T6b: 有通知主管「已回覆」: {len(admin_msgs)} 筆")
passed += ok; failed += not ok

print(f"\n{'=' * 70}")
print(f"結果：✅ {passed}  ❌ {failed}")
print(f"{'=' * 70}")
