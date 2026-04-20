#!/usr/bin/env python3
"""bot_watchdog.py — 簡單的 Bot watchdog daemon，自動重啟崩潰的 Bot。"""
import subprocess, time, signal, sys, os

BOT_CMD = ["python3", "-u", "/Users/apple/clawd-kaedebot/rag/telegram_bot.py"]
proc = None
RESTART_DELAY = 5
pid_file = "/tmp/telegram_watchdog.pid"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[Watchdog {ts}] {msg}", flush=True)

def start():
    global proc
    # 確保舊的已結束
    if proc and proc.poll() is None:
        log("舊 Bot 還在跑，先殺掉...")
        proc.terminate()
        proc.wait()
    log("啟動 Bot...")
    proc = subprocess.Popen(BOT_CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log(f"Bot PID: {proc.pid}")

def signal_handler(sig, frame):
    log("收到退出訊號，關閉 Bot...")
    if proc:
        proc.terminate()
        proc.wait()
    if os.path.exists(pid_file):
        os.remove(pid_file)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def run():
    log("Watchdog 啟動")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    start()
    restarts = 0
    while True:
        line = proc.stdout.readline()
        if line:
            sys.stdout.write(line.decode(errors="replace"))
            sys.stdout.flush()
        elif proc.poll() is not None:
            restarts += 1
            log(f"Bot 已退出 (exit={proc.returncode})，{RESTART_DELAY} 秒後重啟（第 {restarts} 次）")
            time.sleep(RESTART_DELAY)
            start()

if __name__ == "__main__":
    run()
