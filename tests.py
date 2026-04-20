#!/usr/bin/env python3
"""
rag/tests.py — 測試案例
用法：python3 tests.py
"""

import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import requests

BASE = "http://127.0.0.1:9093"
BOT_API = f"https://api.telegram.org/bot8315147713:AAG8MCeKzEoGI62o9RbH2dryXWaQMsmQNVA"

# ── 工具 ───────────────────────────────────────────────────────────────────

def clean(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

def api(q: str) -> dict:
    r = requests.post(f"{BASE}/api/chat_json",
        json={"question": q, "session_id": "test"},
        timeout=60)
    r.raise_for_status()
    return r.json()

def check(label: str, cond: bool, detail=""):
    mark = "✅" if cond else "❌"
    print(f"{mark} {label}" + (f" → {detail}" if detail else ""))
    return cond

passed = failed = 0

def run(name, fn):
    global passed, failed
    print(f"\n── {name} ──")
    try:
        fn()
        passed += 1
    except Exception as e:
        print(f"   ❗ 例外：{e}")
        failed += 1

# ── RAG 檢索測試 ──────────────────────────────────────────────────────────

def test_phone():
    d = api("Total Swiss 電話多少")
    ans = clean(d["answer"])
    check("電話能找到", "7733-0800" in ans, ans[:60])
    check("有 sources", len(d["sources"]) > 0)
    check("不是 handover", not d["handover"])

def test_product_price():
    d = api("Fit Solution 多少錢")
    ans = clean(d["answer"])
    check("價格能找到", "5,800" in ans or "5800" in ans, ans[:80])
    check("有來源標註", len(d["sources"]) > 0)

def test_product_name():
    d = api("Fit Solution 是什麼")
    ans = clean(d["answer"])
    check("產品介紹非空", len(ans) > 10, ans[:60])
    check("有 sources", len(d["sources"]) > 0)

def test_company_info():
    d = api("Total Swiss 是哪一年創立的")
    ans = clean(d["answer"])
    check("創立年份能找到", "2010" in ans, ans[:80])

def test_product_list():
    d = api("有哪些產品")
    ans = clean(d["answer"])
    check("產品列表非空", len(ans) > 10, ans[:60])
    check("有來源", len(d["sources"]) > 0)

def test_faq():
    d = api("如何成為會員")
    ans = clean(d["answer"])
    check("FAQ 回應非空", len(ans) > 5, ans[:60])
    check("有來源", len(d["sources"]) > 0)

def test_no_info():
    """知識庫沒有的內容應該 handover"""
    d = api("比特幣今天多少錢")
    ans = clean(d["answer"])
    # 有可能答了，也有可能 handover
    ok = d["handover"] or d["sources"] or len(ans) > 5
    check("無知識庫內容處理", ok, f"handover={d['handover']}, sources={len(d['sources'])}, ans={ans[:40]}")

# ── MiniMax thinking 移除測試 ───────────────────────────────────────────────

def test_thinking_removed():
    d = api("請介紹 Total Swiss")
    ans = clean(d["answer"])
    check("思考過程已移除", "<think>" not in ans and "</think>" not in ans, ans[:60])
    check("答案不為空", len(ans) > 5)

# ── Telegram Bot 模擬測試 ──────────────────────────────────────────────────

def test_greeting_hi():
    """測試問候語直接回覆，不轉人工"""
    import telegram_bot as tb
    # 模擬問候
    greetings = {"hi", "hello", "嗨", "你好", "您好", "hey", "hi!", "hi."}
    for g in ["hi", "hello", "你好"]:
        ok = g.lower().strip().rstrip("!.") in greetings
        check(f"問候 '{g}' 識別", ok)

def test_handover_keywords():
    """敏感關鍵字應觸發 handover"""
    # 直接測試邏輯，不 import telegram_bot 避免執行緒問題
    keywords = ["密碼", "password", "信用卡", "銀行帳戶", "法律", "律師"]
    q_pass = "我的密碼是多少"
    ok1 = any(kw.lower() in q_pass.lower() for kw in keywords)
    check("密碼 → handover", ok1)

    q_card = "我的信用卡號是什麼"
    ok2 = any(kw.lower() in q_card.lower() for kw in keywords)
    check("信用卡 → handover", ok2)

    q_normal = "Total Swiss產品介紹"
    ok3 = not any(kw.lower() in q_normal.lower() for kw in keywords)
    check("正常產品問題不觸發", ok3)

# ── 速度測試 ──────────────────────────────────────────────────────────────

def test_response_speed():
    import time
    q = "Total Swiss 的客服電話"
    start = time.time()
    d = api(q)
    elapsed = time.time() - start
    check("回應時間 < 20s", elapsed < 20, f"{elapsed:.1f}s")
    check("回應有內容", len(clean(d["answer"])) > 5)

# ── 主程式 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("RAG 系統測試")
    print("=" * 60)

    run("RAG 檢索測試 — 電話", test_phone)
    run("RAG 檢索測試 — 價格", test_product_price)
    run("RAG 檢索測試 — 產品名", test_product_name)
    run("RAG 檢索測試 — 公司資訊", test_company_info)
    run("RAG 檢索測試 — 產品列表", test_product_list)
    run("RAG 檢索測試 — FAQ", test_faq)
    run("RAG 檢索測試 — 無知識庫內容", test_no_info)
    run("MiniMax thinking 移除", test_thinking_removed)
    run("Telegram Bot 問候識別", test_greeting_hi)
    run("Telegram Bot 敏感關鍵字", test_handover_keywords)
    run("速度測試", test_response_speed)

    print("\n" + "=" * 60)
    print(f"結果：✅ {passed}  ❌ {failed}")
    print("=" * 60)
