import sqlite3  # Python에 포함된 SQLite 도구입니다.
from pathlib import Path  # DB 파일 위치를 계산합니다.

DB_PATH = Path(__file__).resolve().parent / 'game_data.db'  # 프로젝트 폴더의 DB 파일입니다.


def get_connection(): # DB 연결을 만드는 함수
    connection = sqlite3.connect(DB_PATH,timeout=10) # connect()로 DB 파일에 연결
    connection.execute("PRAGMA foreign_keys = ON") # 사용자와 인증 정보 사이의 외래키 관계를 검사
    connection.row_factory = sqlite3.Row # 조회 결과를 컬럼 이름으로 읽도록 설정
    return connection # 만들어진 DB 연결 반환

def initialize_database():  # 서버 시작 시 테이블을 준비합니다.
    connection = get_connection()
    try: # 작업 중 오류가 나더라도 finally에서 연결을 닫도록 함
        with connection:  # 성공하면 저장하고, 오류가 나면 변경을 취소합니다.
            connection.execute('''
                CREATE TABLE IF NOT EXISTS trades ( -- trades 테이블이 없을 때만 생성
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 각 거래를 구분하는 정수 번호를 자동 생성
                    seller TEXT NOT NULL CHECK(length(seller) > 0), -- 판매자 문자열이며 NULL과 빈 문자열을 금지
                    buyer TEXT NOT NULL CHECK(length(buyer) > 0), -- 구매자 문자열이며 NULL과 빈 문자열 금지
                    item_name TEXT NOT NULL CHECK(length(item_name) > 0),  -- 거래 당시 아이템 이름 저장
                    price INTEGER NOT NULL CHECK(price > 0), -- 거래 당시 개당 가격이며 0보다 커야 함
                    quantity INTEGER NOT NULL CHECK(quantity > 0) -- 실제 거래한 수량이며 1개 이상이어야 함
                )
            ''')  # 기존 테이블과 데이터는 유지합니다.
            connection.execute('''
                CREATE TABLE IF NOT EXISTS listings( -- listings 테이블이 없을때만 생성
                  listing_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 판매 등록을 구분하는 번호를 자동 생성
                    seller TEXT NOT NULL CHECK(length(seller)>0), -- 아이템을 판매 등록한 사용자 이름
                    item_name TEXT NOT NULL CHECK(length(item_name)>0), -- 판매할 아이템 이름
                    category TEXT NOT NULL -- 아이템 분류이며 NULL을 허용하지 않음
                        CHECK(category IN ('무기','방어구','소비','기타')), -- 지정한 네 가지 분류만 저장할 수 있음
                    price INTEGER NOT NULL CHECK(price > 0), -- 아이템 한개의 판매 가격
                    quantity INTEGER NOT NULL CHECK(quantity >= 0), -- 남은 판매 수량, 전부 팔리면 0
                    status TEXT NOT NULL DEFAULT '판매중' -- 상태를 생략하고 등록하면 판매중으로 저장
                        CHECK(status IN ('판매중','판매완료','취소')), -- 이 세가지 상태만 저장할 수 있음
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- 등록 시각을 자동 저장하며 SQLite 기준 UTC
                )
            ''')
            connection.execute('''
            CREATE TABLE IF NOT EXISTS users ( -- users 테이블이 없을 때만 생성
            username TEXT PRIMARY KEY NOT NULL -- 사용자 이름을 중복될 수 없는 식별자로 사용
                    CHECK(length(username)>0), -- 빈 문자열로 된 사용자 이름을 금지
                balance INTEGER NOT NULL DEFAULT 0 -- 보유 재화이며 값을 생략하면 0 저장
                    CHECK(balance >= 0) -- 잔액이 음수가 되는 것을 DB에서도 막음
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

            connection.executemany( # 같은 SQL을 여러 입력값에 대해 반복 실행
                '''
                INSERT OR IGNORE INTO users (username, balance) -- 계정을 추가하되 중복 등 무시 가능한 제약 위반을 건너뜀
                VALUES(?,?) -- 아래에서 사용자 이름과 초기 잔액을 순서대로 전달
                ''',
                [
                    ('player_001',0), # 판매 테스트 계정, 처음 생성할 때 잔액을 0으로 설정
                    ('player_002',10000000), # 구매 테스트 계정, 처음 생성할 때 재화를 지급
                ],
            )




    finally: # 정상 처리되거나 오류가 발생하거나 항상 실행
        connection.close()  # 사용한 연결을 닫습니다.c

