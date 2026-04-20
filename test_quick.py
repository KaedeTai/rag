#!/usr/bin/env python3
"""快速測試 20 個問題，先看問題再說"""
import sys, os, time, json
sys.path.insert(0, '/Users/apple/clawd-kaedebot/rag')
import rag

QUESTIONS = [
    # 縣市資訊（最關鍵）
    "Total Swiss 台北怎麼去？",
    "Total Swiss 台中辦公室在哪裡？",
    "Total Swiss 高雄的地址？",
    "Total Swiss 台南有服務據點嗎？",
    "Total Swiss 桃園的聯絡方式？",
    # 基本問題
    "Total Swiss 客服電話是多少？",
    "Fit Solution 是什麼？",
    "如何購買 Total Swiss 產品？",
    "Total Swiss 是直銷嗎？",
    "怎麼成為會員？",
    # 公司
    "Total Swiss 創辦人是誰？",
    "Total Swiss 總部在哪裡？",
    "八馬國際事業是做什麼的？",
    # 產品
    "有哪些保健食品？",
    "空氣淨化產品有哪些？",
    "水氧機有什麼功能？",
    # 購買
    "直購價是多少？",
    "可以網購嗎？",
    "多久可以收到貨？",
    "有保固嗎？",
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
            short = len(ans) < 30
            unknown = any(k in ans for k in ["沒有這個資料", "知識庫中沒有", "無法確認", "不清楚", "不知道"])
            flag = ""
            if handover: flag += "⚠️ "
            if short: flag += "📏 "
            if unknown: flag += "❓ "
            print(f"[{i+1:2d}/20] {flag or '✅'} {q[:25]:25s} | {ans[:50]}... ({elapsed:.0f}s)")
            results.append({"q": q, "a": ans, "handover": handover, "unknown": unknown, "short": short, "elapsed": elapsed})
        except Exception as e:
            print(f"[{i+1:2d}/20] ❌ {q[:25]} → ERROR: {e}")
            results.append({"q": q, "a": str(e), "error": True})
        time.sleep(0.3)

    print("\n=== 統計 ===")
    print(f"總問題: {len(results)}")
    print(f"轉主管: {sum(1 for r in results if r.get('handover'))}")
    print(f"答案含糊: {sum(1 for r in results if r.get('unknown'))}")
    print(f"答案過短: {sum(1 for r in results if r.get('short'))}")
    print(f"錯誤: {sum(1 for r in results if r.get('error'))}")

    with open("/Users/apple/clawd-kaedebot/rag/test_quick_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n已存: test_quick_results.json")

if __name__ == "__main__":
    main()
