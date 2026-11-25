import database # 테스트할 때 사용할 DB 경로를 변경하기 위해 가져옴
from main import app # FASTAPI
from fastapi.testclient import TestClient # 브라우저 없이 API에 요청을 보내는 도구

def test_trade_flow_preserves_money_and_items(tmp_path,monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'test.db')

    with TestClient(app) as client:
        password = 'TestAuction!2026'
        tokens = {}

        for username in ['seller_test','buyer_test']:
            signup = client.post('/auth/signup', json = {
                'username': username,
                'password': password,
            })
            assert signup.status_code == 201, signup.text

            login = client.post('/auth/login', json = {
                'username' : username,
                'password' : password,
            })
            assert login.status_code == 200, login.text
            tokens[username] = {'Authorization': 'Bearer '+ login.json()['access_token']}

        seller = tokens['seller_test']
        buyer = tokens['buyer_test']

        connection = database.get_connection()
        try:
            with connection:
                connection.execute(
                    'UPDATE users SET balance = ? WHERE username = ?',
                    (10000, 'buyer_test'),
                )
                connection.execute(
                    'INSERT INTO inventory_items (username,item_name,quantity) VALUES (?,?,?)',
                    ('seller_test', '검증용 검', 5),
                )
        finally:
            connection.close()

        listing = client.post('/listings',headers=seller, json = {
            'item_name': '검증용 검',
            'category': '무기',
            'price': 1000,
            'quantity': 3,
        })

        assert listing.status_code == 201, listing.text
        listing_id = listing.json()['listing_id']
        assert client.get('/me/inventory',headers=seller).json()['items'][0]['quantity'] == 2

        def read_trade_state():
            return {
                'buyer': client.get('/auth/me',headers=buyer).json(),
                'seller': client.get('/auth/me',headers=seller).json(),
                'buyer_inventory': client.get('/me/inventory',headers=buyer).json(),
                'seller_inventory': client.get('/me/inventory', headers=seller).json(),
                'listings': client.get('/me/listings', headers=seller).json(),
                'history': client.get('/me/trades', headers=buyer).json(),
            }

        purchase_url = f'/listings/{listing_id}/purchase'

        rejected_cases = [
            ('수량 초과', buyer,4,409),
            ('본인 상품 구매', seller,1,400),
            ('로그인 없음', {},1,401),
            ('수량 0',buyer,0,422),
        ]

        for name,headers,quantity,expected_status in rejected_cases:
            before = read_trade_state()

            rejected = client.post(
                purchase_url,
                headers=headers,
                json={'quantity':quantity},
            )

            assert rejected.status_code == expected_status,(name,rejected.text)
            assert read_trade_state() == before, name

        def set_buyer_balance(amount):
            connection = database.get_connection()
            try:
                with connection:
                    connection.execute(
                        'UPDATE users SET balance = ? WHERE username = ?',
                        (amount,'buyer_test'),
                    )
            finally:
                connection.close()

        set_buyer_balance(1000)
        before = read_trade_state()

        insufficient = client.post(
            purchase_url,
            headers=buyer,
            json={'quantity': 2},
        )

        assert insufficient.status_code == 400, insufficient.text
        assert insufficient.json()['detail'] == '보유 재화가 부족합니다.'
        assert read_trade_state() == before

        set_buyer_balance(10000)
        
        purchase = client.post(
            f'/listings/{listing_id}/purchase',headers=buyer,json={'quantity':2},
        )
        assert purchase.status_code == 201, purchase.text
        trade_id = purchase.json()['trade_id']
        assert purchase.json()['remaining_quantity'] == 1

        assert client.get('/auth/me', headers=buyer).json()['balance'] == 8000
        assert client.get('/auth/me', headers=seller).json()['balance'] == 0
        history = client.get('/me/trades?role=seller',headers=seller)
        assert history.status_code == 200, history.text
        pending_trade = next(
            trade for trade in history.json()['trades']
            if trade['trade_id'] == trade_id
        )
        assert pending_trade['payout_status'] == 'pending'

        payout_url = f'/trades/{trade_id}/payout'
        assert client.post(payout_url).status_code == 401
        assert client.post(payout_url,headers=buyer).status_code == 403

        payout = client.post(payout_url,headers=seller)
        assert payout.status_code == 200,payout.text
        assert payout.json()['trade_id'] == trade_id
        assert payout.json()['received_amount'] == 2000

        history = client.get('/me/trades?role=seller', headers=seller)
        assert history.status_code == 200, history.text
        paid_trade = next(
            trade for trade in history.json()['trades']
            if trade['trade_id'] == trade_id
        )
        assert paid_trade['payout_status'] == 'received'

        assert client.get('/auth/me',headers=seller).json()['balance'] == 2000

        assert client.post(payout_url, headers=seller).status_code == 409
        assert client.get('/auth/me', headers=seller).json()['balance'] == 2000

        receive_url = f'/trades/{trade_id}/receive'
        assert client.post(receive_url, headers=seller).status_code == 403
        assert client.post(receive_url, headers=buyer).status_code == 200
        assert client.post(receive_url, headers=buyer).status_code == 409
        
        cancel_url = f'/listings/{listing_id}/cancel'
        assert client.post(cancel_url, headers = buyer).status_code == 403
        assert client.post(cancel_url, headers = seller).status_code == 200
        assert client.post(cancel_url, headers = seller).status_code == 409

        seller_items = client.get('/me/inventory',headers=seller).json()['items']
        buyer_items = client.get('/me/inventory',headers=buyer).json()['items']
        assert seller_items[0]['quantity'] == 3
        assert buyer_items[0]['quantity'] == 2
        assert seller_items[0]['quantity'] + buyer_items[0]['quantity'] == 5
                