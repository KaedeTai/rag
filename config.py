"""
rag/config.py
=============
組態設定檔。

設計原則
--------
所有設定皆可透過環境變數置換，預設值僅供本地開發使用。
正式環境、生產部署強烈建議使用環境變數，而非修改此檔案。

機密資訊（API key、token）
-------------------------
不要把實際的 key 寫在程式碼裡。推薦做法：

    export MINIMAX_API_KEY="sk-..."
    export TELEGRAM_BOT_TOKEN="..."
    export BRAVE_API_KEY="..."

或在 systemd / launchd 環境中設定環境變數。
"""

import os

# ════════════════════════════════════════════════════════════════════════════
# LLM 設定
# ════════════════════════════════════════════════════════════════════════════

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "minimax")
"""
切換 LLM provider。
- "minimax"   : MiniMax ChatCompletions V2（預設）
- "anthropic" : Anthropic Claude API
- "openai"    : OpenAI ChatGPT API
"""

LLM_MODEL = os.getenv("LLM_MODEL", "MiniMax-M2.7")
"""LLM 模型名稱。注意：不同 provider 的模型名稱格式不同。"""

# ── MiniMax ─────────────────────────────────────────────────────────────────
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
"""MiniMax API Key。建議透過環境變數設定。"""
MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"

# ── Anthropic ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ════════════════════════════════════════════════════════════════════════════
# Embedding 設定（Vector Mode 使用，Prompt Mode 不需要）
# ════════════════════════════════════════════════════════════════════════════

EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "local")
"""
Embedding provider。
- "local"  : 本地 sentence-transformers（推薦，無 API 費用）
- "openai" : OpenAI text-embedding-3-small
"""

LOCAL_EMBED_MODEL  = "nomic-embed-text"      # 本地模型（目前未使用，保留）
OPENAI_EMBED_MODEL = "text-embedding-3-small" # OpenAI 模型（目前未使用，保留）

# ════════════════════════════════════════════════════════════════════════════
# 向量資料庫（Qdrant）
# ════════════════════════════════════════════════════════════════════════════

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_knowledge")

# ════════════════════════════════════════════════════════════════════════════
# 對話歷史（SQLite）
# ════════════════════════════════════════════════════════════════════════════

DB_PATH = os.getenv("DB_PATH", "data/chat_history.db")

# ════════════════════════════════════════════════════════════════════════════
# 網站設定
# ════════════════════════════════════════════════════════════════════════════

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "9093"))

# ════════════════════════════════════════════════════════════════════════════
# RAG 模式
# ════════════════════════════════════════════════════════════════════════════

RAG_METHOD = os.getenv("RAG_METHOD", "prompt")
"""
RAG 回答模式。
- "prompt" : Prompt Mode（推薦，知識庫直接塞進 prompt，快速且不需要 Qdrant）
- "vector" : Vector Mode（需要 Qdrant 向量資料庫）
- "dual"   : 雙模式並行（同時跑，取高分者，慢但嚴謹）
"""

# ════════════════════════════════════════════════════════════════════════════
# 網路搜尋
# ════════════════════════════════════════════════════════════════════════════

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
"""Brave Search API Key（選填，不填則使用 DuckDuckGo HTML fallback）。"""
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# ════════════════════════════════════════════════════════════════════════════
# Telegram Bot（由 telegram_bot.py 與 supervisor.py 直接使用）
# ════════════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8450020208:AAFkPREJy4BWoyRkC4P3lZUeJf-oHEcDjQ8")
ADMIN_TELEGRAM_ID  = os.getenv("ADMIN_TELEGRAM_ID", "574704148")
