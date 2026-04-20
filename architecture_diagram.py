#!/usr/bin/env python3
"""Draw a beautiful architecture diagram for Total Swiss RAG system."""
from PIL import Image, ImageDraw, ImageFont
import math, os

# ── 顏色 ──────────────────────────────────────────────────────────────────
C = {
    "bg":         (245, 247, 250),
    "telegram":   (  0, 136, 204),
    "supervisor": (139,   0,  41),
    "app":       ( 34, 136,  78),
    "rag":       ( 15, 118, 110),
    "sub":       ( 50,  50,  80),
    "kb":        (180,  60,  60),
    "qdrant":    (108, 114, 124),
    "llm":       (139,  74, 216),
    "arrow":     (130, 150, 180),
    "dim":       (160, 170, 200),
    "light":     (200, 210, 240),
    "dark":      ( 30,  30,  30),
    "white":     (255, 255, 255),
    "yellow":    (255, 240, 200),
    "yellow_bd": (255, 200, 100),
    "orange":    (255, 153,   0),
}

W, H = 1200, 860
img = Image.new("RGBA", (W, H), C["bg"])
draw = ImageDraw.Draw(img)

# ── 字體 ───────────────────────────────────────────────────────────────────
def font(size):
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Arial.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()

FT  = font(15)   # title
FM  = font(13)   # main box
FS  = font(11)   # sub box
FD  = font(10)   # detail
FTY = font(9)    # tiny

# ── 工具函式 ────────────────────────────────────────────────────────────────
def shadow(draw, x0, y0, x1, y1, r=10, off=4):
    draw.rounded_rectangle([x0+off, y0+off, x1+off, y1+off], r, fill=(0,0,0,25))

def box(draw, x0, y0, x1, y1, fill, r=10, text1="", text2="", bd=None):
    shadow(draw, x0, y0, x1, y1, r)
    draw.rounded_rectangle([x0,y0,x1,y1], r, fill=fill, outline=bd or fill)
    cx, cy = (x0+x1)//2, (y0+y1)//2
    if text2:
        b1 = draw.textbbox((0,0), text1, font=FM)
        t1w = b1[2]-b1[0]; t1h = b1[3]-b1[1]
        b2 = draw.textbbox((0,0), text2, font=FS)
        t2w = b2[2]-b2[0]; t2h = b2[3]-b2[1]
        draw.text((cx-t1w//2, cy-t1h//2-10), text1, fill=C["white"], font=FM)
        draw.text((cx-t2w//2, cy+t1h//2+2), text2, fill=C["light"], font=FS)
    else:
        b = draw.textbbox((0,0), text1, font=FM)
        tw = b[2]-b[0]; th = b[3]-b[1]
        draw.text((cx-tw//2, cy-th//2), text1, fill=C["white"], font=FM)

def line(x0,y0,x1,y1, col=None, w=2):
    draw.line([(x0,y0),(x1,y1)], fill=col or C["arrow"], width=w)

def arr(x0,y0,x1,y1):
    """Draw an arrow from (x0,y0) to (x1,y1)"""
    line(x0,y0,x1,y1)
    dx, dy = x1-x0, y1-y0
    dist = math.sqrt(dx*dx+dy*dy)
    if dist < 1:
        return
    dx, dy = dx/dist, dy/dist
    for side in [30, -30]:
        rad = math.atan2(dy, dx)
        ax = x1 + math.cos(rad + math.radians(side)) * 9
        ay = y1 + math.sin(rad + math.radians(side)) * 9
        draw.line([(x1,y1),(ax,ay)], fill=C["arrow"], width=2)

def label(x, y, text, f=FD, col=(50,50,50)):
    b = draw.textbbox((0,0), text, font=f)
    tw = b[2]-b[0]
    draw.text((x-tw//2, y), text, fill=col, font=f)

# ════════════════════════════════════════════════════════════════════════════
# 標題
# ════════════════════════════════════════════════════════════════════════════
title = "Total Swiss 智能客服系統 — 系統架構圖"
b = draw.textbbox((0,0), title, font=FT)
tw = b[2]-b[0]
draw.text(((W-tw)//2, 16), title, fill=C["dark"], font=FT)
draw.line([(60,52),(W-60,52)], fill=(139,0,41), width=3)

# ════════════════════════════════════════════════════════════════════════════
# 第一層：客戶端
# ════════════════════════════════════════════════════════════════════════════
Y1 = 75
clients = [
    ( 90, "💬 Telegram Bot",  "@Total_Swiss_bot"),
    (430, "🌐 公開客服網頁",   "http://.../chat"),
    (745, "👤 主管後台",        "http://.../（管理員）"),
]
for cx, lb, sub in clients:
    box(draw, cx, Y1, cx+210, Y1+65, C["telegram"], text1=lb, text2=sub)
    arr(cx+105, Y1+65, cx+105, Y1+90)

# ════════════════════════════════════════════════════════════════════════════
# 第二層：Bot / Supervisor
# ════════════════════════════════════════════════════════════════════════════
Y2 = 152
box(draw,  60, Y2, 315, Y2+72, C["telegram"],   text1="📱 telegram_bot.py",   text2="長輪詢接收 Telegram 訊息")
box(draw, 430, Y2, 675, Y2+72, C["supervisor"],  text1="🖥️  supervisor.py",    text2="主管後台 :9092  +  公開 /chat 網頁")
box(draw, 760, Y2, 960, Y2+72, C["app"],         text1="⚡  app.py（FastAPI）", text2=":9093  REST API 入口")

# supervisor → app.py
arr(552, Y2, 552, Y2+18)
arr(760, Y2+36, 675, Y2+36)
arr(675, Y2+36, 675, Y2+18)

# telegram → app.py（斜線）
line(187, Y2, 187, Y2-10, 1)
line(187, Y2-10, 852, Y2-10, 1)
line(852, Y2-10, 852, Y2+18, 1)

# ════════════════════════════════════════════════════════════════════════════
# 第三層：rag.py
# ════════════════════════════════════════════════════════════════════════════
Y3 = 275
box(draw, 300, Y3, 720, Y3+72, C["rag"], text1="🧠  rag.py — RAG 核心引擎", text2="回答生成  /  轉主管判斷  /  反饋寫庫")
arr(510, Y3+72, 510, Y3+90)

# ════════════════════════════════════════════════════════════════════════════
# 第四層：rag.py 三大子模組
# ════════════════════════════════════════════════════════════════════════════
Y4 = 412
subs = [
    ( 60, "📚 知識庫",        "load_kb_text()"),
    (370, "🌐 網路搜尋",     "web_search()"),
    (680, "🤖 LLM 呼叫",      "ask_llm()"),
]
for bx, lb, fn in subs:
    box(draw, bx, Y4, bx+255, Y4+80, C["sub"], text1=lb, text2=fn)
    arr(bx+127, Y3+72, bx+127, Y4+80)

# 知識庫底下四個 md 檔
YKD = Y4 + 95
kbs = [
    ( 60,  "01_公司簡介.md",  C["kb"]),
    (200,  "02_產品資訊.md",  ( 60, 100, 180)),
    (340,  "03_常見問題.md",  ( 60, 130,  80)),
    (480,  "04_媒體報導.md",  (160, 100, 200)),
]
for bx, name, col in kbs:
    draw.rounded_rectangle([bx, YKD, bx+130, YKD+38], 6, fill=(40,40,60))
    b = draw.textbbox((0,0), name, font=FTY)
    tw = b[2]-b[0]
    draw.text((bx+65-tw//2, YKD+11), name, fill=(200,215,240), font=FTY)
    arr(bx+65, Y4+80, bx+65, YKD)

# ════════════════════════════════════════════════════════════════════════════
# 第五層：Qdrant（左下）
# ════════════════════════════════════════════════════════════════════════════
YQ = 635
box(draw, 60, YQ, 280, YQ+72, C["qdrant"], text1="🗄️  Qdrant", text2="向量資料庫  :6333")
line(315, Y4+40, 280, YQ+36, col=C["dim"], w=1)

# ════════════════════════════════════════════════════════════════════════════
# 第五層：LLM 引擎（右上豎長方）
# ════════════════════════════════════════════════════════════════════════════
YLLM = 90
box(draw, 980, YLLM, 1170, YLLM+315, C["llm"], text1="🧬  LLM 引擎", text2="MiniMax / Anthropic / OpenAI")

llm_items = [
    ("Provider",   "MiniMax（預設）"),
    ("Endpoint",   "/text/chatcompletion_v2"),
    ("Model",      "MiniMax-M2.7"),
    ("Temperature","0.3（穩定輸出）"),
    ("Max Tokens", "1024"),
    ("Fallback",  "Anthropic / OpenAI"),
]
for k, (k_, v) in enumerate(llm_items):
    ky = YLLM + 72 + k * 38
    draw.text((990, ky),   k_+":",  fill=C["light"], font=FTY)
    draw.text((990, ky+14), v,     fill=C["white"], font=FD)

# rag → llm
line(720, Y3+36, 980, YLLM+157, col=C["dim"], w=1)
arr(980, YLLM+157, 950, YLLM+157)

# ════════════════════════════════════════════════════════════════════════════
# 第六層：回答模式說明（右下）
# ════════════════════════════════════════════════════════════════════════════
YMODE = 635
draw.rounded_rectangle([730, YMODE, 1160, YMODE+205], 10,
                         fill=(248,250,255), outline=(200,210,230))
draw.text((748, YMODE+10), "回答模式（RAG_METHOD）", fill=(30,60,120), font=FM)

modes = [
    ("prompt（預設）", "知識庫全文塞進 prompt，15-30 秒，無需 Qdrant", C["app"]),
    ("vector",         "Qdrant 向量檢索，需先建索引（indexer.py）",    C["qdrant"]),
    ("dual",           "兩者並行取高分者，慢但嚴謹",                   C["rag"]),
]
for j, (mode, desc, col) in enumerate(modes):
    my = YMODE + 44 + j * 52
    draw.rounded_rectangle([738, my, 838, my+34], 6, fill=col)
    draw.text((743, my+8), mode, fill=C["white"], font=FD)
    draw.text((845, my+8), desc, fill=(50,50,50), font=FTY)

# ════════════════════════════════════════════════════════════════════════════
# 第七層：轉主管決策（底部）
# ════════════════════════════════════════════════════════════════════════════
YFLOW = 790
draw.rounded_rectangle([270, YFLOW, 930, YFLOW+52], 8,
                         fill=C["yellow"], outline=C["yellow_bd"])
draw.text((285, YFLOW+16),
          "答案含糊 或 分數 < 0.25  →  轉主管  →  寫入 chat_history.db  →  主管後台通知",
          fill=(140,90,20), font=FD)
arr(510, Y3+72, 510, YFLOW+52)

# ── 儲存 ──────────────────────────────────────────────────────────────────
out = "/Users/apple/clawd-kaedebot/rag/架構圖.png"
img.save(out, "PNG")
print(f"Saved: {out}  ({W}x{H})")
