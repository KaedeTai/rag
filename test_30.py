#!/usr/bin/env python3
"""測試 30 個核心問題"""
import sys, time, json
sys.path.insert(0, '/Users/apple/clawd-kaedebot/rag')
import rag

QUESTIONS = [
    # 公司基本
    "Total Swiss 客服電話是多少？",
    "Total Swiss 創辦人是誰？",
    "Total Swiss 總部在哪裡？",
    "八馬國際是做什麼的？",
    "Total Swiss 是直銷嗎？",
    # 據點（縣市）
    "台北公司地址？",
    "台中營運中心在哪裡？",
    "高雄公司地址？",
    "台南服務據點在哪裡？",
    "新竹服務據點在哪裡？",
    "桃園公司地址？",
    # 產品
    "Fit Solution 是什麼？",
    "有哪些產品種類？",
    "細胞營養套組多少錢？",
    "空氣淨化產品有哪些？",
    # 購買/會員
    "如何購買 Total Swiss 產品？",
    "怎麼成為會員？",
    "可以網購嗎？",
    "直購價是多少？",
    # 物流
    "多久可以收到貨？",
    "運費多少錢？",
    "可以超商取貨嗎？",
    "國外可以訂購嗎？",
    # 付款
    "有哪些付款方式？",
    "可以分期付款嗎？",
    # 保固/售後
    "有保固嗎？",
    "保固期多久？",
    "產品故障怎麼辦？",
    "維修中心在哪裡？",
    # 退換貨
    "可以退貨嗎？",
    "退貨要多久完成退款？",
]

def main():
    results = []
    for i, q in enumerate(QUESTIONS):
        t = time.time()
        try:
            result = rag.answer(q, method="prompt")
            elapsed = time.time() - t
            ans = result.get("answer", "")
            handover = result.get("handover", False)
            unknown = any(k in ans for k in ["沒有這個資料", "知識庫中沒有", "不清楚", "不知道", "目前沒有這個資料"])
            flag = ""
            if handover: flag += "⚠️ "
            if unknown: flag += "❓ "
            print(f"[{i+1:2d}/30] {flag or '✅ ':6s} {q[:22]:22s} | {ans[:45]}... ({elapsed:.0f}s)")
            results.append({"q": q, "a": ans, "elapsed": elapsed, "handover": handover, "unknown": unknown})
        except Exception as e:
            print(f"[{i+1:2d}/30] ❌ ERROR: {q[:22]} → {e}")
            results.append({"q": q, "error": str(e)})
        time.sleep(0.5)

    print("\n=== 統計 ===")
    handover_count = sum(1 for r in results if r.get("handover"))
    unknown_count = sum(1 for r in results if r.get("unknown"))
    print(f"總問題: {len(results)} | ⚠️ 轉主管: {handover_count} | ❓ 答案含糊: {unknown_count}")

    # 顯示有問題的
    problems = [r for r in results if r.get("handover") or r.get("unknown") or r.get("error")]
    if problems:
        print(f"\n=== 有問題的答案 ({len(problems)}) ===")
        for r in problems:
            print(f"  Q: {r['q']}")
            print(f"  A: {r.get('a', r.get('error',''))[:80]}")
            print()

    with open("/Users/apple/clawd-kaedebot/rag/test_30_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
