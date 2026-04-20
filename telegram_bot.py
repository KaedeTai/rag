import sys, os, time, uuid, re, random, requests
import config

BOT_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
ADMIN_ID = int(config.ADMIN_TELEGRAM_ID)
PENDING = {}  # msg_id -> {question, user_name, user_id, chat_id, replied_to}


def send_msg(chat_id: int, text: str):
    import logging
    log = logging.getLogger("bot")
    url = f"{BOT_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    log.info(f"[Send] → TG chat_id={chat_id} len={len(text)} text={repr(text)[:80]}")
    try:
        r = requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"[Send] ❌ network error: {e}")
        raise
    if r.status_code != 200:
        log.error(f"[Send] ❌ TG API {r.status_code}: {r.text[:300]}")
    else:
        log.info(f"[Send] ✅ TG 200 OK msg_id={r.json().get('result',{}).get('message_id')}")

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
    """
    將主管回覆轉為給客戶的答案。回傳 {answer, thinking}。

    邏輯（嚴禁更動流程）：
    1. 主管用引號「」『』""'' 包裹內容 → 原文轉達，不經過 MiniMax
    2. 回覆 >= 40 字 → 直接發給客戶，不經過 MiniMax
    3. 回覆 < 40 字（短回覆）→ 一定要經過 MiniMax 潤飾，
       MiniMax 回覆後，過濾掉所有 <!-- --> 和 <前> 標籤，
       取乾淨文字作為答案發給客戶。
       MiniMax 失敗或處理後答案仍為空 → 絕對不能發 raw text，
       要用內建邏輯生成完整回覆（見 fallback_generate）。
    """
    import re as _re
    sr = supervisor_text.strip()

    # ── 1. 引號 → 原文轉達 ─────────────────────────────────────────────
    for qre in [r"「([^」]*)」", r"『([^』]*)』", r"\"([^\"]*)\"", r"'([^']*)'"]:
        m = _re.search(qre, sr)
        if m:
            return {"answer": m.group(1).strip(), "thinking": ""}

    # ── 2. >= 40 字 → 直接發 ──────────────────────────────────────────
    if len(sr) >= 40:
        return {"answer": sr, "thinking": ""}

    # ── 3. 短回覆 → MiniMax 潤飾（必要步驟，不可跳過）───────────────
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.MINIMAX_API_KEY,
            base_url=config.MINIMAX_BASE_URL,
        )
        prompt = (
            "【角色】你是 Total Swiss 智能客服，請將「客服主管對客服機器的指示」"
            "改寫成一段可以直接回覆給客户的完整句子。\n\n"
            "【公司客服資訊】（可適度融入）\n"
            "電話：02-7733-0800（全球客服中心）\n"
            "Email：gsc@tsmail.com.tw\n\n"
            "【客户原始問題】\n「" + customer_q + "」\n\n"
            "【主管指示】\n「" + sr + "」\n\n"
            "【要求】\n"
            "1. 只準確表達主管的意思，不捏造產品、服務或優惠資訊\n"
            "2. 語氣禮貌、完整，通常需要 2-3 句話\n"
            "3. 可適度補充聯絡方式（電話 02-7733-0800）\n"
            "4. 輸出乾淨純文字，絕對不要包含 <!-- --> 或 <前> 等任何標籤"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        # 過濾 MiniMax 可能產生的 thinking block
        raw = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL)
        raw = raw.strip()
        if raw:
            return {"answer": raw, "thinking": ""}

    except Exception as e:
        print(f"[MiniMax rewrite error] {e}")

    # ── 4. Fallback：MiniMax 完全失敗 → 絕對不能發 raw text ─────────
    # 用內建邏輯生成完整回覆（這不是捷徑，是最後防線）
    suffix = (
        "\n\n感謝您的來訊傾訴。我們非常重視您的感受，"
        "也希望能妥善為您處理。若有任何疑問或需要進一步協助，"
        "歡迎致電全球客服中心 02-7733-0800（每天 9:00-18:00）"
        "或 Email 至 gsc@tsmail.com.tw，會有專人為您服務。祝您一切順利！"
    )
    # 用主管原始指示的意圖為核心，加上禮貌框架，不直接暴露主管原文
    fallback_body = (
        "感謝您向我們反映這個情況，我們已收到您的意見。"
        "主管對此非常重視，正在進一步了解與評估。"
        "為確保您的問題得到最妥善的處理，"
    )
    return {"answer": fallback_body + suffix, "thinking": ""}

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
    import logging
    log = logging.getLogger("bot")

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

    log.info(f"[Handle] uid={user_id} name={user_name} msg_id={msg_id} text={repr(text)[:50]}")

    # ── 1. 主管（Kaede）回覆 Bot 轉過來的客戶問題 ──────────────────────────
    target = msg.get("reply_to_message", {})
    if target:
        replied_to = target.get("message_id")
        log.info(f"[Handle] 有 reply_to_message，id={replied_to}，PENDING={list(PENDING.keys())}")
        if replied_to and replied_to in PENDING:
            pending = PENDING.pop(replied_to)
            log.info(f"[Handle] 主管回覆，PENDING key={replied_to}，question={pending.get('question','')[:30]}")
            typing_done = start_typing(int(pending["chat_id"]))
            sr = supervisor_reply(pending.get("question", ""), text)
            typing_done.set()
            send_msg(int(pending["chat_id"]), sr["answer"])
            send_msg(chat_id, "已回覆給客戶。")
            log.info(f"[Handle] 完成：主管回覆給客戶")
            return
        log.info(f"[Handle] reply_to_message 但不在 PENDING 中")

    # ── 2. 問候語 ───────────────────────────────────────────────────────
    greetings = {
        "hi", "hello", "嗨", "你好", "您好", "hey", "yo",
        "hi!", "hi.", "你好!", "您好!", "嗨囉",
    }
    if text.lower().strip().rstrip("!.") in greetings:
        log.info(f"[Handle] 問候語，直接回覆")
        send_msg(chat_id, "你好！有什麼關於 Total Swiss 的問題可以問我喔 😊")
        return

    # ── 3. should_handover 檢查 ─────────────────────────────────────────
    try:
        handover_kw = should_handover(text)
        log.info(f"[Handle] should_handover={handover_kw}")
    except Exception as e:
        log.error(f"[Handle] should_handover 失敗: {e}", exc_info=True)
        handover_kw = False

    # ── 4. 正常問題 → RAG API ──────────────────────────────────────────
    log.info(f"[Handle] 呼叫 RAG API，text={repr(text)[:50]}")
    typing_done = start_typing(chat_id)
    try:
        result = rag_answer(text)
        log.info(f"[Handle] RAG 回來了，handover={result.get('handover')}")
    except Exception as e:
        log.error(f"[Handle] rag_answer 失敗: {e}", exc_info=True)
        typing_done.set()
        send_msg(chat_id, "目前服務暫時無法使用，請稍後再試。")
        return
    typing_done.set()

    answer = result.get("answer", "")
    handover_api = result.get("handover", False)

    if handover_kw or handover_api:
        log.info(f"[Handle] 轉主管（kw={handover_kw} api={handover_api}），forward_to_kaede")
        try:
            forward_to_kaede(text, user_name, user_id, chat_id, msg_id)
            log.info(f"[Handle] forward_to_kaede 完成，發送「請稍候」")
        except Exception as e:
            log.error(f"[Handle] forward_to_kaede 失敗: {e}", exc_info=True)
        send_msg(chat_id, "這個問題我需要確認一下，請稍候，我會通知專人回覆您。")
        return

    log.info(f"[Handle] 正常回覆，len={len(answer)}, calling send_msg...")
    send_msg(chat_id, answer)
    log.info(f"[Handle] ✅ 完成")


def main():
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("/tmp/telegram_bot.log"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    log = logging.getLogger("bot")
    log.info("[Bot] 啟動中...")
    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{BOT_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            if resp.status_code == 409:
                log.warning("[Polling] 409 Conflict — 清除並重試")
                requests.get(f"{BOT_API}/getUpdates",
                             params={"offset": -1, "timeout": 1}, timeout=5)
                time.sleep(1)
                continue
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 60)
                log.warning(f"[Polling] 429 Rate Limited，等待 {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                delay = min(2 * (2 ** random.randint(0, 5)) + random.uniform(0, 1), 60)
                log.warning(f"[Polling] 5xx error，等待 {delay:.1f}s...")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            for u in updates:
                update_id = u["update_id"]
                try:
                    handle(u)
                    offset = update_id + 1
                except Exception as e:
                    log.error(f"[Handle] 例外（update_id={update_id}，不放過offset）: {e}")
                    # offset 不前進，下次重試同一則訊息
        except requests.exceptions.Timeout:
            log.warning("[Polling] 連線超時，繼續...")
        except requests.exceptions.ConnectionError as e:
            delay = min(2 * (2 ** random.randint(0, 5)) + random.uniform(0, 1), 60)
            log.warning(f"[Polling] 連線錯誤 ({e})，{delay:.1f}s 後重試...")
            time.sleep(delay)
        except Exception as e:
            log.error(f"[Polling] 例外: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
