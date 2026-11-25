import database
from main import app
from fastapi.testclient import TestClient

def test_read_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(database,'DB_PATH',tmp_path / 'permission.db')

    with TestClient(app) as client:
        tokens = {}
        password = 'TestAuction!2026'

        for username in ['reader_one','reader_two','reader_three']:
            signup = client.post('/auth/signup', json = {
                'username': username,
                'password': password,
            })
            assert signup.status_code == 201, signup.text

            login = client.post('/auth/login', json={
                'username': username,
                'password': password,
            })
            assert login.status_code == 200, login.text
            tokens[username] = {
                'Authorization' : 'Bearer ' + login.json()['access_token'],
            }

        connection = database.get_connection()
        try:
            with connection:
                own_trade_id = connection.execute(
                    'INSERT INTO trades(seller,buyer,item_name,price,quantity) VALUES (?,?,?,?,?)',
                    ('reader_one','reader_two','권한 확인용 검', 1000,2),
                ).lastrowid

                other_trade_id = connection.execute(
                    'INSERT INTO trades (seller, buyer, item_name,price,quantity) VALUES(?,?,?,?,?)',
                    ('reader_two','reader_three','다른 사람의 물약',300,1),
                ).lastrowid

        finally:
            connection.close()

        owner = tokens['reader_one']
        buyer = tokens['reader_two']
        outsider = tokens['reader_three']

        protected_urls = [
            '/users/reader_one',
            '/trades',
            f'/trades/{own_trade_id}',
            '/trade-stats',
            '/seller-stats',
        ]

        for url in protected_urls:
            response = client.get(url)
            assert response.status_code == 401,(url, response.text)

        own_user = client.get('/users/reader_one',headers=owner)
        assert own_user.status_code == 200, own_user.text
        assert own_user.json()['username'] == 'reader_one'
        assert client.get('/users/reader_two', headers=owner).status_code == 403

        history = client.get('/trades', headers=owner)
        legacy_history = client.get('/me/trades?role=seller',headers=owner)
        assert legacy_history.status_code == 200, legacy_history.text
        assert legacy_history.json()['trades'][0]['payout_status'] == 'legacy'
        assert {trade['trade_id'] for trade in history.json()['trades']} == {own_trade_id}

        filtered = client.get('/trades?seller=reader_two',headers=owner)
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()['trades'] == []

        detail_url = f'/trades/{own_trade_id}'
        assert client.get(detail_url, headers=owner).status_code == 200
        assert client.get(detail_url, headers=buyer).status_code == 200
        assert client.get(detail_url, headers=outsider).status_code == 404
        assert client.get(f'/trades/{other_trade_id}',headers=owner).status_code == 404

        stats = client.get('/trade-stats',headers=owner)
        assert stats.status_code == 200, stats.text
        assert stats.json() == {
            'trade_count': 1,
            'total_quantity' : 2,
            'total_amount': 2000,
        }

        sales = client.get('/seller-stats', headers=owner)
        assert sales.status_code == 200,sales.text
        assert sales.json() == {
            'total' : 1,
            'sellers': [{
                'seller':'reader_one',
                'tade_count' : 1,
                'total_quantity' : 2,
                'total_amount' : 2000,
            }],
        }

