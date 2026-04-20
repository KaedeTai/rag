#!/usr/bin/env python3
"""compare_rag.py — 比較 vector 和 prompt 兩種 RAG 模式的輸出"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import rag

QUESTIONS = [
    "Total Swiss 客服電話多少？",
    "Total Swiss 創立年份？",
    "Fit Solution 多少錢？",
    "素食蛋白多少錢？",
    "退貨政策是什麼？",
    "細胞營養是什麼？",
    "比特幣價格？",
    "大陸買得到嗎？",
    "可以退貨嗎？",
    "產品有什麼？",
]

def clean(text):
    return text.strip()

print("=" * 80)
print("RAG 模式比較")
print("=" * 80)

for i, q in enumerate(QUESTIONS, 1):
    print(f"\n【{i}】 {q}")
    print("-" * 80)

    for method in ["vector", "prompt"]:
        r = rag.answer(q, method=method)
        ans = clean(r["answer"])
        src = r["sources"][0]["source"] if r["sources"] else "—"
        print(f"  [{method:6}] {ans[:120]}{'...' if len(ans)>120 else ''}")
        print(f"            src: {src}")

print("\n" + "=" * 80)
print(f"共 {len(QUESTIONS)} 題，兩種模式完成")
print("=" * 80)
