from getpass import getpass
from pwdlib import PasswordHash
from database import get_connection,initialize_database

def seed_demo():
    initialize_database()
    password = getpass('데모 계정 비밀번호를 입력하세요(12~128자): ')

    if not 12 <= len(password) <= 128:
        print('비밀번호는 12~128자로 입력하세요.')
        return

    hasher = PasswordHash.recommended()
    connection = get_connection()
    results = []

    try:
        with connection:
            connection.execute('BEGIN IMMEDIATE')

            for username, balance in [('demo_seller',0),('demo_buyer',1000000)]:
                existing = connection.execute(
                    'SELECT username FROM users WHERE username = ?',
                    (username,),
                ).fetchone()

                if existing is not None:
                    results.append(username + ': 이미 존재하므로 변경하지 않습니다.')
                    continue

                connection.execute(
                    'INSERT INTO users (username, balance) VALUES (?,?)',
                    (username,balance),
                )

                connection.execute(
                    'INSERT INTO user_credentials (username, password_hash) VALUES (?,?)',
                    (username, hasher.hash(password)),
                )

                if username == 'demo_seller':
                    connection.executemany(
                        'INSERT INTO inventory_items (username,item_name,quantity) VALUES (?,?,?)',
                        [
                            (username,'모험가의 검', 5),
                            (username,'회복 물약', 20),
                        ],
                    )
                results.append(username + ': 생성 완료')

        for result in results:
            print(result)
    finally:
        connection.close()

if __name__ == '__main__':
    seed_demo()