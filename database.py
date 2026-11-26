import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / 'game_data.db'


def get_connection():
    connection = sqlite3.connect(DB_PATH,timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database():
    connection = get_connection()
    try:
        with connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller TEXT NOT NULL CHECK(length(seller) > 0),
                    buyer TEXT NOT NULL CHECK(length(buyer) > 0),
                    item_name TEXT NOT NULL CHECK(length(item_name) > 0),
                    price INTEGER NOT NULL CHECK(price > 0),
                    quantity INTEGER NOT NULL CHECK(quantity > 0)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS listings(
                  listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller TEXT NOT NULL CHECK(length(seller)>0),
                    item_name TEXT NOT NULL CHECK(length(item_name)>0),
                    category TEXT NOT NULL
                        CHECK(category IN ('무기','방어구','소비','기타')),
                    price INTEGER NOT NULL CHECK(price > 0),
                    quantity INTEGER NOT NULL CHECK(quantity >= 0),
                    status TEXT NOT NULL DEFAULT '판매중'
                        CHECK(status IN ('판매중','판매완료','취소')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY NOT NULL
                    CHECK(length(username)>0),
                balance INTEGER NOT NULL DEFAULT 0
                    CHECK(balance >= 0)
                    )
            ''')  

            connection.execute('''
                CREATE TABLE IF NOT EXISTS user_credentials (
                    username TEXT PRIMARY KEY NOT NULL
                        REFERENCES users(username) ON DELETE CASCADE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            connection.execute('''
                CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY NOT NULL,
                username TEXT NOT NULL
                    REFERENCES users(username) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
                )
            ''')

            connection.execute('''
                CREATE TABLE IF NOT EXISTS account_emails(
                    username TEXT PRIMARY KEY NOT NULL
                        REFERENCES users(username) ON DELETE CASCADE,
                    email TEXT NOT NULL UNIQUE,
                    verified_at INTEGER NOT NULL
                    )
            ''')

            connection.execute('''
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                token_hash TEXT PRIMARY KEY NOT NULL,
                username TEXT NOT NULL UNIQUE
                    REFERENCES users(username) ON DELETE CASCADE,
                email TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
                )
            ''')
            connection.execute('''
            CREATE TABLE IF NOT EXISTS inventory_items (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            item_name TEXT NOT NULL CHECK(length(item_name) > 0),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            UNIQUE(username, item_name)
            )
        ''')
            connection.execute('''
            CREATE TABLE IF NOT EXISTS trade_item_receipts(
            trade_id INTEGER PRIMARY KEY REFERENCES trades(trade_id),
            username TEXT NOT NULL REFERENCES users(username),
            received_at INTEGER NOT NULL
            )
        ''')

            connection.execute(
                """CREATE TABLE IF NOT EXISTS trade_payouts (
                        trade_id INTEGER PRIMARY KEY
                            REFERENCES trades(trade_id),
                        seller TEXT NOT NULL
                            REFERENCES users(username),
                        amount INTEGER NOT NULL
                            CHECK(amount > 0 AND amount <= 9007199254740991),
                        created_at INTEGER NOT NULL,
                        received_at INTEGER
                            CHECK(received_at IS NULL OR received_at >= 0)
                    )
                    """
            )

            listing_colums = {
                row['name']
                for row in connection.execute('PRAGMA table_info(listings)').fetchall()
            }

            if 'stock_reserved' not in listing_colums:
                connection.execute('''
                    ALTER TABLE listings
                    ADD COLUMN stock_reserved INTEGER NOT NULL DEFAULT 0
                    CHECK(stock_reserved IN(0,1))
                ''')

            connection.executemany(
                '''
                INSERT OR IGNORE INTO users (username, balance)
                VALUES(?,?)
                ''',
                [
                    ('player_001',0),
                    ('player_002',10000000),
                ],
            )




    finally:
        connection.close()

