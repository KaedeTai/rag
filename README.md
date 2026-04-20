# Total Swiss 智能客服系統

RAG（Retrieval-Augmented Generation）客服 Bot，支援 Telegram + 公開網頁客服介面。

---

## 系統架構

```
 客戶訊息
     │
     ▼
 Telegram @Total_Swiss_bot        公開網頁 /chat
     │                                    │
     ▼                                    ▼
 telegram_bot.py（長輪詢）         supervisor.py :9092/chat
     │                              （Flask）
     ▼
 app.py :9093（FastAPI）◄──────────┘
     │
     ├── rag.answer() ────► RAG 核心引擎
     │                       │
     │                       ├── Prompt Mode（預設）：知識庫 + Web 搜尋
     │                       ├── Vector Mode：Qdrant 向量檢索
     │                       └── Dual Mode：兩者並行
     │
     └── supervisor.py :9092/
           ├── /              主管後台（待回覆問題）
           ├── /answered      已回覆記錄
           ├── /feedback      RAG 雙模式評估
           └── /api/webhook   Bot 寫入新問題
```

---

## 服務列表

| 服務 | 檔案 | Port | 說明 |
|------|------|------|------|
| Telegram Bot | `telegram_bot.py` | — | 長輪詢接收訊息 |
| RAG API | `app.py` | 9093 | AI 對話、知識庫、Web 搜尋 |
| 主管後台 | `supervisor.py` | 9092/ | 主管查看並回覆客戶問題 |
| 公開客服網頁 | `supervisor.py` | 9092/chat | 客戶直接輸入問題的網頁 |

---

## 啟動與停止

```bash
# 1. Qdrant 向量資料庫（長期跑，Vector Mode 需要）
/Users/apple/clawd-kaedebot/rag/qdrant_bin/qdrant --uri http://127.0.0.1:6333 &

# 2. RAG API
cd /Users/apple/clawd-kaedebot/rag
python3 app.py &          # port 9093

# 3. Supervisor Dashboard（含公開客服網頁）
python3 supervisor.py &    # port 9092

# 4. Telegram Bot
./bot_service.sh start   # 位於 rag/bot_service.sh
```

---

## 目錄結構

```
rag/
├── app.py                  # FastAPI 主體（port 9093）
├── supervisor.py           # Flask 主管後台 + 公開客服網頁（port 9092）
├── telegram_bot.py         # Telegram Bot 主程式
├── rag.py                  # RAG 核心引擎
│                           #   ├── 網路搜尋（web_search）
│                           #   ├── 知識庫載入（load_kb_text）
│                           #   ├── Prompt Mode（answer_by_prompt）
│                           #   ├── Vector Mode（search / add_documents）
│                           #   ├── LLM 呼叫（ask_llm）
│                           #   └── 主回答函式（answer）
├── indexer.py              # 知識庫建索引 CLI（Vector Mode 用）
├── config.py               # 設定檔（支援環境變數）
├── data/                   # 知識庫內容
│   ├── 01_公司簡介.md
│   ├── 02_產品資訊.md
│   ├── 03_常見問題.md
│   └── 04_媒體報導.md
└── qdrant_bin/            # Qdrant 向量資料庫執行檔
```

---

## 回答流程（`rag.answer`）

```
接收問題
    │
    ▼
should_handover() → 敏感題 → 回「已通知專人」（見下方關鍵字清單）
    │
    ├── method == "prompt"（預設）
    │       │
    │       └── 背景執行緒：web_search(question)
    │               │
    │               ├── KB-only 回答（約 8-15s）
    │               ├── web thread join
    │               └── 有 web 結果 → KB+Web 重新生成
    │
    ├── method == "vector"
    │       └── Qdrant 向量檢索 → ask_llm → 回傳
    │
    └── method == "dual"（兩者並行）
            ├── web_search（背景）
            ├── search → ask_llm（Vector 分支）
            ├── answer_by_prompt → _ask_confidence（Prompt 分支）
            ├── web join → KB+Web 重新生成（如有結果）
            └── 選分數高者
                    │
                    ├── 含糊（"沒有這個資料"）→ 轉主管
                    ├── 分數 < 0.25 → 轉主管
                    └── 否則回傳答案
```

---

## 知識庫管理

| 檔案 | 內容 |
|------|------|
| `01_公司簡介.md` | 公司背景、創立、總部、客服電話 |
| `02_產品資訊.md` | 四大領域（Fit/Time/Air/Water）、產品價格 |
| `03_常見問題.md` | 購買/會員、縣市據點、物流、保固、退換貨 |
| `04_媒體報導.md` | 媒體報導、殊榮、認證、用戶調查 |

**新增或更新知識**：直接編輯 `data/*.md`，Prompt Mode 立即生效（不需要重啟）。

---

## API 端點

### `POST /api/chat_json`（主要端點）

```json
// Request
{
  "question": "高雄公司地址？",
  "session_id": "user_123",   // 選填
  "method": "prompt"           // prompt | vector | dual（預設：config.RAG_METHOD）
}

// Response
{
  "answer": "高雄公司地址：**高雄市前金區五福三路 21 號 3 樓**...",
  "sources": [{"source": "03_常見問題.md", "score": 1.0}],
  "handover": false,
  "session_id": "user_123",
  "dual": null                // prompt mode = null
}
```

### `GET /api/status`
健康檢查：LLM provider、Qdrant 連線狀態。

### `POST /api/reset`
清除指定 session 的訊息歷史。

---

## 設定（環境變數）

```bash
# LLM
export LLM_PROVIDER="minimax"      # minimax | anthropic | openai
export LLM_MODEL="MiniMax-M2.7"
export MINIMAX_API_KEY="sk-..."

# RAG 模式（預設：prompt）
export RAG_METHOD="prompt"          # prompt | vector | dual

# Telegram
export TELEGRAM_BOT_TOKEN="8450020208:AAFk..."
export ADMIN_TELEGRAM_ID="574704148"

# Qdrant（Vector Mode 需要）
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"
```

---

## 技術規格

| 項目 | 細節 |
|------|------|
| LLM | MiniMax ChatCompletions V2（`https://api.minimaxi.com/v1/text/chatcompletion_v2`） |
| Embedding | `all-MiniLM-L6-v2`（本地執行，384 維） |
| 向量庫 | Qdrant（`localhost:6333`） |
| Web 搜尋 | Brave API → DuckDuckGo HTML fallback |
| 知識庫格式 | Markdown（Prompt Mode 無需建索引） |

---

## 常見問題

**Q: Bot 沒有回應？**
```bash
# 檢查程序
ps aux | grep -E "telegram_bot|app.py|supervisor" | grep -v grep
# 檢查 API 狀態
curl http://localhost:9093/api/status
```

**Q: 知識庫更新後答案沒變？**
Prompt Mode：變更立即生效（KB 讀自磁碟，無需重啟）。
Vector Mode：`python3 indexer.py` 重建索引後重啟 app.py。

**Q: Telegram 409 Conflict？**
多個 Bot 程序同時跑，先 `./bot_service.sh stop` 再 `./bot_service.sh start`。

**Q: AI 一直說「沒有這個資料」？**
1. 檢查 `data/03_常見問題.md` 是否有該主題
2. 確認 Web 搜尋正常（`BRAVE_API_KEY` 是否設定）
3. 在 `/feedback` 頁面標記答案好壞，累積後同步進向量庫

---

## 敏感關鍵字（轉主管）

以下關鍵字出現時，Bot 直接轉給主管，不經過 MiniMax：

| 類別 | 關鍵字 |
|------|--------|
| 帳號安全 | 密碼、信用卡、帳號、帳戶、密文 |
| 法律 | 法律、律師、訴訟、報案、報警、告、起訴、控告、提告、法院、檢調、消保官 |
| 金流 | 投資、出金、入金、匯款、轉帳 |
| 消費 | 退款、消費糾紛、投訴、申訴管道 |
| 推廣 | 優惠券、折扣碼、兌換、抽獎 |
| 會籍 | 如何加入、如何購買、直銷 |
| 合約 | 要約要約邀請定型化契約 |
| 個資 | 個資隱私個資法 |

---

## Bot 操作資訊

- **Bot**: `@Total_Swiss_bot`
- **Token**: `8450020208:AAFkPREJy4BWoyRkC4P3lZUeJf-oHEcDjQ8`
- **Supervisor Dashboard**: `http://localhost:9092/`
- **公開客服網頁**: `http://localhost:9092/chat`
- **主管 Telegram ID**: `574704148`
