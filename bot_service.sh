#!/bin/bash
# bot_service.sh — Telegram Bot 服務管理
# 用法：./bot_service.sh start | stop | restart | status

WORKDIR="/Users/apple/clawd-kaedebot/rag"
PID_FILE="/tmp/telegram_watchdog.pid"
LOG_FILE="/tmp/watchdog.log"

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        # 檢查 PID 是否真的在跑
        kill -0 "$PID" 2>/dev/null && return 0
    fi
    return 1
}

do_start() {
    if is_running; then
        echo "Bot 已在運行（PID=$(cat $PID_FILE)）"
        return 1
    fi
    echo "啟動 Bot..."
    cd "$WORKDIR"
    python3 -u bot_watchdog.py > "$LOG_FILE" 2>&1 &
    sleep 3
    if is_running; then
        echo "Bot 啟動成功（PID=$(cat $PID_FILE)）"
    else
        echo "Bot 啟動失敗，查看日誌：tail $LOG_FILE"
    fi
}

do_stop() {
    if ! is_running; then
        echo "Bot 未運行"
        return 0
    fi
    echo "停止 Bot..."
    PID=$(cat "$PID_FILE")
    kill -INT "$PID" 2>/dev/null
    sleep 3
    if ! is_running; then
        echo "Bot 已停止"
    else
        echo "Bot 來不及停止，強制殺掉..."
        kill -9 "$PID" 2>/dev/null
        sleep 1
        rm -f "$PID_FILE"
        echo "Bot 已強制停止"
    fi
}

do_status() {
    if is_running; then
        echo "✅ Bot 運行中（PID=$(cat $PID_FILE)）"
        if [ -f "$LOG_FILE" ]; then
            echo "--- 最近日誌 ---"
            tail -5 "$LOG_FILE"
        fi
    else
        echo "❌ Bot 未運行"
    fi
}

case "$1" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_stop
        sleep 2
        do_start
        ;;
    status)
        do_status
        ;;
    *)
        echo "用法：$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
