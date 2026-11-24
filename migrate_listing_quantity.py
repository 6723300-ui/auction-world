import sqlite3
from database import DB_PATH

backup_path = DB_PATH.with_name("game_data_before_quantity_change.db")

if backup_path.exists():
    raise RuntimeError("백업 파일이 이미 있습니다. 중복 실행 여부를 확인하세요.")

connection = sqlite3.connect(DB_PATH)
backup = sqlite3.connect(backup_path)

try:
    connection.backup(backup)
finally:
    backup.close()

try:
    connection.execute("BEGIN IMMEDIATE")

    connection.execute("""
        CREATE TABLE listings_new(
        listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller TEXT NOT NULL CHECK(length(seller) > 0),
        item_name TEXT NOT NULL CHECK(length(item_name) > 0),
        category TEXT NOT NULL
            CHECK(category IN('무기','방어구','소비','기타')),
        price INTEGER NOT NULL CHECK(price > 0),
        quantity INTEGER NOT NULL CHECK(quantity >= 0),
        status TEXT NOT NULL DEFAULT '판매중'
            CHECK(status IN('판매중','판매완료','취소')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        INSERT INTO listings_new(
            listing_id, seller, item_name, category,
            price, quantity, status, created_at
        )
        SELECT
            listing_id, seller, item_name, category,
            price, quantity, status, created_at
        FROM listings
    """)

    connection.execute("DROP TABLE listings")
    connection.execute("ALTER TABLE listings_new RENAME TO listings")
    connection.commit()
    
    print("완료: 기존 판매 정보를 유지하면서 수량을 0을 허용했습니다.")

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()

