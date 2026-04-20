#!/usr/bin/env python3
"""測試 100 個客戶問題，找出回答錯誤"""
import sys, os, time
sys.path.insert(0, '/Users/apple/clawd-kaedebot/rag')
import rag, json

# 100 個測試問題（覆蓋各種主題）
QUESTIONS = [
    # === 公司基本資訊 === (1-10)
    "Total Swiss 是什麼公司？",
    "Total Swiss 創辦人是誰？",
    "Total Swiss 成立多久了？",
    "Total Swiss 總部在哪裡？",
    "八馬國際事業是做什麼的？",
    "Total Swiss 是直銷公司嗎？",
    "王文欽博士是誰？",
    "Total Swiss 在台灣有幾年歷史？",
    "Total Swiss 的產品產地是哪裡？",
    "Total Swiss 屬於哪個集團？",

    # === 全球客服/聯絡資訊 === (11-20)
    "Total Swiss 客服電話是多少？",
    "怎麼聯繫 Total Swiss？",
    "Total Swiss 的 Email 是什麼？",
    "全球客服中心電話？",
    "客服中心上班時間？",
    "可以寫信問問題嗎？",
    "台灣的客服電話是什麼？",
    "gsc@tsmail.com.tw 是做什麼的？",
    "有 LINE 客服嗎？",
    "Total Swiss 在台灣有辦公室嗎？",

    # === 縣市據點/聯絡資訊 === (21-35)
    "Total Swiss 台北怎麼去？",
    "Total Swiss 台中辦公室在哪裡？",
    "Total Swiss 高雄的地址？",
    "Total Swiss 台南有服務據點嗎？",
    "Total Swiss 桃園的聯絡方式？",
    "Total Swiss 新竹有辦公室嗎？",
    "Total Swiss 宜蘭有服務處嗎？",
    "Total Swiss 花蓮聯絡方式？",
    "Total Swiss 台東有據點嗎？",
    "Total Swiss 彰化有服務嗎？",
    "Total Swiss 雲林有辦公室嗎？",
    "Total Swiss 南投的地址？",
    "Total Swiss 嘉義怎麼聯繫？",
    "Total Swiss 屏東有服務據點嗎？",
    "Total Swiss 基隆的聯絡方式？",

    # === 產品種類 === (36-45)
    "Total Swiss 有哪些產品？",
    "Fit Solution 是什麼？",
    "Time 系列是做什麼的？",
    "Air 產品有哪些？",
    "Water 系列是什麼？",
    "細胞營養套組包含什麼？",
    "Total Swiss 有哪些保健食品？",
    "空氣淨化產品有哪些？",
    "水氧機有什麼功能？",
    "太空水機是做什麼的？",

    # === 購買與會員 === (46-60)
    "如何購買 Total Swiss 產品？",
    "怎麼成為會員？",
    "Total Swiss 是直銷嗎？",
    "會員有什麼福利？",
    "直購價是多少？",
    "Fit Solution 多少錢？",
    "可以網購嗎？",
    "哪裡可以買到 Total Swiss？",
    "網路可以下單嗎？",
    "有經銷商嗎？",
    "新會員優惠有哪些？",
    "首購優惠是什麼？",
    "如何聯絡會員顧問？",
    "國外可以訂購嗎？",
    "有經銷據點嗎？",

    # === 產品功效/成分 === (61-70)
    "Fit Solution 有什麼功效？",
    "產品有科學依據嗎？",
    "細胞營養是什麼原理？",
    "Total Swiss 有臨床實驗嗎？",
    "產品有認證嗎？",
    "成分安全嗎？",
    "有不含添加物的產品嗎？",
    "素食者可以吃嗎？",
    "過敏體質可以吃嗎？",
    "孕婦可以吃嗎？",

    # === 物流/退換 === (71-80)
    "多久可以收到貨？",
    "運費多少錢？",
    "可以退貨嗎？",
    "退貨政策是什麼？",
    "國外寄送要多久？",
    "有低溫配送嗎？",
    "包裝怎麼樣？",
    "可以超商取貨嗎？",
    "線上刷卡可以吗？",
    "有哪些付款方式？",

    # === 產品使用/劑量 === (81-88)
    "Fit Solution 怎麼吃？",
    "每日建議劑量？",
    "飯前還是飯後吃？",
    "可以跟藥物一起吃嗎？",
    "水氧機怎麼使用？",
    "空氣淨化機多久換濾網？",
    "太空水機怎麼安裝？",
    "產品保存期限多久？",

    # === 投訴/售後 === (89-95)
    "產品有問題怎麼辦？",
    "如何申請售後服務？",
    "會員申訴管道？",
    "產品壞了可以維修嗎？",
    "有保固嗎？",
    "保固期多久？",
    "維修中心在哪裡？",

    # === 其他常見問題 === (96-100)
    "Total Swiss 有沒有 app？",
    "可以訂閱嗎？",
    "有推薦碼優惠嗎？",
    "如何知道最新優惠？",
    "Total Swiss 在中國有賣嗎？",
]

def test_question(q, i):
    """測試單一問題"""
    t = time.time()
    try:
        result = rag.answer(q, method="prompt")
        elapsed = time.time() - t
        ans = result.get("answer", "")
        handover = result.get("handover", False)
        # 基本判斷答案品質
        handover_flag = "⚠️ HANDOVER" if handover else ""
        short_flag = "📏 SHORT" if len(ans) < 30 else ""
        return {
            "id": i,
            "question": q,
            "answer": ans,
            "elapsed": round(elapsed, 1),
            "handover": handover,
            "flags": f"{handover_flag} {short_flag}".strip()
        }
    except Exception as e:
        return {
            "id": i,
            "question": q,
            "answer": f"ERROR: {e}",
            "elapsed": 0,
            "handover": None,
            "flags": "❌ ERROR"
        }

def main():
    print(f"測試 {len(QUESTIONS)} 個問題...\n")
    results = []
    for i, q in enumerate(QUESTIONS):
        r = test_question(q, i+1)
        results.append(r)
        status = r['flags'] if r['flags'] else "✅"
        print(f"[{i+1:3d}/{len(QUESTIONS)}] {status:20s} {q[:30]}")
        time.sleep(0.5)  # 避免太密集

    # 統計
    print("\n" + "="*60)
    handovers = [r for r in results if r['handover']]
    errors = [r for r in results if 'ERROR' in r['flags']]
    short_ans = [r for r in results if 'SHORT' in r['flags']]
    print(f"總問題數: {len(results)}")
    print(f"⚠️ 轉主管: {len(handovers)} ({len(handovers)*100//len(results)}%)")
    print(f"❌ 錯誤: {len(errors)}")
    print(f"📏 答案過短: {len(short_ans)}")

    # 寫詳細報告
    report_path = "/Users/apple/clawd-kaedebot/rag/test_report_100.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n詳細報告: {report_path}")

    # 顯示有問題的
    if handovers:
        print(f"\n=== ⚠️ 轉主管的問題 ({len(handovers)}) ===")
        for r in handovers:
            print(f"  Q{r['id']:3d}: {r['question']}")
            print(f"       A: {r['answer'][:80]}...")
            print()

    if errors:
        print(f"\n=== ❌ 錯誤的問題 ({len(errors)}) ===")
        for r in errors:
            print(f"  Q{r['id']:3d}: {r['question']} → {r['answer'][:60]}")

if __name__ == "__main__":
    main()
