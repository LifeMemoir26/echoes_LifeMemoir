"""
migrate_chunks_db.py — 为已有用户的 chunks.db 创建 sqlite-vec + FTS5 虚拟表
幂等：可多次运行，不会影响已有数据

用法：
    python backend/scripts/migrate_chunks_db.py

会自动遍历 data/*/chunks.db
"""

import sqlite3
import sys
from pathlib import Path


def migrate_db(db_path: Path) -> None:
    print(f"迁移: {db_path}")
    conn = sqlite3.connect(str(db_path))

    # 尝试加载 sqlite-vec
    vec_available = False
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        vec_available = True
        print("  sqlite-vec 加载成功")
    except Exception as e:
        print(f"  WARNING: sqlite-vec 不可用，跳过 chunks_vec: {e}")

    cursor = conn.cursor()

    if vec_available:
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                    summary_id INTEGER PRIMARY KEY,
                    embedding FLOAT[768]
                )
            """)
            print("  chunks_vec 虚拟表已就绪")
        except Exception as e:
            print(f"  WARNING: chunks_vec 创建失败: {e}")

    try:
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                content='summaries',
                content_rowid='summary_id',
                tokenize='unicode61'
            )
        """)
        print("  chunks_fts 虚拟表已就绪")
    except Exception as e:
        print(f"  WARNING: chunks_fts 创建失败: {e}")

    conn.commit()
    conn.close()
    print(f"  完成: {db_path}")


def main():
    # 确定 data 目录
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent.parent / "data"

    if not data_dir.exists():
        print(f"data 目录不存在: {data_dir}")
        sys.exit(0)

    db_files = list(data_dir.glob("*/chunks.db"))
    if not db_files:
        print("未发现任何 chunks.db 文件，无需迁移。")
        sys.exit(0)

    print(f"发现 {len(db_files)} 个 chunks.db 文件")
    for db_path in db_files:
        migrate_db(db_path)

    print("\n全部迁移完成。")


if __name__ == "__main__":
    main()
