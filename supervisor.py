#!/usr/bin/env python3
# rag/supervisor.py
# 主管網頁後台：查看所有待回覆問題、直接回覆客戶
#
# 主要路由
# --------
#   GET  /              - 待回覆問題列表
#   GET  /answered      - 已回覆記錄
#   POST /reply/<qid>   - 送出回覆（同步到 Telegram）
#   GET  /chat          - 公開客服網頁
#   GET  /feedback      - RAG 雙模式評估頁面
#   POST /api/webhook   - Bot 寫入新問題（Bot → Supervisor）
#   POST /api/feedback/sync - 將"Good"標記同步進 Qdrant

import config

import sqlite3, os
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, redirect, url_for

BASE  = Path(__file__).parent
DB    = BASE / "data" / "chat_history.db"
TOKEN = config.TELEGRAM_BOT_TOKEN
BOT   = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
ADMIN_ID = config.ADMIN_TELEGRAM_ID

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(32)

# ── DB ──────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB), check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS questions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT,
        user_name   TEXT,
        question    TEXT,
        chat_id     INTEGER,
        msg_id      INTEGER,
        created_at  TEXT,
        answered_at TEXT,
        status      TEXT DEFAULT 'pending',
        answer      TEXT
    )""")
    conn.commit()
    return conn


def save_question(user_id, user_name, question, chat_id, msg_id):
    db = get_db()
    db.execute("""INSERT INTO questions
        (user_id, user_name, question, chat_id, msg_id, created_at, status)
        VALUES (?,?,?,?,?,?,?)""",
        (user_id, user_name, question, chat_id, msg_id,
         datetime.now().isoformat(), "pending"))
    db.commit()
    db.close()


def answer_question(qid: int, answer: str):
    db = get_db()
    db.execute("""UPDATE questions
        SET status=?, answer=?, answered_at=?
        WHERE id=?""",
        ("answered", answer, datetime.now().isoformat(), qid))
    db.commit()
    row = db.execute("SELECT chat_id, user_name, question FROM questions WHERE id=?", (qid,)).fetchone()
    db.close()
    return row  # (chat_id, user_name, question)


def get_pending():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM questions WHERE status='pending' ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    cols = ["id","user_id","user_name","question","chat_id","msg_id","created_at","answered_at","status","answer"]
    return [dict(zip(cols, r)) for r in rows]


def get_answered(limit=50):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM questions WHERE status='answered' ORDER BY answered_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    db.close()
    cols = ["id","user_id","user_name","question","chat_id","msg_id","created_at","answered_at","status","answer"]
    return [dict(zip(cols, r)) for r in rows]


# ── Telegram 通知 ─────────────────────────────────────────────────────────────

import requests


def get_feedback(limit=50):
    db = get_db()
    rows = db.execute("""
        SELECT id, question, vector_answer, vector_score, vector_thinking,
               prompt_answer, prompt_score, prompt_thinking,
               selected_mode, final_answer,
               human_verdict_vector, human_verdict_prompt, created_at
        FROM rag_feedback
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return [dict(zip(
        ["id","question","vector_answer","vector_score","vector_thinking",
         "prompt_answer","prompt_score","prompt_thinking",
         "selected_mode","final_answer",
         "human_verdict_vector","human_verdict_prompt","created_at"], r
    )) for r in rows]

def update_verdict(fid, mode, verdict):
    col = "human_verdict_" + mode  # "vector" or "prompt"
    db = get_db()
    db.execute(f"UPDATE rag_feedback SET {col}=? WHERE id=?", (verdict, fid))
    db.commit()
    db.close()

def sync_good_to_vector():
    """將人類標記為好的答案寫入 Qdrant。"""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    import rag
    db = get_db()
    rows = db.execute("""
        SELECT id, question, vector_answer, prompt_answer,
               human_verdict_vector, human_verdict_prompt
        FROM rag_feedback
        WHERE human_verdict_vector='good' OR human_verdict_prompt='good'
    """).fetchall()
    db.close()
    synced = 0
    for row in rows:
        fid, question, va, pa, vv, vp = row
        # 選被標記 good 的答案
        good_answer = None
        if vv == "good" and va:
            good_answer = va
        elif vp == "good" and pa:
            good_answer = pa
        if not good_answer:
            continue
        try:
            rag.add_documents([{
                "content": f"問題：{question}\n\n回答：{good_answer}",
                "source": f"[human-feedback-{fid}]"
            }])
            synced += 1
            print(f"[Sync] FID={fid} synced to vector DB")
        except Exception as e:
            print(f"[Sync] FID={fid} failed: {e}")
    return synced


FEEDBACK_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>RAG 雙模式回饋</title>
<style>
  body{font-family:-apple-system,sans-serif;background:#f4f6f9;padding:20px;}
  h1{color:#1a3c6e;margin-bottom:20px;}
  .topnav{display:flex;gap:12px;margin-bottom:20px;}
  .topnav a{padding:8px 16px;background:#1a3c6e;color:white;border-radius:6px;text-decoration:none;font-size:14px;}
  .topnav span{padding:8px 16px;background:#28a745;color:white;border-radius:6px;font-size:14px;}
  .card{background:white;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,0.12);}
  .q{font-size:15px;font-weight:bold;color:#1a3c6e;margin-bottom:12px;padding:8px;background:#f0f4ff;border-radius:6px;}
  .mode-section{padding:10px;border-radius:6px;margin-bottom:8px;}
  .mode-vector{background:#fff3cd;}.mode-prompt{background:#d1ecf1;}
  .mode-label{font-size:12px;font-weight:bold;padding:2px 8px;border-radius:10px;display:inline-block;margin-bottom:6px;}
  .l-vector{background:#ffc107;color:#333;}.l-prompt{background:#17a2b8;color:white;}
  .l-selected{background:#28a745;color:white;}
  .score{font-size:12px;color:#666;}
  .answer-text{font-size:14px;margin:6px 0;}
  .verdict-row{display:flex;gap:8px;margin-top:8px;}
  .vbtn{padding:4px 12px;border:none;border-radius:4px;cursor:pointer;font-size:13px;}
  .v-good{background:#28a745;color:white;}.v-bad{background:#dc3545;color:white;}
  .v-none{background:#ccc;color:#333;}
  .verdicted{border:2px solid #28a745;}
  .meta{font-size:12px;color:#999;margin-top:8px;}
  .sync-btn{padding:10px 20px;background:#28a745;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;}
  .card-meta{font-size:12px;color:#888;margin-bottom:8px;}
</style>
</head>
<body>
<div class="topnav">
  <a href="/">← 待回覆</a>
  <a href="/answered">已回覆</a>
  <span>雙模式回饋</span>
</div>
<h1>雙模式評估（vector vs prompt）</h1>

<form action="/api/feedback/sync" method="post" style="margin-bottom:20px;">
  <button type="submit" class="sync-btn">🔄 同步"Good"答案進向量資料庫</button>
</form>

{% for f in feedback %}
<div class="card">
  <div class="card-meta">#{{ f.id }} ｜ {{ f.created_at }}</div>
  <div class="q">Q：{{ f.question }}</div>

  <!-- Vector 答案 -->
  <div class="mode-section mode-vector" id="vec-{{ f.id }}">
    <span class="mode-label l-vector">VECTOR</span>
    {% if f.selected_mode == 'vector' %}<span class="mode-label l-selected">✓ 採用</span>{% endif %}
    <div class="score">分數：{{ "%.4f"|format(f.vector_score) }}</div>
    <div class="answer-text">{{ f.vector_answer }}</div>
    {% if f.vector_thinking %}<details class="thinking-box"><summary>🤔 Thinking</summary><pre>{{ f.vector_thinking }}</pre></details>{% endif %}
    <div class="verdict-row">
      <button class="vbtn v-good"
        onclick="setVerdict({{ f.id }}, 'vector', 'good')"
        {% if f.human_verdict_vector=='good' %}style="outline:3px solid #28a745"{% endif %}>
        👍 Good
      </button>
      <button class="vbtn v-bad"
        onclick="setVerdict({{ f.id }}, 'vector', 'bad')"
        {% if f.human_verdict_vector=='bad' %}style="outline:3px solid #dc3545"{% endif %}>
        👎 Bad
      </button>
      <button class="vbtn v-none"
        onclick="setVerdict({{ f.id }}, 'vector', '')"
        {% if not f.human_verdict_vector %}style="outline:2px solid #888"{% endif %}>
        清除
      </button>
    </div>
  </div>

  <!-- Prompt 答案 -->
  <div class="mode-section mode-prompt" id="pr-{{ f.id }}">
    <span class="mode-label l-prompt">PROMPT</span>
    {% if f.selected_mode == 'prompt' %}<span class="mode-label l-selected">✓ 採用</span>{% endif %}
    <div class="score">分數：{{ "%.4f"|format(f.prompt_score) }}</div>
    <div class="answer-text">{{ f.prompt_answer }}</div>
    {% if f.prompt_thinking %}<details class="thinking-box"><summary>🤔 Thinking</summary><pre>{{ f.prompt_thinking }}</pre></details>{% endif %}
    <div class="verdict-row">
      <button class="vbtn v-good"
        onclick="setVerdict({{ f.id }}, 'prompt', 'good')"
        {% if f.human_verdict_prompt=='good' %}style="outline:3px solid #28a745"{% endif %}>
        👍 Good
      </button>
      <button class="vbtn v-bad"
        onclick="setVerdict({{ f.id }}, 'prompt', 'bad')"
        {% if f.human_verdict_prompt=='bad' %}style="outline:3px solid #dc3545"{% endif %}>
        👎 Bad
      </button>
      <button class="vbtn v-none"
        onclick="setVerdict({{ f.id }}, 'prompt', '')"
        {% if not f.human_verdict_prompt %}style="outline:2px solid #888"{% endif %}>
        清除
      </button>
    </div>
  </div>

  <div class="meta">最終採用：{{ f.selected_mode }} ｜ {{ f.final_answer[:60] }}...</div>
</div>
{% endfor %}

<script>
async function setVerdict(id, mode, verdict) {
  await fetch(`/api/feedback/${id}/verdict/${mode}?verdict=${verdict}`, {method:"POST"});
  location.reload();
}
</script>
</body>
</html>
"""

def send_telegram(chat_id, text):
    try:
        requests.post(f"{BOT}/sendMessage", json={
            "chat_id": chat_id, "text": text[:4096]
        }, timeout=10)
    except Exception as e:
        print(f"[Telegram error] {e}")


# ── 頁面 ─────────────────────────────────────────────────────────────────────

TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Total Swiss 客服管理後台</title>
<style>
  *  { box-sizing: border-box; margin: 0; padding: 0; }
  body{ font-family: -apple-system, sans-serif; background:#f4f6f9; color:#333; padding:20px; }
  h1  { color:#1a3c6e; margin-bottom:20px; }
  .badge{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:12px; }
  .pending{ background:#fff3cd; color:#856404; }
  .answered{ background:#d4edda; color:#155724; }
  .card{ background:white; border-radius:8px; padding:16px; margin-bottom:16px;
         box-shadow:0 1px 4px rgba(0,0,0,0.1); }
  .card-header{ display:flex; justify-content:space-between; align-items:center;
                 margin-bottom:10px; }
  .card-meta{ font-size:12px; color:#888; }
  .card-question{ background:#f8f9fa; border-radius:6px; padding:12px;
                  margin-bottom:12px; font-size:15px; }
  .card-answer  { background:#e8f4fd; border-radius:6px; padding:12px; font-size:15px; }
  .reply-form{ display:flex; gap:8px; }
  .reply-form textarea{ flex:1; padding:8px; border:1px solid #ddd;
                        border-radius:6px; resize:vertical; min-height:60px; }
  .reply-form button{ background:#1a3c6e; color:white; border:none;
                      padding:8px 20px; border-radius:6px; cursor:pointer; }
  .reply-form button:hover{ background:#2a5bae; }
  .tabs{ display:flex; gap:4px; margin-bottom:20px; }
  .tab{ padding:8px 20px; border-radius:6px 6px 0 0; cursor:pointer;
        background:#ddd; color:#555; text-decoration:none; }
  .tab.active{ background:#1a3c6e; color:white; }
  .count{ display:inline-block; background:#dc3545; color:white;
          border-radius:10px; padding:1px 7px; font-size:11px; margin-left:4px; }
  .empty{ color:#888; text-align:center; padding:40px; }
  .success{ background:#d4edda; color:#155724; padding:10px 16px;
             border-radius:6px; margin-bottom:16px; }
</style>
</head>
<body>
<h1>Total Swiss 客服管理後台</h1>

<div class="tabs">
  <a class="tab active" href="/">待回覆 <span class="count">{{ pending_count }}</span></a>
  <a class="tab" href="/answered">已回覆</a>
</div>

{% if success %}
<div class="success">✅ 已回覆，客戶將收到通知。</div>
{% endif %}

<div id="questions">
  {% if pending %}
    {% for q in pending %}
    <div class="card" id="q{{ q.id }}">
      <div class="card-header">
        <strong>{{ q.user_name or q.user_id }}</strong>
        <span class="badge pending">待回覆</span>
      </div>
      <div class="card-meta">用戶ID: {{ q.user_id }}｜時間: {{ q.created_at }}</div>
      <div class="card-question">{{ q.question }}</div>
      <form class="reply-form" method="post" action="/reply/{{ q.id }}">
        <textarea name="answer" placeholder="輸入回覆內容..."></textarea>
        <button type="submit">發送回覆</button>
      </form>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">✅ 沒有待回覆的問題</div>
  {% endif %}
</div>
</body>
</html>
"""

ANSWERED_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>已回覆記錄</title>
<style>
  body{ font-family:-apple-system,sans-serif; background:#f4f6f9; padding:20px; }
  .card{ background:white; border-radius:8px; padding:16px; margin-bottom:12px;
         box-shadow:0 1px 4px rgba(0,0,0,0.1); }
  .badge{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:12px; }
  .answered{ background:#d4edda; color:#155724; }
  .card-meta{ font-size:12px; color:#888; margin-bottom:8px; }
  .q{ background:#f8f9fa; padding:10px; border-radius:6px; margin-bottom:8px; }
  .a{ background:#e8f4fd; padding:10px; border-radius:6px; color:#155724; }
  h1{ color:#1a3c6e; margin-bottom:20px; }
  .back{ display:inline-block; margin-bottom:16px; color:#1a3c6e; }
</style>
</head>
<body>
<a class="back" href="/">← 返回待回覆</a>
<h1>已回覆記錄</h1>
{% for q in answered %}
<div class="card">
  <div class="card-meta">
    <strong>{{ q.user_name or q.user_id }}</strong> ({{ q.user_id }})
    ｜ 回覆時間：{{ q.answered_at }}
  </div>
  <div class="q"><strong>Q：</strong>{{ q.question }}</div>
  <div class="a"><strong>A：</strong>{{ q.answer }}</div>
</div>
{% endfor %}
</body>
</html>
"""



# ── 公開客服網頁 ──────────────────────────────────────────────────────────────

CHAT_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Total Swiss 線上客服</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; height: 100vh; display: flex; flex-direction: column; }
  .header { background: #8B0029; color: white; padding: 16px 24px; display: flex; align-items: center; gap: 12px; }
  .header img { width: 36px; height: 36px; border-radius: 50%; }
  .header h1 { font-size: 18px; font-weight: 600; }
  .header span { font-size: 13px; opacity: 0.85; }
  .chat { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; max-width: 720px; margin: 0 auto; width: 100%; }
  .msg { display: flex; gap: 10px; max-width: 85%%; }
  .msg.user { align-self: flex-end; flex-direction: row-reverse; }
  .msg .bubble { padding: 12px 16px; border-radius: 18px; font-size: 15px; line-height: 1.5; }
  .msg.bot .bubble { background: white; border-top-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .msg.user .bubble { background: #8B0029; color: white; border-top-right-radius: 4px; }
  .msg .time { font-size: 11px; opacity: 0.6; margin-top: 4px; text-align: right; }
  .typing { display: flex; gap: 8px; align-items: center; padding: 12px 16px; background: white; border-radius: 18px; width: fit-content; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .typing-dot { width: 8px; height: 8px; background: #aaa; border-radius: 50%%; animation: bounce 1.4s infinite; }
  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce { 0%%,60%%,100%% { transform: translateY(0); } 30%% { transform: translateY(-6px); } }
  .input-area { background: white; padding: 16px 24px; border-top: 1px solid #eee; }
  .input-row { display: flex; gap: 12px; max-width: 720px; margin: 0 auto; }
  .input-row input { flex: 1; padding: 12px 16px; border: 1px solid #ddd; border-radius: 24px; font-size: 15px; outline: none; }
  .input-row input:focus { border-color: #8B0029; }
  .input-row button { background: #8B0029; color: white; border: none; padding: 10px 24px; border-radius: 24px; font-size: 15px; cursor: pointer; white-space: nowrap; }
  .input-row button:hover { background: #6d0021; }
  .input-row button:disabled { background: #ccc; cursor: not-allowed; }
  .handover-hint { text-align: center; color: #888; font-size: 13px; padding: 8px; }
  .welcome { text-align: center; padding: 40px 20px; color: #666; }
  .welcome h2 { color: #8B0029; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="header">
  <div style="width:36px;height:36px;background:white;border-radius:50%%;display:flex;align-items:center;justify-content:center;font-size:20px;">🌿</div>
  <div>
    <h1>Total Swiss 線上客服</h1>
    <span>AI 智能助理為您服務</span>
  </div>
</div>
<div class="chat" id="chat"></div>
<div class="input-area">
  <form id="form" onsubmit="sendQuestion(event)">
    <div class="input-row">
      <input type="text" id="question" placeholder="請輸入您的問題..." autocomplete="off" autofocus>
      <button type="submit" id="sendBtn">送出</button>
    </div>
  </form>
  <div class="handover-hint" id="handoverHint" style="display:none">💬 您的問題已轉交專人處理，我們會儘快回覆您！</div>
</div>
<script>
var sessionId = Math.random().toString(36).slice(2);
var chat = document.getElementById('chat');
var form = document.getElementById('form');
var input = document.getElementById('question');
var sendBtn = document.getElementById('sendBtn');
var handoverHint = document.getElementById('handoverHint');

function addMsg(role, text) {
  var div = document.createElement('div');
  div.className = 'msg ' + role;
  var time = new Date().toLocaleTimeString('zh-TW', {hour:'2-digit', minute:'2-digit'});
  div.innerHTML = '<div class="bubble">' + escapeHtml(text) + '</div><div class="time">' + time + '</div>';
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function showTyping() {
  var div = document.createElement('div');
  div.className = 'msg bot';
  div.id = 'typing';
  div.innerHTML = '<div class="bubble typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function removeTyping() {
  var t = document.getElementById('typing');
  if (t) t.remove();
}

function escapeHtml(text) {
  return String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/
/g,'<br>');
}

function sendQuestion(e) {
  e.preventDefault();
  var q = input.value.trim();
  if (!q) return;
  addMsg('user', q);
  input.value = '';
  sendBtn.disabled = true;
  showTyping();

  fetch('http://localhost:9093/api/chat_json', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: q, session_id: sessionId})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    removeTyping();
    var ans = data.answer || '抱歉，系統忙碌中，請稍後再試。';
    addMsg('bot', ans);
    if (data.handover) {
      handoverHint.style.display = 'block';
    }
  })
  .catch(function(err) {
    removeTyping();
    addMsg('bot', '抱歉，系統連線失敗，請檢查網路後再試。錯誤：' + err.message);
  })
  .finally(function() {
    sendBtn.disabled = false;
    input.focus();
  });
}

// 歡迎訊息
addMsg('bot', '您好！我是 Total Swiss 線上客服 🌿\n\n請問有什麼可以幫您？\n\n您可以問我關於：\n• 公司與產品資訊\n• 各縣市據點與聯絡方式\n• 購買方式與會員服務\n• 物流、配送與售後服務\n• 其他任何問題');
</script>
</body>
</html>
"""

@app.route("/chat")
def chat_page():
    return CHAT_TEMPLATE

# ── 路由 ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    pending = get_pending()
    return render_template_string(TEMPLATE,
        pending=pending,
        pending_count=len(pending),
        success=False
    )


@app.route("/answered")
def answered_page():
    return render_template_string(ANSWERED_TEMPLATE, answered=get_answered())


@app.route("/reply/<int:qid>", methods=["POST"])
def reply(qid):
    answer = request.form.get("answer", "").strip()
    if not answer:
        return redirect(url_for("index"))

    row = answer_question(qid, answer)
    if row:
        chat_id, user_name, question = row
        # 發給客戶
        send_telegram(chat_id,
            f"以下是 Total Swiss 專人的回覆：\n\n{answer}")
        # 通知主管（可選）
        send_telegram(int(ADMIN_ID),
            f"✅ 已回覆給 {user_name}：{answer[:100]}")
    return redirect(url_for("index"))


# ── API（給 Bot 用）───────────────────────────────────────────────────────────

@app.route("/api/pending", methods=["GET"])
def api_pending():
    """Bot 查詢待回覆數量。"""
    rows = get_pending()
    return jsonify({"count": len(rows), "questions": rows})


@app.route("/api/webhook", methods=["POST"])
def api_webhook():
    """
    Bot 收到新問題時 call 這個 API，
    把問題寫入資料庫（同時 notify 主管）。
    """
    data = request.json or {}
    save_question(
        user_id  = data.get("user_id", ""),
        user_name= data.get("user_name", ""),
        question = data.get("question", ""),
        chat_id  = int(data.get("chat_id", 0)),
        msg_id   = int(data.get("msg_id", 0)),
    )
    return jsonify({"ok": True})


# ── 啟動 ──────────────────────────────────────────────────────────────────────


@app.route("/feedback")
def feedback_page():
    """雙模式回饋頁面。"""
    return render_template_string(FEEDBACK_TEMPLATE, feedback=get_feedback(100))

@app.route("/api/feedback/<int:fid>/verdict/<mode>", methods=["POST"])
def api_feedback_verdict(fid, mode):
    verdict = request.args.get("verdict", "")
    update_verdict(fid, mode, verdict)
    return jsonify({"ok": True, "fid": fid, "mode": mode, "verdict": verdict})

@app.route("/api/feedback/sync", methods=["POST"])
def api_feedback_sync():
    try:
        count = sync_good_to_vector()
        return jsonify({"ok": True, "synced": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    print("[Supervisor Dashboard] 啟動中...")
    print("[Supervisor] http://localhost:9092/")
    print("[Supervisor] 讓主管能看到客戶問題的網頁後台")
    app.run(host="0.0.0.0", port=9092, debug=False)


