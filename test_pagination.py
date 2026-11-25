import database  # 임시 DB 경로를 설정합니다.
from main import app  # 테스트할 서버입니다.
from fastapi.testclient import TestClient  # API 요청 도구입니다.


def test_listing_pagination(tmp_path, monkeypatch):  # 페이지 조회를 검증합니다.
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'pagination.db')  # 실제 DB와 분리합니다.

    with TestClient(app) as client:  # 테스트 서버를 시작합니다.
        connection = database.get_connection()  # 임시 DB에 연결합니다.
        try:  # 검색용 상품을 준비합니다.
            with connection:  # 아래 데이터를 한 번에 저장합니다.
                connection.execute('DELETE FROM listings')  # 임시 DB의 초기 상품을 비웁니다.
                connection.executemany(  # 상품 23개를 추가합니다.
                    'INSERT INTO listings (seller, item_name, category, price, quantity) VALUES (?, ?, ?, ?, ?)',
                    [
                        ('page_seller', f'페이지 검 {number}', '무기', number * 100, 1)
                        for number in range(1, 24)  # 가격은 100부터 2,300까지입니다.
                    ],
                )
                connection.execute(  # 검색에서 제외할 취소 상품입니다.
                    'INSERT INTO listings (seller, item_name, category, price, quantity, status) VALUES (?, ?, ?, ?, ?, ?)',
                    ('page_seller', '취소된 검', '무기', 100, 1, '취소'),
                )
        finally:  # 상품 준비가 끝나면 실행합니다.
            connection.close()  # DB 연결을 닫습니다.

        pages = []  # 여기부터는 finally 바깥입니다.
        for page in [1, 2, 3]:  # 세 페이지를 조회합니다.
            response = client.get('/listings', params={
                'page': page,  # 조회할 페이지입니다.
                'page_size': 10,  # 숫자 뒤에는 마침표가 아니라 쉼표입니다.
                'sort_by': 'latest',  # 최신순으로 조회합니다.
            })
            assert response.status_code == 200, response.text  # 조회 성공 여부입니다.
            data = response.json()  # 응답을 읽습니다.
            assert data['total'] == 23  # 취소 상품은 제외합니다.
            assert data['page'] == page  # 현재 페이지를 확인합니다.
            assert data['page_size'] == 10  # 페이지 크기입니다.
            assert data['total_pages'] == 3  # 전체 페이지 수입니다.
            pages.append(data['listings'])  # 페이지 상품을 보관합니다.

        assert [len(items) for items in pages] == [10, 10, 3]  # 페이지별 상품 수입니다.
        ids = [item['listing_id'] for items in pages for item in items]  # 상품 번호를 모읍니다.
        assert len(set(ids)) == 23  # 중복 상품이 없어야 합니다.
        assert ids == sorted(ids, reverse=True)  # 최신순이 유지돼야 합니다.

        filtered = client.get('/listings', params={
            'max_price': 1000,  # max_prince가 아니라 max_price입니다.
            'sort_by': 'price_low',  # 낮은 가격순입니다.
            'page': 2,  # 두 번째 페이지입니다.
            'page_size': 3,  # 세 개씩 조회합니다.
        })
        assert filtered.status_code == 200, filtered.text  # 조회 성공 여부입니다.
        assert filtered.json()['total'] == 10  # 가격 조건에 맞는 상품 수입니다.
        assert filtered.json()['total_pages'] == 4  # 전체 페이지 수입니다.
        assert [item['price'] for item in filtered.json()['listings']] == [400, 500, 600]  # 두 번째 페이지의 가격입니다.

        beyond = client.get('/listings', params={'page': 4, 'page_size': 10})  # 범위 밖의 페이지입니다.
        assert beyond.status_code == 200, beyond.text  # 정상 응답이어야 합니다.
        assert beyond.json()['listings'] == []  # filtered가 아니라 beyond의 결과를 검사합니다.
        assert beyond.json()['total'] == 23  # 전체 건수는 유지됩니다.

        for params in [{'page': 0}, {'page_size': 0}, {'page_size': 101}]:  # 잘못된 입력입니다.
            assert client.get('/listings', params=params).status_code == 422  # status_code에는 밑줄이 들어갑니다.