"""
rag/rag.py
=========
Total Swiss 智能客服系統 - RAG 核心引擎

職責
----
1. 載入知識庫（Markdown 檔案）
2. 網路搜尋（ Brave API → DuckDuckGo HTML fallback ）
3. 回答生成（Prompt Mode，預設；Vector Mode，需 Qdrant）
4. 轉主管判斷（Content-aware + 分數閾值）
5. 雙模式並行（Vector + Prompt，同時跑取較優者）

依賴
----
- Python 3.10+
- 第三方套件：requests, sentence-transformers, qdrant-client, anthropic, openai
- 組態：config.py（API key、模式設定）

使用範例
--------
    import rag
    result = rag.answer("高雄公司地址？", method="prompt")
    # result = {"answer": "...", "handover": False, "sources": [...], "dual": {...}}
"""

# ─── 標準 library ────────────────────────────────────────────────────────────
import os
import re
import uuid
import sqlite3
import threading
from typing import Optional

# ─── 第三方套件 ─────────────────────────────────────────────────────────────
import requests

# ─── 本地模組 ────────────────────────────────────────────────────────────────
import config

# ════════════════════════════════════════════════════════════════════════════
# 第一層：網路搜尋（ Web Search ）
# ════════════════════════════════════════════════════════════════════════════

def web_search(query: str, num: int = 5) -> str:
    """
    搜尋網路並回傳格式化結果字串。

    搜尋策略
    --------
    1. Brave Search API（優先，需 BRAVE_API_KEY）
    2. DuckDuckGo HTML（備援，不需要 API key）

    參數
    ----
    query : 搜尋關鍵字
    num   : 回傳結果數量（預設 5）

    回傳
    ----
    str : 格式化後的搜尋結果，無結果時回傳空字串 ""
    """
    # ── 策略一：Brave Search API ──────────────────────────────────────────
    brave_key = getattr(config, "BRAVE_API_KEY", None) or os.getenv("BRAVE_API_KEY", "")
    brave_url = getattr(config, "BRAVE_SEARCH_URL", None) or \
        "https://api.search.brave.com/res/v1/web/search"

    if brave_key:
        try:
            headers = {
                "X-Subscription-Token": brave_key,
                "Accept": "application/json",
            }
            resp = requests.get(
                brave_url,
                headers=headers,
                params={"q": query, "count": num},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if results:
                    lines = ["【網路搜尋結果】"]
                    for res in results[:num]:
                        lines.append(f"- {res.get('title', '')}")
                        lines.append(f"  {res.get('description', '')}")
                        lines.append(f"  來源：{res.get('url', '')}")
                    return "\n".join(lines)
        except Exception as e:
            print(f"[WebSearch] Brave API error: {e}")

    # ── 策略二：DuckDuckGo HTML fallback ─────────────────────────────────
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""

        # 解析 DuckDuckGo HTML 中的搜尋結果
        raw_results = re.findall(
            r'<a class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
            r'.*?'
            r'<a class="result__snippet"[^>]*>([^<]+)</a>',
            resp.text,
            re.DOTALL,
        )
        if not raw_results:
            return ""

        def _clean(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s).strip()

        lines = ["【網路搜尋結果】"]
        for url, title, snippet in raw_results[:num]:
            lines.append(f"- {_clean(title)}")
            lines.append(f"  {_clean(snippet)}")
            lines.append(f"  來源：{url}")
        return "\n".join(lines)

    except Exception as e:
        print(f"[WebSearch] DuckDuckGo error: {e}")
        return ""


# ════════════════════════════════════════════════════════════════════════════
# 第二層：知識庫（ Prompt Mode ）
# ════════════════════════════════════════════════════════════════════════════

# 知識庫快取（程序生命週期內有效）
_kb_cache: Optional[list[dict]] = None


def load_kb_text() -> list[dict]:
    """
    讀取 data/ 目錄下所有 .md 檔案，回傳格式：
    [{"source": "filename.md", "content": "...", "content_hash": "..."}, ...]

    注意：結果會被快取（_kb_cache），直到程序重啟才會重新讀取磁碟。
    如需強制重載，請修改 _kb_cache = None。
    """
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache

    kb_dir = os.path.join(os.path.dirname(__file__), "data")
    docs = []
    for fname in sorted(os.listdir(kb_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(kb_dir, fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            docs.append({"source": fname, "content": content})
    _kb_cache = docs
    return docs


def _build_rag_prompt(question: str, kb_block: str, web_block: str = "") -> str:
    """
    組裝 RAG prompt 字串。

    參數
    ----
    question : 用戶問題
    kb_block : 知識庫內容（已格式化為單一字串）
    web_block: 網路搜尋結果（可為空）

    Prompt 設計原則
    ---------------
    - 明確告知「知識庫為主、網路為輔」
    - 不知道時引导 LLM 說「請聯繫全球客服中心」
    - 不透露 chunk、source file 等底層實作細節
    """
    web_section = (f"\n\n{web_block}") if web_block else ""
    return (
        "你是一個 Total Swiss 公司內部智能客服，根據以下知識庫及網路搜尋結果回答問題。\n"
        "如果知識庫和網路都沒有相關資訊，請說「目前沒有這個資料，請聯繫全球客服中心 02-7733-0800」。\n"
        "回答時請直接針對問題，不需要提及知識庫或資料來源。\n\n"
        "===\n"
        f"{kb_block}{web_section}\n"
        "===\n\n"
        f"用戶問題：{question}\n"
        "回答："
    )


def answer_by_prompt(question: str, web_results: str = "") -> dict:
    """
    Prompt Mode 回答：將整份知識庫（+ 網路結果）塞进 LLM prompt。

    參數
    ----
    question   : 用戶問題
    web_results: 網路搜尋結果字串（可為 ""）

    回傳
    ----
    {
        "answer"        : str,   # LLM 回覆
        "sources"       : list,  # [{"source": "...", "score": 1.0}, ...]
        "handover"      : bool,  # 固定 False（Prompt Mode 不自己做 handover 判斷）
        "prompt_thinking": str,  # LLM thinking（可能為空）
    }
    """
    docs = load_kb_text()

    # 將 KB 組裝成單一文字區塊
    kb_lines = []
    for d in docs:
        kb_lines.append(f"【{d['source']}】")
        kb_lines.append(d["content"])
    kb_block = "\n\n".join(kb_lines)

    prompt = _build_rag_prompt(question, kb_block, web_results)
    result = ask_llm(prompt) or {}

    answer_text = result.get("answer", "").strip()
    if not answer_text:
        answer_text = (
            "抱歉，系統暫時無法處理您的問題，"
            "請稍後再試或聯繫全球客服中心 02-7733-0800。"
        )

    return {
        "answer": answer_text,
        "sources": [{"source": d["source"], "score": 1.0} for d in docs],
        "handover": False,
        "prompt_thinking": result.get("thinking", ""),
    }


# ════════════════════════════════════════════════════════════════════════════
# 第三層：向量檢索（ Vector Mode ）
# ════════════════════════════════════════════════════════════════════════════

# Sentence-Transformer 模型（程序起動後懶載，僅 Vector Mode 使用）
_st_model: Optional[object] = None


def _get_embed_model():
    """
    懶載 sentence-transformers 模型。
    模型：all-MiniLM-L6-v2（384 維，无需 GPU）
    """
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        print("[Embedding] Loading all-MiniLM-L6-v2...")
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    將文字列表轉為向量列表（本地執行，無 API 費用）。
    使用 all-MiniLM-L6-v2，維度 384，輸出已正規化為 numpy array。
    """
    model = _get_embed_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    return vectors.tolist()


def get_qdrant():
    """建立 Qdrant client（單次連線，不做連線池）。"""
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=getattr(config, "QDRANT_HOST", "localhost"),
        port=int(getattr(config, "QDRANT_PORT", 6333)),
    )


def get_embed_dim() -> int:
    """all-MiniLM-L6-v2 向量維度固定為 384。"""
    return 384


def init_collection():
    """
    確保 Qdrant collection 存在；若不存在則自動建立。
    Collection 名稱來自 config.COLLECTION_NAME。
    """
    from qdrant_client.models import Distance, VectorParams
    qc = get_qdrant()
    try:
        qc.get_collection(config.COLLECTION_NAME)
    except Exception:
        dim = get_embed_dim()
        print(f"[RAG] Creating Qdrant collection '{config.COLLECTION_NAME}' (dim={dim})")
        qc.create_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    return qc


def search(query: str, top_k: int = 5) -> list[dict]:
    """
    向量相似度檢索。

    參數
    ----
    query : 檢索文字
    top_k : 回傳最相似的 Top K 結果

    回傳
    ----
    list[dict] : [{"content": str, "source": str, "score": float}, ...]
    """
    from qdrant_client.models import VectorParams
    qc = init_collection()
    query_vec = embed_texts([query])[0]

    # Qdrant client 版本：query_points（新 API）
    results = qc.query_points(
        collection_name=config.COLLECTION_NAME,
        query=query_vec,
        limit=top_k,
        with_payload=True,
    ).points

    return [
        {
            "content": hit.payload.get("content", ""),
            "source":  hit.payload.get("source", ""),
            "score":   hit.score,
        }
        for hit in results
    ]


def add_documents(docs: list[dict]):
    """
    新增文件到 Qdrant 向量庫。

    參數
    ----
    docs : [{"content": "...", "source": "filename.txt"}, ...]
    """
    from qdrant_client.models import PointStruct
    qc = init_collection()
    vectors = embed_texts([d["content"] for d in docs])
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload={"content": d["content"], "source": d.get("source", "")},
        )
        for d, vec in zip(docs, vectors)
    ]
    qc.upsert(collection_name=config.COLLECTION_NAME, points=points)


def build_prompt(question: str, contexts: list[dict]) -> str:
    """
    組裝 Vector Mode 的 RAG prompt（給 ask_llm 使用）。

    注意：此 prompt 與 _build_rag_prompt 不同，這是給 Vector Mode
    （只有 top-k 相關文件）用的，沒有包含完整知識庫。
    """
    context_block = "\n\n".join(
        f"【文件 {i+1}】({c['source']}):\n{c['content']}"
        for i, c in enumerate(contexts)
    )
    return f"""你是一個公司內部智能助理，根據以下文件回答問題。
如果文件中沒有相關資訊，請說「目前沒有這個資料，請聯繫相關部門。」。

---
{context_block}
---

問題：{question}

回答："""


# ════════════════════════════════════════════════════════════════════════════
# 第四層：LLM 呼叫
# ════════════════════════════════════════════════════════════════════════════

def ask_llm(prompt: str) -> dict:
    """
    送 prompt 到已設定的 LLM，回傳 {"thinking": "", "answer": str}。

    支援的 Provider（由 config.LLM_PROVIDER 切換）
    -----------------------------------------------
    - minimax   : MiniMax ChatCompletions V2（預設，config.MINIMAX_API_KEY）
    - anthropic : Anthropic Messages API（config.ANTHROPIC_API_KEY）
    - openai    : OpenAI Chat Completions（config.OPENAI_API_KEY）

    錯誤處理
    --------
    任何 provider 失敗，回傳空 dict {}，由 caller 決定如何處理。
    不會拋出例外交給上層（避免一次網路錯誤就阻斷整個流程）。
    """
    provider = getattr(config, "LLM_PROVIDER", "minimax")

    if provider == "minimax":
        url = f"{config.MINIMAX_BASE_URL}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {config.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,        # 較低的隨機性，確保回答穩定
            "max_tokens": 1024,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            resp_data = resp.json()
            return {
                "thinking": "",
                "answer": resp_data["choices"][0]["message"]["content"],
            }
        except Exception as e:
            print(f"[LLM] MiniMax error: {e}")
            return {}

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"thinking": "", "answer": resp.content[0].text}

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"thinking": "", "answer": resp.choices[0].message.content}

    else:
        raise ValueError(f"[LLM] Unknown provider: {provider}. 請檢查 config.LLM_PROVIDER。")


# ════════════════════════════════════════════════════════════════════════════
# 第五層：輔助函式（敏感題判斷、答案信心評估）
# ════════════════════════════════════════════════════════════════════════════

def should_handover(question: str) -> bool:
    """
    判斷問題是否涉及敏感內容，應直接轉主管處理。

    原則
    ----
    - 涉及法律威脅、密碼、信用卡等 → 立即轉主管
    - 涉及内部管理事務 → 轉主管
    - 其餘正常走 RAG 流程
    """
    text = question.lower()
    SENSITIVE_KEYWORDS = [
        "秘密", "投訴", "法務", "法律", "告訴", "報警", "警察",
        "申訴管道", "内部", "黑名單", "炒魷魚", "裁員",
    ]
    return any(kw in text for kw in SENSITIVE_KEYWORDS)


def _ask_confidence(question: str, answer_text: str) -> float:
    """
    請 LLM 評估答案信心，傳回 0.0 ~ 1.0 的浮點數。

    實作細節
    --------
    - Prompt 要求 LLM 只回覆數字（避免多餘文字）
    - 用正則表達式取第一個 0.0~1.0 的數字
    - 失敗時回傳 0.5（中性信心）

    備註：此機制目前只用於雙模式比較，單模式（prompt）不使用。
    """
    if not answer_text or not answer_text.strip():
        return 0.0

    prompt = (
        f"問題：{question}\n"
        f"答案：{answer_text}\n\n"
        "答案是否正確、完整、有用？請只回覆一個 0.0 到 1.0 的數字："
    )
    try:
        result = ask_llm(prompt) or {}
        raw = result.get("answer", "0").strip()
        match = re.search(r"0\.\d+|1\.0|0", raw)
        if match:
            return float(match.group())
    except Exception:
        pass
    return 0.5


# ════════════════════════════════════════════════════════════════════════════
# 第六層：主回答函式
# ════════════════════════════════════════════════════════════════════════════

def answer(
    question: str,
    history: Optional[list[dict]] = None,
    method: Optional[str] = None,
) -> dict:
    """
    回答用戶問題的單一入口。

    參數
    ----
    question : 用戶問題
    history  : 對話歷史（目前未使用，為未來多輪對話預留）
    method   : 回答模式
               - None / "prompt" : Prompt Mode（推薦，知識庫直接塞進 prompt）
               - "vector"        : Vector Mode（需要 Qdrant，語意搜尋）
               - "dual"         : 雙模式並行（同時跑，取高分者）

    回傳
    ----
    {
        "answer"  : str,   # 直接顯示給用戶的答案
        "sources" : list,  # 來源文件 [{"source": str, "score": float}, ...]
        "handover": bool,  # True = 已轉主管，用戶看到「請稍候」
        "dual"    : dict | None,  # 雙模式時的詳細比較資訊
    }

    流程圖
    ------
    should_handover()  → True → 直接回「敏感資訊已轉主管」
         │
         ↓ False
    method == "vector"  → 純向量搜尋回答
         │
         ↓
    method == "prompt"  → Prompt Mode + 並行 Web 搜尋
         │
         ↓
    (其他 / None)       → 雙模式並行（vector + prompt + web search）
         │
         └→ 兩個分支都走完後：
              • 答案含糊（"沒有這個資料"）→ 轉主管
              • 分數 < 0.25 → 轉主管
              • 否則回傳得分較高的答案
    """
    # ── 0. 敏感題直接轉 ──────────────────────────────────────────────────
    if should_handover(question):
        return {
            "answer": "這個問題涉及敏感資訊，已通知專人與您聯繫。",
            "sources": [],
            "handover": True,
            "dual": None,
        }

    # ── 1. Prompt Mode（網路搜尋並行）────────────────────────────────────
    if method == "prompt":
        web_result_holder: list = [None]

        def _web_bg() -> None:
            """背景執行緒：網路搜尋（不阻塞主要流程）"""
            web_result_holder[0] = web_search(question)

        web_thread = threading.Thread(target=_web_bg, name="web-search")
        web_thread.start()

        # 第一階段：只用 KB，回答較快（約 8-15 秒）
        result = answer_by_prompt(question, web_results="")

        # 等待網路搜尋完成
        web_thread.join()
        web_res = web_result_holder[0] or ""

        # 第二階段：如果 web 有結果，用 KB + Web 重新生成（約 8-15 秒）
        if web_res:
            result = answer_by_prompt(question, web_results=web_res)

        return {**result, "dual": None}

    # ── 2. Vector Mode（純向量搜尋）───────────────────────────────────────
    if method == "vector":
        try:
            contexts = search(question, top_k=5)
        except Exception as e:
            print(f"[RAG] Vector search error: {e}")
            contexts = []

        if not contexts:
            return {
                "answer": "目前沒有這個資料，請聯繫全球客服中心 02-7733-0800。",
                "sources": [],
                "handover": False,
                "dual": None,
            }

        llm_result = ask_llm(build_prompt(question, contexts)) or {}
        return {
            "answer": llm_result.get("answer", ""),
            "sources": [{"source": c["source"], "score": c["score"]} for c in contexts],
            "handover": False,
            "dual": None,
        }

    # ── 3. 雙模式並行（vector + prompt + web search）─────────────────────
    #       同時跑三件事：向量搜尋、KB prompt、網路搜尋
    #       最後取分數較高的答案

    web_result_holder: list = [None]
    contexts: list = []
    vector_answer: str = ""
    vector_score: float = 0.0
    prompt_answer: str = ""
    prompt_score: float = 0.0

    def _web_bg() -> None:
        web_result_holder[0] = web_search(question)

    web_thread = threading.Thread(target=_web_bg, name="web-search-dual")

    # 啟動緒程
    web_thread.start()

    # ── Vector 分支 ──────────────────────────────────────────────────────
    try:
        contexts = search(question, top_k=5)
        if contexts:
            llm_r = ask_llm(build_prompt(question, contexts)) or {}
            vector_answer = llm_r.get("answer", "")
            vector_score = float(contexts[0]["score"])
    except Exception as e:
        print(f"[RAG] Vector branch error: {e}")
        vector_answer = ""
        vector_score = 0.0

    # ── Prompt 分支（先用 KB，web 完成後重新生成）───────────────────────────
    # 注意：此處故意先不用 web results，等 web thread join 後再重新生成
    try:
        prompt_r = answer_by_prompt(question, web_results="")
        prompt_answer = prompt_r.get("answer", "")
        prompt_score = _ask_confidence(question, prompt_answer)
    except Exception as e:
        print(f"[RAG] Prompt branch error: {e}")
        prompt_answer = ""
        prompt_score = 0.0

    # 等待網路搜尋完成
    web_thread.join()
    web_results = web_result_holder[0] or ""

    # 如果有 web 結果，重新生成 KB+Web 版本的答案
    if web_results:
        try:
            prompt_r2 = answer_by_prompt(question, web_results=web_results)
            prompt_answer = prompt_r2.get("answer", "")
            prompt_score = _ask_confidence(question, prompt_answer)
        except Exception as e:
            print(f"[RAG] Prompt re-generation error: {e}")

    # ── 選答案 + 決定是否轉主管 ──────────────────────────────────────────
    UNCERTAIN_PHRASES = [
        "沒有這個資料", "未提及", "未明確", "不確定", "不確定是否",
        "無法確認", "沒有明確", "尚未確認", "資料中沒有",
        "不清楚", "不知道", "無相關", "找不到",
    ]

    selected = "prompt" if prompt_score >= vector_score else "vector"
    final = prompt_answer if selected == "prompt" else vector_answer
    final_lower = final.lower()

    handover_reason: Optional[str] = None
    if any(phrase in final_lower for phrase in UNCERTAIN_PHRASES):
        handover_reason = "[Content-aware 判定]"
    elif prompt_score < 0.25 or vector_score < 0.25:
        handover_reason = "[分數不足]"

    # 寫入反饋資料庫（無論是否轉主管都寫）
    _write_feedback(
        question=question,
        vector_answer=vector_answer,
        vector_score=vector_score,
        prompt_answer=prompt_answer,
        prompt_score=prompt_score,
        selected_mode="handover" if handover_reason else selected,
        final_answer=f"{handover_reason} 需人工處理" if handover_reason else final,
    )

    # ── 轉主管 ──────────────────────────────────────────────────────────
    if handover_reason:
        return {
            "answer": "這個問題我需要確認一下，請稍候，我會通知專人回覆您。",
            "sources": [],
            "handover": True,
            "dual": {
                "vector_answer": vector_answer,
                "vector_score": round(vector_score, 4),
                "prompt_answer": prompt_answer,
                "prompt_score": round(prompt_score, 4),
                "selected_mode": "handover",
                "web_results_used": bool(web_results),
            },
        }

    # ── 回傳答案 ────────────────────────────────────────────────────────
    sources = (
        [{"source": c["source"], "score": c["score"]} for c in contexts]
        if selected == "vector"
        else prompt_r.get("sources", [])
    )
    return {
        "answer": final,
        "sources": sources,
        "handover": False,
        "dual": {
            "vector_answer": vector_answer,
            "vector_score": round(vector_score, 4),
            "prompt_answer": prompt_answer,
            "prompt_score": round(prompt_score, 4),
            "selected_mode": selected,
            "web_results_used": bool(web_results),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# 第七層：資料庫輔助
# ════════════════════════════════════════════════════════════════════════════

def _write_feedback(
    question: str,
    vector_answer: str,
    vector_score: float,
    prompt_answer: str,
    prompt_score: float,
    selected_mode: str,
    final_answer: str,
) -> None:
    """
    將每次 RAG 回答寫入 SQLite（rag_feedback 表），供日後分析與模型回饋。
    失敗時靜默忽略（不回覆用戶錯誤，不阻斷流程）。
    """
    db_path = os.path.join(os.path.dirname(__file__), "data", "chat_history.db")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_feedback (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                question          TEXT,
                vector_answer     TEXT,
                vector_score      REAL,
                prompt_answer     TEXT,
                prompt_score      REAL,
                selected_mode     TEXT,
                final_answer      TEXT,
                created_at        TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO rag_feedback
                (question, vector_answer, vector_score,
                 prompt_answer, prompt_score, selected_mode, final_answer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            question, vector_answer, vector_score,
            prompt_answer, prompt_score, selected_mode, final_answer,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Feedback write failed: {e}")
