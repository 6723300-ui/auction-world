import database
from main import app
from fastapi.testclient import TestClient


def test_listing_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'pagination.db')

    with TestClient(app) as client:
        connection = database.get_connection()
        try:
            with connection:
                connection.execute('DELETE FROM listings')
                connection.executemany(
                    'INSERT INTO listings (seller, item_name, category, price, quantity) VALUES (?, ?, ?, ?, ?)',
                    [
                        ('page_seller', f'페이지 검 {number}', '무기', number * 100, 1)
                        for number in range(1, 24)
                    ],
                )
                connection.execute(
                    'INSERT INTO listings (seller, item_name, category, price, quantity, status) VALUES (?, ?, ?, ?, ?, ?)',
                    ('page_seller', '취소된 검', '무기', 100, 1, '취소'),
                )
        finally:
            connection.close()

        pages = []
        for page in [1, 2, 3]:
            response = client.get('/listings', params={
                'page': page,
                'page_size': 10,
                'sort_by': 'latest',
            })
            assert response.status_code == 200, response.text
            data = response.json()
            assert data['total'] == 23
            assert data['page'] == page
            assert data['page_size'] == 10
            assert data['total_pages'] == 3
            pages.append(data['listings'])

        assert [len(items) for items in pages] == [10, 10, 3]
        ids = [item['listing_id'] for items in pages for item in items]
        assert len(set(ids)) == 23
        assert ids == sorted(ids, reverse=True)

        filtered = client.get('/listings', params={
            'max_price': 1000,
            'sort_by': 'price_low',
            'page': 2,
            'page_size': 3,
        })
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()['total'] == 10
        assert filtered.json()['total_pages'] == 4
        assert [item['price'] for item in filtered.json()['listings']] == [400, 500, 600]

        beyond = client.get('/listings', params={'page': 4, 'page_size': 10})
        assert beyond.status_code == 200, beyond.text
        assert beyond.json()['listings'] == []
        assert beyond.json()['total'] == 23

        for params in [{'page': 0}, {'page_size': 0}, {'page_size': 101}]:
            assert client.get('/listings', params=params).status_code == 422