from typing import Literal # 입력값과 정해진 선택지로 제한하는 도구
from fastapi import FastAPI, HTTPException, Query, Depends # API 서버를 만드는 도구를 가져옴
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials # 요청 헤더에서 로그인 토큰을 읽음
from pydantic import BaseModel, Field, ConfigDict # 요청 데이터의 구조와 값의 허용 범위를 정의, 입력 검사와 모델 설정 도구
from contextlib import asynccontextmanager # 서버 시작/종료 작업을 정의하는 도구
from database import get_connection, initialize_database # database.py에서 DB 연결/초기화 함수를 가져옴
from pathlib import Path # 파일의 위치와 경로를 다룹니다.
from fastapi.responses import FileResponse # HTML 같은 파일을 브라우저에 전달
import sqlite3 # 사용자 이름 중복 같은 DB 오류 처리
from pwdlib import PasswordHash # 비밀번호 해시를 생성하는 도구
from pydantic import BaseModel, Field, ConfigDict, SecretStr # 기존 import에 SecretStr 추가
import secrets # 예측하기 어려운 로그인 토큰
import hashlib # 토큰을 DB에 보관하기 위한 해시를 만듬
import time # 로그인 만료 시각을 계산


@asynccontextmanager # yield 기준으로 시버 시작 전 작업과 종료 작업을 나눔
async def lifespan(app: FastAPI): # FastAPI가 서버를 시작하고 종료할 때 사용하는 함수
    initialize_database() # 요청을 받기 전에 DB 테이블과 테스트 계정을 준비
    yield # 초기화가 끝났으므로 서버가 요청을 처리하도록 넘김

app = FastAPI( # 실행할 API 프로그램을 만듬
    title="가상 FPS 게임 데이터 API", # API 문서 제목
    description="포트폴리오용 거래/전투 데이터 분석 프로젝트", # 프로젝트 설명
    version="0.1.0", # 현재 개발 버전
    lifespan=lifespan, # 서버 시작 시 위의 lifespan 함수를 사용 하도록 연결
) 

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail='로그인이 필요합니다.',
            headers={'WWW-Authenticate':'Bearer'},
        )

    token_hash = hashlib.sha256(
        credentials.credentials.encode('utf-8')
    ).hexdigest()

    Connection = get_connection()

    try:
        user = Connection.execute(
            """
            SELECT users.username, users.balance
            FROM auth_sessions
            JOIN users ON users.username = auth_sessions.username
            WHERE auth_sessions.token_hash = ?
            AND auth_sessions.expires_at > ?
              """,
              (token_hash, int(time.time())),
        ).fetchone()

        if user is None:
            raise HTTPException(
                status_code=401,
                detail='로그인이 만료됐거나 유효하지 않습니다.',
                headers={'WWW-Authenticate': 'Bearer'}
            )

        return dict(user)

    finally:
        Connection.close()

@app.get("/") # 기본 주소로 GET 요청이 오면 아래 함수를 실행
def read_root(): # 기본 주소의 응답을 만드는 함수
    return{"message":"게임 데이터 API가 실행 중입니다."} # 딕셔너리가 JSON 응답으로 전달


@app.get("/health") # 서버 상태를 확인하는 주소
def health_check(): # 서버 상태를 확인하는 함수
    return{ # 응답 데이터 생성
        "status":"ok" # 서버가 정상적으로 응답하는 표시
    }

# 처음 메모리 저장을 연습할 때 만들었던 데이터
# 현재 아래 API들은 DB를 사용하므로 이 전역 목록은 거래 조회/구매에 사용되지 않습니다.
# 연습용 거래 기록 추후 DB에 저장한 데이터를 조회
trades = [ # 여러 거래를 담는 리스트
    { # 첫 번째 거래 정보를 담는 딕셔너러
        "trade_id": 1, # 거래구분 번호
        "seller": "player_001", # 판매자
        "buyer": "player_002", # 구매자
        "item_name":"드래곤 라이플", # 거래한 아이템
        "price":1500, # 아이템 1개 가격
        "quantity": 1, # 거래 수량
    },
    { # 두 번째 거래
        "trade_id":2, # 거래구분 번호
        "seller":"player_003", # 판매자
        "buyer":"player_001", # 구매자
        "item_name":"회복 키트", # 거래한 아이템
        "price":200, # 아이템 1개 가격
        "quantity":5, # 거래 수량
    },
] 

@app.get("/trades")  # 완료된 거래 기록을 조회하는 API
def get_trades(seller: str | None = None):  # seller는 문자열이며, 생략하면 None이 됩니다.
    connection = get_connection() # 이번 요청에서 사용할 DB연걸을 만듬

    try: # 아래 작업 중 오류가 나더라도 finally에서 연결을 담도록 함.
        if seller is None: # 판매자를 지정하지 않았다면 전체 거래를 조회
            rows = connection.execute( # DB에 SQL를 실행함.
                'SELECT * FROM trades ORDER BY trade_id' # 모든 거래를 번호가 작은 순서로 조회
            ).fetchall() # 조회된 행을 모두 가져옴
        else: # 판매자를 지정했다면 해당 판매자의 거래만 조회
            rows = connection.execute( # 조건이 있는 SQL을 실행
                'SELECT * FROM trades WHERE seller = ? ORDER BY trade_id', # ?에 판매자 값을 전달
                (seller,), # 값 한 개를 담은 튜블, 마지막 쉼표도 필요
            ).fetchall() # 조건에 맞는 모든 거래를 가져옴
        
        trades = [dict(row) for row in rows] # 각 DB 행을 딕셔너리로 바뀌 리스트로 만듬

        return { # 응답으로 보낼 정보를 구성
            'total': len(trades), # 조회된 거래 건수
            'trades': trades, # 조회된 거래 목록
        } # FastAPI가 이 데이터를 JSON으로 반환

    finally: # 정상 처리하거나 오류가 나거나 항상 싱행
        connection.close() # 이번 요청에 사용한 DB 연결을 닫음

@app.get('/trades/{trade_id}') # 주소의 거래 번호를 특정 거래 하나를 조회합니다.
def get_trade(trade_id: int): # 주소에서 받은 trade_id를 정수로 검사
    connection = get_connection() # DB 연결

    try: # 조회 작업 시작
        row = connection.execute( # SQL 실행
            'SELECT * FROM trades WHERE trade_id = ?', # 해당 거래 번호의 기록을 찾음
            (trade_id,), # 물음표에 넣을 거래 번호
        ).fetchone() # 결과 한 행을 가져오며, 없으면 None

        if row is None: # 해당 번호의 거래가 없는 경우
            raise HTTPException( # 정상 응답 대신 HTTP 오류 응답을 보냄
                status_code=404, # 요청한 데이터를 찾을 수 없는 상태
                detail='해당 거래를 찾을 수 없습니다.', # 응답에 표시할 설명
            )

        return dict(row) # 조회한 한 행을 딕셔너리로 변환해서 반환

    finally: # 거래를 찾지 못한 경우 실행
        connection.close() # DB 종료

@app.get('/trade-stats') # 전체 거래 통계를 조회하는 API
def get_trade_stats(): # 전체 거래 건수/수량/금액 계산
    connection = get_connection() # DB 연결

    try: # 통계 조회를 시작
        row = connection.execute( # 집계 SQL을 실행
            '''
            SELECT -- 아래 계산 결과를 조회
                COUNT(*) AS trade_count, -- 거래 기록의 갯수
                COALESCE(SUM(quantity),0) AS total_quantity, -- 전체 거래 수량이며, 결과가 NULL 이면 0
                COALESCE(SUM(price * quantity),0) AS total_amount -- 개당 가격*수량을 모두 합한 금액
            FROM trades -- 거래 기록 테이블을 집계
            '''
        ).fetchone() # GROUP BY가 없는 전체 집계이므로 결과 한 행을 받음

        return dict(row) # 통계 결과를 딕셔너리로 반환

    finally: # 조회가 끝나면 실행
        connection.close() # DB 종료


@app.get('/seller-stats') # 현재 코드에 등록된 주소, 등호가 들어간 이름을 그대로 유지
def get_seller_stats(): # 판매자별 거래 통계를 계산하는 함수
    connection = get_connection() # DB에 연결

    try: # 조회 작업 시작
        rows = connection.execute( # 판매자별 집계 SQL 실행
            '''
            SELECT 
                seller, -- 통계가 누구의 것인 판매자 이름도 반환
                COUNT(*) AS tade_count, -- 각 판매자의 거래 건수, 현재 응답 이름은 tade_count
                SUM(quantity) AS total_quantity, -- 각 판매자가 거래한 총수량
                SUM(price * quantity) AS total_amount -- 각 판매자의 총거래 금액
            FROM trades -- 거래 기록을 대상으로 함
            GROUP BY seller -- 같은 판매자의 거래끼리 묶음
            ORDER BY total_amount DESC, seller ASC -- 금액이 큰 순서이며 동률이면 판매자 이름순
            '''
        ).fetchall() # 판매자별 결과를 모두 가져옴

        sellers = [dict(row) for row in rows] # 결과를 딕셔너리 목록으로 바꿈

        return{ # 집계 응담 구성
            'total': len(sellers), # 집계된 판매자 그룹 수
            'sellers': sellers, # 판매자별 집계 목록
        } # 판매자 이름과 거래 건수/수량/금액을 함께 반환

    finally: # 조회 후 항상 실행
        connection.close() # DB 연결 종료

class ListingCreate(BaseModel): # 판매 등록 시 받을 입력 구조
    model_config = ConfigDict(str_strip_whitespace=True) # 문자열 앞뒤 공백을 먼저 제거

    item_name: str = Field(min_length=1) # 아이템 이름
    category: Literal['무기','방어구','소비','기타'] # 네 가지 분류 중 하나만 허용
    price: int = Field(strict=True, gt=0, le=9007199254740991) # SQLlife 정수 범위 안의 양수 가격
    quantity: int = Field(strict=True, gt=0, le=9007199254740991) # 판매 등록 수량도 양수로 제한


@app.post('/listings', status_code=201) # 새로운 판매 등록을 만드는 API
def create_listing(
    listing: ListingCreate,
    user: dict = Depends(get_current_user),
    ):
    connection = get_connection() # DB연결

    try: # 등록 작업 시작
        with connection: # 성공하면 저장하고, 오류나면 취소
            connection.execute('BEGIN IMMEDIATE')

            inventory = connection.execute(
                'SELECT inventory_id, quantity FROM inventory_items WHERE username = ? AND item_name = ?',
                (user['username'],listing.item_name),
            ).fetchone()

            if inventory is None:
                raise HTTPException(400,'보관함에 없는 아이템입니다.')

            if inventory['quantity'] < listing.quantity:
                raise HTTPException(400,'보유 수량이 부족합니다.')

            remaining = inventory['quantity'] - listing.quantity

            if remaining == 0:
                connection.execute(
                    'DELETE FROM inventory_items WHERE inventory_id = ?',
                    (inventory['inventory_id'],),
                )
            else:
                connection.execute(
                    'UPDATE inventory_items SET quantity = ? WHERE inventory_id = ?',
                    (remaining, inventory['inventory_id']),
                )

            cursor = connection.execute( # 새 판매 정보를 DB에 추가
                '''
                INSERT INTO listings( -- 판매 등록 테이블에 행 추가
                    seller, item_name, category, price, quantity, stock_reserved -- 저장할 컬럼 순서
                )
                VALUES(?,?,?,?,?,1) -- 아래 다섯 값을 순서대로 사용
                ''',
             (
                    user['username'],
                    listing.item_name,
                    listing.category,
                    listing.price,
                    listing.quantity,
                ),
         )
            
            row = connection.execute( # 방금 등록한 판매 정보를 다시 조회
                'SELECT * FROM listings WHERE listing_id =?', # 등록 번호 찾기
                (cursor.lastrowid,), # 방금 생성한 번호 전달
            ).fetchone() # 한 행을 가져옴, 기본 상태와 등록 시각도 포함

        return dict(row) # DB 저장이 끝난 뒤 등록 결과를 반환

    finally: # 오류 발생 여부와 관계없이 실행
        connection.close() # DB 종료
                
@app.get('/listings') # 거래소 검색 화면에서 사용하는 판매 목록 API
def get_listing( # 검색 조건을 받는 함수
    keyword: str | None = None, # 아이템 이름 검색어이며, 생락 가능
    category: Literal['무기', '방어구', '소비', '기타'] | None = None, # 분류 조건이며 생략 가능
    min_price: int | None = Query(default=None, ge=0, le=9007199254740991), # 최저 가격
    max_price: int | None = Query(default=None, ge=0, le=9007199254740991), # 최고 가격
    sort_by: Literal['latest','price_low','price_high'] = 'latest', # 허용된 정렬 방식만 받음
): # 검색 조건 정의
    if min_price is not None and max_price is not None: # 양쪽 가격을 모두 입력한 경우
        if min_price > max_price: # 최저 가격이 최고 가격보다 크면 잘못된 조건
            raise HTTPException( # 잘못된 검색 조건이라는 응답을 보냄
                status_code= 422, # 입력 조건이 유효하지 않다는 상태 코드
                detail='최저 가격은 최고 가격보다 클 수 없습니다.' # 오류 설명
            )
    connection = get_connection() # 검색 조건 검사 통과 후 DB 연결

    try: # 검색 SQL을 만들고 실행
        sql = "SELECT * FROM listings WHERE status = '판매중'" # 판매 중인 아이템만 검색
        params = [] # SQL의 ?에 넣을 값들을 순서대로 보관

        if keyword and keyword.strip(): # 검색어가 있고 공백뿐인 값이 아니라면 실행
            sql += " AND instr(item_name, ?) > 0" # 이름에 검색어가 포함되는 조건 붙임
            params.append(keyword.strip()) # 검색어의 앞뒤 공백을 제거해 전달
            
        if category is not None: # 분류를 지정한 경우
            sql += " AND category = ?" # 같은 분류만 조회하도록 조건을 추가
            params.append(category) # 선택한 분류를 전달

        if min_price is not None: # 최저 가격이 지정된 경우
            sql += " AND price >= ?" # 개당 가격이 최저 가격 이상이여야 함
            params.append(min_price) # 최조 가격 전달

        if max_price is not None: #
            sql += " AND price <= ?"
            params.append(max_price)

        sort_options = { # 정렬 이름에 대응하는 SQL을 미리 정해 둠
            'latest': 'listing_id DESC', # 등록 번호가 큰 최신 상품부터 표시
            'price_low': 'price ASC, listing_id DESC', # 낮은 가격순이며 같은 가격은 최신순
            'price_high': 'price DESC, listing_id DESC', # 높은 가격순이며 같은 가격은 최신순
        }
 
        sql += " ORDER BY " + sort_options[sort_by] # 선택한 정렬 조건을 SQL 마지막에 붙임

        rows = connection.execute(sql, params).fetchall() # 완성한 SQL과 입력값으로 검색
        listings = [dict(row) for row in rows] # DB 결과를 딕셔너리 목록으로 바꿈

        return { # 검색 응답 구성
            'total': len(listings), # 검색 결과 건수
            'listings': listings, # 검색된 판매 등록 목록
        }

    finally: # 검색 성공 여부와 관계없이 실행
        connection.close() # DB 연결 종료

@app.get('/market', include_in_schema=False) # 거래소 화면 주소이며 /docs 목록에는 표시하지 않음
def market_page(): # 거래소 HTML을 제공하는 함수
    html_path = Path(__file__).resolve().parent / 'market.html' # main.py와 같은 폴더의 HTML을 찾음
    return FileResponse(html_path) # HTML 파일을 브라우저로 전달

@app.get('/users/{username}') # 주소에 지정한 사용자 정보를 조회
def get_user(username: str): # 사용자 이름을 문자열로 받음
    connection = get_connection() # DB 연결

    try: # 사용자 조회 시작
        row = connection.execute( # 사용자 이름과 잔액 조회
            'SELECT username, balance FROM users WHERE username = ?', # 이름이 일치하는 계정 찾기
            (username,), # 조회할 사용자 이름
        ).fetchone() # 계정 한 개를 가져오며 없으면 None

        if row is None: # 해당 사용자가 없는 경우
            raise HTTPException( # HTTP 오류 응답을 만듬
                status_code=404, # 사용자를 찾지 못했다는 상태 코드
                detail='사용자를 찾을 수 없습니다.', # 오류 설명
            )

        return dict(row) # 사용자 이름과 잔액을 반환

    finally: # 항상 실행
        connection.close() # DB 연결 종료

class PurcjaseCreate(BaseModel): #  # 현재 코드의 클래스 이름을 유지, 구매 입력 구조
    quantity: int = Field(strict=True, gt=0, le=9007199254740991) # 구매 수령을 양의 정수로 제한


@app.post('/listings/{listing_id}/purchase',status_code=201) # 특정 판매 등록의 구매를 처리함
def purchase_listing(
    listing_id:int, 
    purchase: PurcjaseCreate,
    user: dict = Depends(get_current_user),
    ): # 판매 번호와 구매 요청을 받음
    buyer_username = user['username']
    connection = get_connection() # 이번 구매에 사용할 DB 연결

    try: # 구매 작업 시작
        with connection: # 안쪽 작업이 모두 성공하면 저장하고, 오류가 나면 변경을 취소
            connection.execute("BEGIN IMMEDIATE") # 쓰기 트랜잭션을 시작해 다른 쓰기 작업과 순서를 조정

            listing = connection.execute( # 현재 DB의 판매 정보를 조회
                "SELECT * FROM listings WHERE listing_id = ?", # 구매 대상 판매 번호를 찾음
                (listing_id,), # 주소에서 받은 판매 번호
            ).fetchone() # 판매 정보 한 행을 가져옴

            if listing is None: # 해당 판매 등록이 없는 경우
                raise HTTPException(404, '판매 정보를 찾을 수 없습니다.') # 구매를 중단

            if listing['status'] != '판매중': # 판매완료 또는 취소된 등록이라면 실행
                raise HTTPException(409, '판매 중인 아이템이 아닙니다.') # 현재 판매 상태와 충돌하는 요청

            if purchase.quantity > listing['quantity']: # 요청한 수량이 현재 남은 수량보다 많은 경우
                raise HTTPException(409,'판매 수량이 부적합니다.') # 원래 코드의 문구를 유지 


            if buyer_username == listing['seller']: # 구매자와 판매자가 같은 경우
                raise HTTPException(400,'자신의 아이템은 구매할 수 없습니다.') # 자기 상품 구매 금지

            buyer = connection.execute( # 구매자의 계정 정보를 찾음
                "SELECT * FROM users WHERE username = ?", # 계정 테이블에서 이름을 조회
                (buyer_username,), # 요청으로 받은 구매자 이름
            ).fetchone() # 구매자 정보를 한 행을 가져옴

            seller = connection.execute( # 판매자의 계정 정보를 찾음
                "SELECT * FROM users WHERE username = ?", # 계정 테이블 조회
                (listing['seller'],), # 판매자 이름을 판매 등록에 저장된 값을 사용
            ).fetchone() # 판매자 정보 한 행을 가져옴

            if buyer is None or seller is None: # 두 계정 중 하나라도 없으면 실행
                raise HTTPException(404, '구매자 또는 판매자 계정이 없습니다.') # 구매 중단

            total = listing['price'] * purchase.quantity # DB의 개당 가격*구매 수량으로 금액을 계산

            if buyer['balance'] < total: # 구매자의 잔액을 결재 금액보다 적은 경우
                raise HTTPException(400, '보유 재화가 부족합니다.') # 잔액 변경 전에 구매를 중단

            if seller['balance'] + total > 9007199254740991: # 입금 후 잔액이 정한 한도를 넘는지 확인
                raise HTTPException(409,'판매자외 보유 재화 한도를 초과합니다.') # 입금을 진행하지 않음

            connection.execute( # 구매자에게서 재화를 차감
                "UPDATE users SET balance = balance - ? WHERE username = ?", # 잔액을 구매 금액만큼 줄임
                (total, buyer_username), # 차감할 금액과 구매자 이름
            ) # 아직 트랜잭션 안이므로 이 변경만 따로 확정되진 않음

            connection.execute( # 판매자에게 재화를 입금
                "UPDATE users SET balance = balance + ? WHERE username = ?", # 잔액을 구매 금액만큼 늘림
                (total, listing['seller']), # 입금 금액과 판매자 이름
            ) # 이후 작업이 실패하면 앞의 차감과 함께 취소됨

            remaining = listing['quantity'] - purchase.quantity # 구매 후 남은 판매 수량
            status = '판매완료' if remaining == 0 else '판매중' # 남은 수량이 0이면 판매완료로 변경

            connection.execute( # 판매 등록의 남은 수량과 상태를 갱신
                "UPDATE listings SET quantity = ?, status = ? WHERE listing_id = ?", # 특정 등록만 수정
                (remaining, status, listing_id), # 남은 수량/상태/판매 번호를 순서대로 전달
            )

            cursor = connection.execute( # 성공한 구매의 거래 기록을 추가
                """
                INSERT INTO trades (seller, buyer, item_name, price, quantity) -- 완료된 거래를 기록
                VALUES(?,?,?,?,?) -- 아래 다섯 값을 사용
                """,
                (
                    listing['seller'],
                    buyer_username,
                    listing['item_name'],
                    listing['price'],
                    purchase.quantity,
                ),
            )

            result = { # 구매 결과로 돌려줄 정보를 미리 구성
                'trade_id': cursor.lastrowid, # 새 거래 기록의 번호
                'item_name': listing['item_name'], # 구매할 아이템 이름
                'quantity': purchase.quantity, # 이번 구매 수량
                'total_amount': total, # 사용한 재화
                'buyer_balance': buyer['balance'] - total, # 조회 당시 잔액에서 금액을 뺀 구매 후 잔액
                'remaining_quantity': remaining, # 구매 후 남은 판매 수량
                'status': status, # 구매 후 판매 등록 상태
            } # 이 딕셔너리는 응답을 위한 정보이며 별도의 테이블은 아님

        return result # with 블록을 정상 종료하고 DB 변경이 확정된 뒤 결과를 반환
    finally: # 구매 성공/실패와 상관없이 실행
        connection.close() # DB 연결 종료

@app.get('/me/trades') # 특정 사용자의 구매 기록을 조회하는 API
def get_user_trades(
    role: Literal['buyer','seller'] = 'buyer',
    user: dict = Depends(get_current_user),
):
    connection = get_connection()
    column = 'buyer' if role == 'buyer' else 'seller'

    try: # 구매 내역 조회 시작
        rows = connection.execute( # 거래 기록 조회 SQL 실행
            f"""
            SELECT 
                trade_id, item_name, seller, buyer, price, quantity,
                EXISTS (
                    SELECT 1 FROM trade_item_receipts
                    WHERE trade_item_receipts.trade_id = trades.trade_id
                    ) AS received
            FROM trades -- 거래 기록 테이블 조회
            WHERE {column} = ? -- 해당 사용자가 구매자인 거래만 가져옴
            ORDER BY trade_id DESC -- 최근 거래부터 표시
            """,
            (user['username'],), # 주소에서 받은 사용자 이름
        ).fetchall() # 해당 구매의 거래를 모두 가져옴

        return { # 구매 내역 응답을 만듬
            'total':len(rows), # 구매 기록 건수
            'trades': [dict(row) for row in rows], # 각 거래를 딕셔너리로 변환한 목록
        } # 기록이 없으면 0건과 빈 목록을 반환

    finally: # 항상 실행
        connection.close() # DB 연결 종료
            
@app.get('/me/listings')  # 특정 사용자가 등록한 판매 목록 조회
def get_user_listings(user: dict = Depends(get_current_user)): # 조회할 판매자 이름 받음
    connection = get_connection() # DB 연결

    try: # 판매 등록 내역 조회 시작
        rows = connection.execute( # SQL 실행
            """
            SELECT
                listing_id,
                item_name,
                category,
                price,
                quantity,
                status
            FROM listings -- 판매 등록 테이블 조화
            WHERE seller = ? -- 해당 판매자가 등록한 항목만 가져옴
            ORDER BY listing_id DESC -- 최근 등록한 항목부터 표시
            """,
            (user['username'],), # 조회할 판매자 이름 전달
        ).fetchall() # 상태와 관계없이 해당 판매자의 등록 내역을 가져옴

        return { # 판매 내역 응답 구성
            'total': len(rows), # 판매 등록 건수
            'listings': [dict(row) for row in rows], # 화면에 표시할 판매 등록 목록
        } # 실제 판매 목록 조회 버튼이 사용하는 응답

    finally: # 조회 성공 여부와 관계없이 실행
        connection.close() # 사용한 DB 연결 종료


@app.post('/listings/{listing_id}/cancel') # 특정 판매 등록을 취소하는 주소
def cancel_listing(
    listing_id: int,
    user: dict = Depends(get_current_user),
):
    connection = get_connection()
    
    try:
        with connection: # 성공하면 저장하고, 오류가 나면 변경을 취소
            connection.execute("BEGIN IMMEDIATE") # 구매오 취소가 동시에 처리되지 않도록 쓰기 순서 조정

            listing = connection.execute( 
                "SELECT * FROM listings WHERE listing_id = ?",
                (listing_id,), # 취소할 판매 등록 번호
            ).fetchone() # 해당 판매 정보 한 행을 가져옴

            if listing is None: # 등록 번호가 없는 경우
                raise HTTPException(404,'판매 정보를 찾을 수 없습니다.') 

            if listing['seller'] != user['username']:
                raise HTTPException(403,'본인이 등록한 아이템만 취소할 수 있습니다.')

            if listing['status'] != '판매중': # 판매완료 또는 이미 취소된 등록은 처리하지 않음
                raise HTTPException(409,'판매 중인 등록만 취소할 수 있습니다.')

            if listing['stock_reserved'] == 1:
                returned = connection.execute(
                    """
                INSERT INTO inventory_items (username, item_name, quantity)
                VALUES (?,?,?)
                ON CONFLICT(username, item_name)
                DO UPDATE SET quantity = inventory_items.quantity + excluded.quantity
                WHERE inventory_items.quantity <= ?
                """,
                (
                    user['username'],
                    listing['item_name'],
                    listing['quantity'],
                    9007199254740991 - listing['quantity'],
                ),
            )

            if returned.rowcount != 1:
                raise HTTPException(409, '보관함 수량 한도를 초과해 취소할 수 업습니다.')
            
            connection.execute(
                "UPDATE listings SET status = '취소' WHERE listing_id = ?",
                (listing_id,), # 수량은 유지하고 판매 상태만 바꿈
            )

            result = {
                'listing_id': listing_id,
                'item_name': listing['item_name'],
                'quantity': listing['quantity'],
                'status': '취소',
            }

        return result

    finally:
        connection.close()


password_hasher = PasswordHash.recommended()

class SignupRequest(BaseModel):
    username: str = Field(
        min_length=3, max_length=32,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    password: SecretStr = Field(
        min_length=12, max_length=128,
    )

@app.post('/auth/signup',status_code=201)
def signup(request:SignupRequest):
    hashed_password = password_hasher.hash(
        request.password.get_secret_value()
    )

    connection = get_connection()

    try:
        with connection:
            connection.execute(
                "INSERT INTO users (username,balance) VALUES (?,?)",
                (request.username, 0),
            )

            connection.execute(
                "INSERT INTO user_credentials (username, password_hash) VALUES (?,?)",
                (request.username,hashed_password),
            )

        return {
            'username': request.username,
            'balance': 0,
            'message': '회원가입이 완료되었습니다.', 
        }

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail='이미 사용 중인 아이디입니다.',
        )

    finally:
        connection.close()

DUMMY_PASSWORD_HASH = password_hasher.hash(
    secrets.token_urlsafe(32) # 없는 계정도 비밀번호 검증 연산을 수행하도록 준비
)

class LoginRequest(BaseModel): # 로그인할 때 받는 입력
    username: str = Field(
        min_length=3, max_length=32,
        pattern=r"^[A-Za-z0-9_]+$", # 회원가입과 같은 아이디 규칙
    )
    password:SecretStr=Field(
        min_length=1, max_length=128, # 입력한 비밀번호를 받음
    )

@app.post('/auth/login') # 아이디와 비밀번호로 로그읺하는 API
def login(request: LoginRequest):
    connection = get_connection() # 계정 정보를 조회할 DB 연결

    try:
        account = connection.execute(
            "SELECT username, password_hash FROM user_credentials WHERE username = ?",
            (request.username,), # 입력한 아이디로 인증 정보 찾음
        ).fetchone()

        stored_hash = (
            account['password_hash'] if account is not None
            else DUMMY_PASSWORD_HASH
        ) # 없는 계정도 해시 검증 과정을 거침

        password_matches = password_hasher.verify(
            request.password.get_secret_value(), # 사용자가 입력한 비밀번호
            stored_hash, # DB의 해시와 비교
        )

        if account is None or not password_matches: # 계정이 없거나 비밀번호가 다른 경우
            raise HTTPException(
                status_code=401,
                detail='아이디 또는 비밀번호가 올바르지 않습니다.',
            )

        token = secrets.token_urlsafe(32) # 이번 로그인에 사용할 임의의 토큰
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest() # DBD에는 토큰 원문 대신 해시를 저장
        now = int(time.time()) # 현재 시각을 초 단위 숫자로 가져옴
        expires_at = now + 3600 # 현재부터 1시간 후 만료

        with connection: # 로그인 정보를 DB에 저장
            connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (now,), # 이미 만료된 로그인 정보를 정리
            )

            connection.execute(
                "INSERT INTO auth_sessions (token_hash, username, expires_at) VALUES (?,?,?)",
                (token_hash, account['username'], expires_at), # 토큰 해시/사용자/만료 시각
            )

        return {
            'access_token': token, # 로그인한 사용자에게 토큰 원문을 전달
            'token_type': 'bearer', # 이후 요청에서 사용할 인증 방식
            'expires_in': 3600, # 토큰 사용 가능 시간이며 단위는 초 단위
            'username': account['username'], # 로그인한 계정
        }

    finally:
        connection.close()


@app.get('/auth/me')
def read_current_user(user: dict = Depends(get_current_user)):
    return user


@app.post('/auth/logout')
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail='로그인이 필요합니다.')

    token_hash = hashlib.sha256(credentials.credentials.encode('utf-8')).hexdigest()
    connection = get_connection()

    try:
        with connection:
            connection.execute(
                'DELETE FROM auth_sessions WHERE token_hash = ?',
                (token_hash,),
            )

        return {'message': '로그아웃되었습니다.'}
    finally:
        connection.close()

@app.post('/trades/{trade_id}/receive')
def receive_trade(
    trade_id: int,
    user: dict = Depends(get_current_user),
):
    connection = get_connection()

    try:
        with connection:
            connection.execute('BEGIN IMMEDIATE')

            trade = connection.execute(
                'SELECT * FROM trades WHERE trade_id = ?',
                (trade_id,),
            ).fetchone()

            if trade is None:
                raise HTTPException(404,'거래 기록을 찾을 수 없습니다.')

            if trade['buyer'] != user['username']:
                raise HTTPException(403, '본인이 구매한 물품만 수령할 수 있습니다.')

            receipt = connection.execute(
                'SELECT trade_id FROM trade_item_receipts WHERE trade_id = ?',
                (trade_id,),
            ).fetchone()

            if receipt is not None:
                raise HTTPException(409,'이미 수령한 물품입니다.')

            inventory = connection.execute(
                'SELECT quantity FROM inventory_items WHERE username = ? AND item_name = ?',
                (user['username'], trade['item_name']),
            ).fetchone()

            before_quantity = inventory['quantity'] if inventory is not None else 0
            total_quantity = before_quantity + trade['quantity']

            if total_quantity > 9007199254740991:
                raise HTTPException(409,'아이템 보유 수량 한도를 초과합니다.')

            connection.execute(
                """
                INSERT INTO inventory_items (username, item_name, quantity)
                VALUES (?,?,?)
                ON CONFLICT(username, item_name)
                DO UPDATE SET quantity = excluded.quantity
                """,
                (user['username'],trade['item_name'], total_quantity),
            )

            connection.execute(
                'INSERT INTO trade_item_receipts (trade_id, username, received_at) VALUES (?,?,?)',
                (trade_id, user['username'], int(time.time())),
            )

            return {
                'trade_id': trade_id,
                'item_name': trade['item_name'],
                'received_quantity': trade['quantity'],
                'message': '물품을 수령했습니다.',
            }

    finally:
        connection.close()

@app.get('/me/inventory')
def get_inventory(user:dict = Depends(get_current_user)):
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT inventory_id, item_name, quantity
            FROM inventory_items
            WHERE username = ?
            ORDER BY inventory_id DESC
            """,
            (user['username'],),
        ).fetchall()

        return {
            'total': len(rows),
            'items': [dict(row) for row in rows],
        }
    finally:
        connection.close()