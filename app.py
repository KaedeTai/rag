"""
rag/app.py
=========
FastAPI 主體 - RAG API 伺服器（port 9093）

職責
----
1. HTTP REST API：接收問題、回傳 RAG 答案
2. 對話歷史管理（SQLite）
3. Web UI 渲染（Jinja2）

主要端點
--------
POST /api/chat_json  - JSON 格式（給 Bot 與網頁後台用）
GET  /              - Web UI 首頁
GET  /api/status    - 健康檢查

注意
----
- chat history 僅用於未來多輪對話擴充，目前每次呼叫都是獨立問答
- session_id 可控制對話歷史分組，若不提供則每次產生新的 UUID
"""

# ─── 標準 library ────────────────────────────────────────────────────────────
import sqlite3
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── 第三方套件 ─────────────────────────────────────────────────────────────
from fastapi import FastAPI, Form, Request, Depends
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

# ─── 本地模組 ────────────────────────────────────────────────────────────────
import config
import rag

# ════════════════════════════════════════════════════════════════════════════
# 初始化
# ════════════════════════════════════════════════════════════════════════════

BASE = Path(__file__).parent
os.makedirs(BASE / "data", exist_ok=True)

app = FastAPI(title="Total Swiss 智能客服 API")

# Jinja2 templates（目前只有一個簡單的 chat.html）
try:
    jinja_env = Environment(loader=FileSystemLoader(str(BASE / "templates")))
except Exception:
    # templates 目錄不存在時，使用空環境（首頁不會用到 Jinja2 功能）
    jinja_env = None

# ════════════════════════════════════════════════════════════════════════════
# 資料庫工具
# ════════════════════════════════════════════════════════════════════════════

def get_db():
    """
    取得 SQLite 連線，並確保必要的 Table 存在。
    使用 check_same_thread=False 讓不同緒程可以共享連線。
    """
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         TEXT PRIMARY KEY,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         TEXT PRIMARY KEY,
            session_id TEXT,
            role       TEXT,
            content    TEXT,
            ts         TEXT
        )
    """)
    conn.commit()
    return conn


def save_message(session_id: str, role: str, content: str) -> None:
    """寫入一筆訊息到資料庫。"""
    db = get_db()
    db.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), session_id, role, content, datetime.now().isoformat()),
    )
    db.commit()
    db.close()


def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """取得指定 session 的最新 N 筆訊息（由新到舊，取完後反轉）。"""
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM messages "
        "WHERE session_id=? ORDER BY ts DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    db.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


# ════════════════════════════════════════════════════════════════════════════
# API 端點
# ════════════════════════════════════════════════════════════════════════════

@app.post("/api/chat_json")
async def chat_json(request_data: dict):
    """
    主要對話端點（JSON 格式）。

    Request Body
    ------------
    {
        "question"   : str,   # 用戶問題（必填）
        "session_id": str?,   # 對話 ID（選填，不提供則自動產生）
        "method"     : str?,  # "prompt"(預設) | "vector" | "dual"
    }

    Response
    --------
    {
        "answer"   : str,
        "sources"  : list,
        "handover" : bool,
        "session_id": str,
        "dual"     : dict | null,
    }
    """
    question   = request_data.get("question", "").strip()
    session_id = request_data.get("session_id") or str(uuid.uuid4())
    method     = request_data.get("method") or config.RAG_METHOD

    if not question:
        return {"error": "question 不能為空", "handover": False}

    # 紀錄新 session
    if not request_data.get("session_id"):
        db = get_db()
        db.execute(
            "INSERT INTO sessions VALUES (?, ?)",
            (session_id, datetime.now().isoformat()),
        )
        db.commit()
        db.close()

    history = get_history(session_id)

    # 呼叫 RAG 核心
    result = rag.answer(question, history=history, method=method)

    # 寫入歷史（對話歷史，與 RAG feedback 表不同）
    save_message(session_id, "user", question)
    save_message(session_id, "assistant", result["answer"])

    return {
        "answer":    result["answer"],
        "sources":   result["sources"],
        "handover":  result["handover"],
        "session_id": session_id,
        "dual":      result.get("dual"),
    }


@app.get("/api/sessions/{sid}/history")
def session_history(sid: str):
    """取得指定 session 的對話歷史。"""
    return get_history(sid)


@app.post("/api/reset")
async def reset_session(session_id: str = Form(...)):
    """
    清除指定 session 的所有訊息歷史。

    注意：這不會清除 RAG feedback 表的資料。
    """
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    db.commit()
    db.close()
    return {"ok": True, "session_id": session_id}


@app.get("/api/status")
def api_status():
    """
    健康檢查端點。

    檢查項目
    -------
    - Qdrant 連線狀態（Vector Mode 需要）
    - LLM Provider 設定
    """
    status = {"llm_provider": config.LLM_PROVIDER, "llm_model": config.LLM_MODEL}
    try:
        qc = rag.get_qdrant()
        qc.get_collection(config.COLLECTION_NAME)
        status["qdrant"] = "connected"
    except Exception as e:
        status["qdrant"] = f"error: {e}"
    return status


# ════════════════════════════════════════════════════════════════════════════
# Web UI（目前為簡單的 chat 頁面）
# ════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Web UI 首頁。"""
    if jinja_env is None:
        return "<h1>Total Swiss 智能客服</h1><p>templates 目錄未設定，請聯繫管理員。</p>"
    tmpl = jinja_env.get_template("chat.html")
    return tmpl.render(request=request)


# ════════════════════════════════════════════════════════════════════════════
# CLI 模式（直接終端機互動，開發/除錯用）
# ════════════════════════════════════════════════════════════════════════════

def cli():
    """
    終端機互動模式。

    使用方式
    --------
    python app.py --cli
    """
    print("Total Swiss 智能客服（CLI 模式）\n")
    session_id = str(uuid.uuid4())
    while True:
        q = input("你：").strip()
        if q.lower() in ("exit", "quit", "q"):
            break
        result = rag.answer(q, method="prompt")
        print(f"\n助理：{result['answer']}\n")
        if result["sources"]:
            print("來源：" + "、".join(s["source"] for s in result["sources"]))
        print()
        save_message(session_id, "user", q)
        save_message(session_id, "assistant", result["answer"])


if __name__ == "__main__":
    import sys, uvicorn
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        cli()
    else:
        uvicorn.run(
            app,
            host=config.WEB_HOST,
            port=config.WEB_PORT,
            log_level="info",
        )
