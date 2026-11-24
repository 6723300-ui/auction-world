import database
from main import app
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

def test_only_one_buyer_can_purchase_last_item(tmp_path,monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH',tmp_path / 'concurrency.db')

    with TestClient(app) as client:
        tokens = {}
        password = 'TestAuction!2026'

        for username in ['seller_test','buyer_one','buyer_two']:
            signup = client.post('/auth/signup',json = {
                'username':username,
                'password':password,
            })
            assert signup.status_code == 201,signup.text

            login = client.post('/auth/login', json= {
                'username': username,
                'password': password,
            })
            assert login.status_code == 200, login.text
            tokens[username] ={'Authorization':'Bearer ' + login.json()['access_token']}

        connection = database.get_connection()
        try:
            with connection:
                connection.execute(
                    'UPDATE users SET balance = 10000 WHERE username IN (?,?)',
                    ('buyer_one','buyer_two'),
                )
                connection.execute(
                    'INSERT INTO inventory_items (username, item_name, quantity) VALUES (?,?,?)',
                    ('seller_test','마지막 검',1),
                )
        finally:
            connection.close()

        listing = client.post('/listings',headers=tokens['seller_test'],json={
            'item_name':'마지막 검',
            'category':'무기',
            'price':1000,
            'quantity':1,
        })
        assert listing.status_code == 201, listing.text
        listing_id = listing.json()['listing_id']
        barrier = Barrier(2)

        def purchase_last_item(username):
            barrier.wait(timeout=10)
            return client.post(
                f'/listings/{listing_id}/purchase',
                headers=tokens[username],
                json={'quantity' : 1},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(purchase_last_item, ['buyer_one','buyer_two']))

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [201,409], [response.text for response in responses]

        balances = [
            client.get('/auth/me', headers=tokens[name]).json()['balance']
            for name in ['buyer_one','buyer_two']
        ]
        assert sorted(balances) == [9000,10000]
        assert client.get('/auth/me',headers=tokens['seller_test']).json()['balance'] == 1000
        
        saved = client.get('/me/listings', headers=tokens['seller_test']).json()['listings'][0]
        assert saved['quantity'] == 0
        assert saved['status'] == '판매완료'

        trade_count = sum(
            client.get('/me/trades', headers=tokens[name]).json()['total']
            for name in ['buyer_one','buyer_two']
        )
        assert trade_count == 1