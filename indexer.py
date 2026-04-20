#!/usr/bin/env python3
"""
indexer.py — 建立知識庫索引
======================
把文件資料轉成向量，存進 Qdrant 向量資料庫。

用法：
  python3 indexer.py docs/              # 把整個資料夾的 txt/md/pdf 全部索引
  python3 indexer.py --add "文字內容" "來源：員工手冊"   # 單筆新增
  python3 indexer.py --stats         # 查看現有索引統計
  python3 indexer.py --clear          # 清空索引
"""
import sys, os, glob, argparse, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rag, config

CHUNK_SIZE = 500  # 每個 chunk 的字數


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = 50):
    """把長文字切成 overlapping chunks。"""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start:start + size])
        chunks.append(chunk)
        start += size - overlap
    return chunks


def extract_text_from_file(path: str) -> str:
    """根據副檔名抽取文字。"""
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".txt":
        return open(path, encoding="utf-8").read()

    if ext == ".md":
        return open(path, encoding="utf-8").read()

    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            print("⚠️  pypdf 未安裝，無法處理 PDF。請執行：pip install pypdf")
            return ""

    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            print("⚠️  python-docx 未安裝，無法處理 Word。請執行：pip install python-docx")
            return ""

    if ext in (".csv",):
        import csv
        with open(path, encoding="utf-8") as f:
            return "\n".join(" ".join(row) for row in csv.reader(f))

    return ""


def index_directory(dir_path: str, recursive: bool = True):
    """把資料夾內所有文件建立索引。"""
    patterns = ["*.txt", "*.md", "*.pdf"]
    if recursive:
        patterns = ["**/" + p for p in patterns]

    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(dir_path, pat), recursive=recursive))

    files = [f for f in files if not f.startswith(".")]  # 跳過隱藏檔
    print(f"找到 {len(files)} 個檔案\n")

    all_docs = []
    for f in files:
        print(f"處理：{f}")
        text = extract_text_from_file(f)
        if not text.strip():
            print("  → 無法抽取內容，跳過")
            continue
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            all_docs.append({
                "content": chunk,
                "source": f"{Path(f).name} [chunk {i+1}/{len(chunks)}]",
            })
        print(f"  → {len(chunks)} chunks")

    if all_docs:
        print(f"\n共 {len(all_docs)} 個 chunks，開始向量化和寫入 Qdrant...")
        rag.add_documents(all_docs)
        print(f"✅ 完成！寫入 {len(all_docs)} 個文件到向量資料庫。")
    else:
        print("沒有找到可處理的檔案。")


def stats():
    """顯示索引狀態。"""
    try:
        qc = rag.get_qdrant()
        info = qc.get_collection(config.COLLECTION_NAME)
        print(f"Collection: {config.COLLECTION_NAME}")
        print(f"向量數量：{info.points_count}")
        print(f"向量維度：{info.config.params.vec.size}")
    except Exception as e:
        print(f"無法取得 Collection 資訊：{e}")


def clear():
    """清空 Collection。"""
    try:
        qc = rag.get_qdrant()
        qc.delete_collection(config.COLLECTION_NAME)
        print("✅ 已清空索引。")
    except Exception as e:
        print(f"清空失敗：{e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="知識庫索引工具")
    ap.add_argument("path", nargs="?", help="資料夾路徑")
    ap.add_argument("--add", nargs=2, metavar=("CONTENT", "SOURCE"),
                     help="新增單筆文件：python3 indexer.py --add '內容' '來源'")
    ap.add_argument("--stats", action="store_true", help="顯示索引統計")
    ap.add_argument("--clear", action="store_true", help="清空所有索引")
    ap.add_argument("--chunk-size", type=int, default=CHUNK_SIZE,
                     help=f"每個 chunk 的字數（預設 {CHUNK_SIZE}）")
    args = ap.parse_args()

    if args.stats:
        stats()
    elif args.clear:
        clear()
    elif args.add:
        content, source = args.add
        rag.add_documents([{"content": content, "source": source}])
        print(f"✅ 已新增：{source}")
    elif args.path:
        rag.init_collection()
        index_directory(args.path)
    else:
        ap.print_help()
