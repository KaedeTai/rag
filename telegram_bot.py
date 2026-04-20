import sys, os, time, uuid, re, random, requests
import config

BOT_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
ADMIN_ID = int(config.ADMIN_TELEGRAM_ID)
PENDING = {}  # msg_id -> {question, user_name, user_id, chat_id, replied_to}


def send_msg(chat_id: int, text: str):
    url = f"{BOT_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()

def send_typing(chat_id: int):
    """發送 typing 狀態（Telegram 會維持數秒，需定期重發才不會消失）。"""
    try:
        requests.post(
            f"{BOT_API}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass

import threading as _th

def _typing_loop(chat_id: int, done_event):
    """背景執行緒：每 3 秒重發一次 typing，直到 done_event 觸發。"""
    while not done_event.wait(3):
        try:
            requests.post(
                f"{BOT_API}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5,
            )
        except Exception:
            pass

def start_typing(chat_id: int) -> _th.Event:
    """開始在背景維持 typing 狀態。回傳 done_event，處理完 call done_event.set()。"""
    done = _th.Event()
    t = _th.Thread(target=_typing_loop, args=(chat_id, done), daemon=True)
    t.start()
    return done


def should_handover(question: str) -> bool:
    """檢查是否需要轉人工（敏感關鍵字）。"""
    q = question.lower()
    return any(kw.lower() in q for kw in config.HUMAN_HANDOVER_KEYWORDS)


def forward_to_kaede(question: str, user_name: str, user_id: str, chat_id: int, replied_to: int):
    """
    將客戶問題轉給主管（Kaede）。

    重要：PENDING 的 key 是「Bot 發給主管的那條訊息的 ID」，
    不是客戶原本訊息的 ID。
    因為當主管回覆時，reply_to_message.message_id 會指向
    「主管看到的那條 Bot 訊息」的 ID。
    """
    kb_hint = f"（來自 {user_name}，TG ID {user_id}）"
    # 發送並取得訊息 ID，這個 ID 才是在 PENDING 中要用的那個
    msg_to_admin = f"{kb_hint}\n\n客戶問題：{question}"
    url = f"{BOT_API}/sendMessage"
    r = requests.post(url, json={"chat_id": ADMIN_ID, "text": msg_to_admin}, timeout=10)
    r.raise_for_status()
    admin_msg_id = r.json()["result"]["message_id"]
    PENDING[admin_msg_id] = {
        "question": question,
        "user_name": user_name,
        "user_id": user_id,
        "chat_id": chat_id,
        "time": time.time(),
    }


def clean_thinking(raw: str) -> str:
    import re
    parts = re.split(r"itz", raw, flags=re.IGNORECASE)
    if len(parts) > 1:
        return parts[-1].strip()
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def rag_answer(question: str) -> dict:
    """呼叫本地 RAG API。"""
    try:
        url = "http://127.0.0.1:9093/api/chat_json"
        r = requests.post(
            url,
            json={"question": question, "session_id": str(uuid.uuid4())},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[RAG API error] {e}")
        return {"answer": "目前服務暫時無法使用，請稍後再試。", "handover": True}


def supervisor_reply(customer_q: str, supervisor_text: str) -> dict:
    """將主管回覆轉為給客戶的答案。回傳 {answer, thinking}。"""
    import re as _re
    sr = supervisor_text.strip()
    # 1. 有引號 → 原文轉達
    for qre in [r"「([^」]*)」", r"『([^』]*)』", r"\"([^\"]*)\"", r"'([^']*)'"]:
        m = _re.search(qre, sr)
        if m:
            return {"answer": m.group(1).strip(), "thinking": ""}
    # 2. 長回覆 >=40 字 → 直接給客戶
    if len(sr) >= 40:
        return {"answer": sr, "thinking": ""}
    # 3. 短回覆 → MiniMax 擴充
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.MINIMAX_API_KEY,
            base_url=config.MINIMAX_BASE_URL,
        )
        prompt = (
            "客戶問：「" + customer_q + "」\n"
            "主管答：「" + sr + "」\n\n"
            "請根據主管的答覆，用一句完整句子，直接回答客戶。\n"
            "要求：只準確表達主管的意思，不添加任何新資訊。"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        thinking = "".join(_re.findall(r"<think>.*?</think>", raw, flags=_re.DOTALL))
        answer = clean_thinking(raw)
        return {"answer": answer if answer else sr, "thinking": thinking}
    except Exception as e:
        print(f"[MiniMax rewrite error] {e}")
        return {"answer": sr, "thinking": ""}


def is_answer_sufficient(question: str, answer: str) -> bool:
    """用 MiniMax 判斷答案是否充分。True = 需轉主管。"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.MINIMAX_API_KEY,
            base_url=config.MINIMAX_BASE_URL,
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "用戶問題：「" + question + "」\n"
                    "客服回答：「" + answer + "」\n\n"
                    "請問這個回答是否充分？\n"
                    "「是」= 充分。\n"
                    "「否」= 不充分。\n"
                    "請只回答「是」或「否」。"
                )
            }],
            max_tokens=500,
        )
        verdict = clean_thinking(resp.choices[0].message.content or "").strip()
        return "否" in verdict
    except Exception:
        return True


def handle(update: dict):
    """
    收到 Telegram update 的處理邏輯。

    訊息類型：
    1. 主管（Kaede）回覆 Bot 轉過來的客戶問題
       → 條件：sender_id == ADMIN_ID AND 該訊息有 reply_to_message AND 該 reply_to_message 的 ID 在 PENDING 裡
       → 處理：將主管回覆轉成客戶答案，發給原客戶，告知主管「已回覆」

    2. 主管（Kaede）發的一般訊息（非回覆）
       → 條件：sender_id == ADMIN_ID AND 沒有 reply_to_message
       → 處理：直接忽略（不做任何處理）

    3. 客戶問候語
       → 條件：訊息內容是問候語
       → 處理：直接回覆問候

    4. 客戶一般問題
       → 條件：非主管、非問候
       → 處理：呼叫 RAG API，根據 handover 欄位決定直接回或轉主管
    """
    if "message" not in update:
        return
    msg = update["message"]
    msg_id = msg["message_id"]
    text = msg.get("text", "").strip()
    if not text:
        return

    chat_id = msg["chat"]["id"]
    user = msg["from"]
    user_id = str(user["id"])
    user_name = user.get("first_name", "用戶")

    # ── 1. 主管（Kaede）回覆 Bot 轉過來的客戶問題 ──────────────────────────
    # 主管用「回覆」功能回覆 Bot 訊息時，會攜帶 reply_to_message 欄位。
    # 若該 ID 在 PENDING，代表這是主管在回覆一個待處理的客戶問題。
    target = msg.get("reply_to_message", {})
    if target:
        replied_to = target.get("message_id")
        print(f"[Handle] 有 reply_to_message，id={replied_to}，PENDING keys={list(PENDING.keys())}")
        replied_to = target.get("message_id")
        if replied_to and replied_to in PENDING:
            pending = PENDING.pop(replied_to)
            send_typing(int(pending["chat_id"]))
            print(f"[Handle] 主管回覆，PENDING key={replied_to}，客戶問題={pending.get('question','')[:20]}")
            print(f"[Handle] 主管回覆，PENDING key={replied_to}，客戶問題={pending.get('question','')[:20]}")
            sr = supervisor_reply(pending.get("question", ""), text)
            done.set()
            send_msg(int(pending["chat_id"]), sr["answer"])
            send_msg(chat_id, "已回覆給客戶。")
            return

    # ── 2. （已移除）原本這裡會忽略主管直接訊息 ────────────────────────────
    # 拿掉這個邏輯：即使是 ADMIN，如果訊息不是回覆 PENDING，就當成一般客戶問題處理。
    # 否則 ADMIN 自己測試 Bot 時完全沒反應。

    # ── 3. 問候語 ───────────────────────────────────────────────────────
    greetings = {
        "hi", "hello", "嗨", "你好", "您好", "hey", "yo",
        "hi!", "hi.", "你好!", "您好!", "嗨囉",
    }
    if text.lower().strip().rstrip("!.") in greetings:
        send_msg(chat_id, "你好！有什麼關於 Total Swiss 的問題可以問我喔 😊")
        return

    # ── 4. 正常問題 → RAG API ──────────────────────────────────────────
    # 顯示 typing 狀態（正在思考答案）
    done = start_typing(chat_id)
    result = rag_answer(text)
    done.set()
    answer = result.get("answer", "")
    handover = result.get("handover", False)

    if should_handover(text) or handover:
        forward_to_kaede(text, user_name, user_id, chat_id, msg_id)
        send_msg(chat_id, "這個問題我需要確認一下，請稍候，我會通知專人回覆您。")
        return

    send_msg(chat_id, answer)


def main():
    print("[Bot] 啟動中...")
    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{BOT_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            if resp.status_code == 409:
                requests.get(f"{BOT_API}/getUpdates",
                             params={"offset": -1, "timeout": 1}, timeout=5)
                time.sleep(1)
                continue
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 60)
                print(f"[Polling] 429 Rate Limited，等待 {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                delay = min(2 * (2 ** random.randint(0, 5)) + random.uniform(0, 1), 60)
                time.sleep(delay)
                continue
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            if updates:
                print(f"[Polling] 收到 {len(updates)} 個更新")
            for u in updates:
                offset = u["update_id"] + 1
                handle(u)
        except requests.exceptions.Timeout:
            print("[Polling] 連線超時，繼續...")
        except requests.exceptions.ConnectionError as e:
            delay = min(2 * (2 ** random.randint(0, 5)) + random.uniform(0, 1), 60)
            print(f"[Polling] 連線錯誤 ({e})，{delay:.1f}s 後重試...")
            time.sleep(delay)
        except Exception as e:
            print(f"[Polling] 例外 ({e})，5s 後重試...")
            time.sleep(5)


if __name__ == "__main__":
    main()
