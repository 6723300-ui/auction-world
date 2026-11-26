from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from contextlib import asynccontextmanager
from database import get_connection, initialize_database
from pathlib import Path
from fastapi.responses import FileResponse
import sqlite3
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, ConfigDict, SecretStr
import secrets
import hashlib
import time


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="Auction World API",
    description="게임 아이템 검색·판매·구매·물품 수령·판매 대금 정산을 제공하는 거래소 API입니다.",
    version="0.1.0",
    lifespan=lifespan,
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

@app.get("/")
def read_root():
    return{"message":"게임 데이터 API가 실행 중입니다."}


@app.get("/health")
def health_check():
    return{
        "status":"ok"
    }




trades = [
    {
        "trade_id": 1,
        "seller": "player_001",
        "buyer": "player_002",
        "item_name":"드래곤 라이플",
        "price":1500,
        "quantity": 1,
    },
    {
        "trade_id":2,
        "seller":"player_003",
        "buyer":"player_001",
        "item_name":"회복 키트",
        "price":200,
        "quantity":5,
    },
] 

@app.get("/trades")
def get_trades(
    seller: str | None = None,
    user:dict = Depends(get_current_user),
    ):

    connection = get_connection() 

    try: 
        sql = """SELECT * FROM trades
                WHERE (seller = ? OR buyer = ?)"""
        params = [user['username'], user['username']]

        if seller is not None: 
            sql += " AND seller = ?"
            params.append(seller)

        sql += " ORDER BY trade_id"
        rows = connection.execute(sql,params).fetchall()
        results = [dict(row) for row in rows]

        return {
            'total': len(results),
            'trades': results,
        }
        
    finally: 
        connection.close() 

@app.get('/trades/{trade_id}')
def get_trade(
    trade_id: int,
    user: dict = Depends(get_current_user),
    ):

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT *
            FROM trades
            WHERE trade_id = ?
                AND (seller = ? OR buyer = ?)
            """,
            (trade_id, user['username'],user['username']),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail='해당 거래를 찾을 수 없습니다.',
            )

        return dict(row)

    finally:
        connection.close()

@app.get('/trade-stats') 
def get_trade_stats(
    user: dict = Depends(get_current_user),
):
    connection = get_connection() 

    try: 
        row = connection.execute(
            '''
            SELECT
                COUNT(*) AS trade_count,
                COALESCE(SUM(quantity),0) AS total_quantity,
                COALESCE(SUM(price * quantity),0) AS total_amount
            FROM trades
            WHERE seller = ? or buyer = ?
            ''',
            (user['username'], user['username']),
        ).fetchone() 

        return dict(row)
    finally:
        connection.close()


@app.get('/seller-stats')
def get_seller_stats(
    user: dict = Depends(get_current_user),
):
    connection = get_connection()

    try:
        rows = connection.execute(
            '''
            SELECT 
                seller,
                COUNT(*) AS tade_count,
                SUM(quantity) AS total_quantity,
                SUM(price * quantity) AS total_amount
            FROM trades
            WHERE seller = ?
            GROUP BY seller
            ORDER BY total_amount DESC, seller ASC
            ''',
            (user['username'],),
        ).fetchall()

        sellers = [dict(row) for row in rows]

        return{
            'total': len(sellers),
            'sellers': sellers,
        }

    finally:
        connection.close()

class ListingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_name: str = Field(min_length=1)
    category: Literal['무기','방어구','소비','기타']
    price: int = Field(strict=True, gt=0, le=9007199254740991)
    quantity: int = Field(strict=True, gt=0, le=9007199254740991)


@app.post('/listings', status_code=201)
def create_listing(
    listing: ListingCreate,
    user: dict = Depends(get_current_user),
    ):
    connection = get_connection()

    try:
        with connection:
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

            cursor = connection.execute(
                '''
                INSERT INTO listings(
                    seller, item_name, category, price, quantity, stock_reserved
                )
                VALUES(?,?,?,?,?,1)
                ''',
             (
                    user['username'],
                    listing.item_name,
                    listing.category,
                    listing.price,
                    listing.quantity,
                ),
         )
            
            row = connection.execute(
                'SELECT * FROM listings WHERE listing_id =?',
                (cursor.lastrowid,),
            ).fetchone()

        return dict(row)

    finally:
        connection.close()
                
@app.get('/listings')
def get_listing(
    keyword: str | None = None,
    category: Literal['무기', '방어구', '소비', '기타'] | None = None,
    min_price: int | None = Query(default=None, ge=0, le=9007199254740991),
    max_price: int | None = Query(default=None, ge=0, le=9007199254740991),
    sort_by: Literal['latest','price_low','price_high'] = 'latest',
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20,ge=1,le=100),
):
    if min_price is not None and max_price is not None:
        if min_price > max_price:
            raise HTTPException(
                status_code= 422,
                detail='최저 가격은 최고 가격보다 클 수 없습니다.'
            )
    connection = get_connection()

    try:
        sql = "SELECT * FROM listings WHERE status = '판매중'"
        params = []

        if keyword and keyword.strip():
            sql += " AND instr(item_name, ?) > 0"
            params.append(keyword.strip())
            
        if category is not None:
            sql += " AND category = ?"
            params.append(category)

        if min_price is not None:
            sql += " AND price >= ?"
            params.append(min_price)

        if max_price is not None:
            sql += " AND price <= ?"
            params.append(max_price)

        sort_options = {
            'latest': 'listing_id DESC',
            'price_low': 'price ASC, listing_id DESC',
            'price_high': 'price DESC, listing_id DESC',
        }

        total = connection.execute(
            "SELECT COUNT(*) FROM (" + sql + ") AS matched",
            params,
        ).fetchone()[0]
 
        sql += " ORDER BY " + sort_options[sort_by]

        sql += " LIMIT ? OFFSET ?"
        params.extend([page_size,(page - 1) * page_size])

        rows = connection.execute(sql, params).fetchall()
        listings = [dict(row) for row in rows]

        return {
            'total': total,
            'page': page,
            'page_size':page_size,
            'total_pages':(total + page_size - 1) // page_size,
            'listings': listings,
        }

    finally:
        connection.close()

@app.get('/market', include_in_schema=False)
def market_page():
    html_path = Path(__file__).resolve().parent / 'market.html'
    return FileResponse(html_path)

@app.get('/users/{username}')
def get_user(
    username: str,
    user: dict = Depends(get_current_user),
):
    if username != user['username']:
        raise HTTPException(
            status_code=403,
            detail='본인의 잔액만 조회할 수 있습니다.',
        )
    
    connection = get_connection()

    try:
        row = connection.execute(
            'SELECT username, balance FROM users WHERE username = ?',
            (username,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail='사용자를 찾을 수 없습니다.',
            )

        return dict(row)

    finally:
        connection.close()

class PurcjaseCreate(BaseModel):
    quantity: int = Field(strict=True, gt=0, le=9007199254740991)


@app.post('/listings/{listing_id}/purchase',status_code=201)
def purchase_listing(
    listing_id:int, 
    purchase: PurcjaseCreate,
    user: dict = Depends(get_current_user),
    ):
    buyer_username = user['username']
    connection = get_connection()

    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            listing = connection.execute(
                "SELECT * FROM listings WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()

            if listing is None:
                raise HTTPException(404, '판매 정보를 찾을 수 없습니다.')

            if listing['status'] != '판매중':
                raise HTTPException(409, '판매 중인 아이템이 아닙니다.')

            if purchase.quantity > listing['quantity']:
                raise HTTPException(409,'판매 수량이 부적합니다.')


            if buyer_username == listing['seller']:
                raise HTTPException(400,'자신의 아이템은 구매할 수 없습니다.')

            buyer = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (buyer_username,),
            ).fetchone()

            seller = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (listing['seller'],),
            ).fetchone()

            if buyer is None or seller is None:
                raise HTTPException(404, '구매자 또는 판매자 계정이 없습니다.')

            total = listing['price'] * purchase.quantity

            if buyer['balance'] < total:
                raise HTTPException(400, '보유 재화가 부족합니다.')

            connection.execute(
                "UPDATE users SET balance = balance - ? WHERE username = ?",
                (total, buyer_username),
            )

            remaining = listing['quantity'] - purchase.quantity
            status = '판매완료' if remaining == 0 else '판매중'

            connection.execute(
                "UPDATE listings SET quantity = ?, status = ? WHERE listing_id = ?",
                (remaining, status, listing_id),
            )

            cursor = connection.execute(
                """
                INSERT INTO trades (seller, buyer, item_name, price, quantity)
                VALUES(?,?,?,?,?)
                """,
                (
                    listing['seller'],
                    buyer_username,
                    listing['item_name'],
                    listing['price'],
                    purchase.quantity,
                ),
            )
            connection.execute(
                """
                INSERT INTO trade_payouts (trade_id, seller, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    listing['seller'],
                    total,
                    int(time.time()),
                ),
            )

            result = {
                'trade_id': cursor.lastrowid,
                'item_name': listing['item_name'],
                'quantity': purchase.quantity,
                'total_amount': total,
                'buyer_balance': buyer['balance'] - total,
                'remaining_quantity': remaining,
                'status': status,
            }

        return result
    finally:
        connection.close()

@app.get('/me/trades')
def get_user_trades(
    role: Literal['buyer','seller'] = 'buyer',
    user: dict = Depends(get_current_user),
):
    connection = get_connection()
    column = 'buyer' if role == 'buyer' else 'seller'

    try:
        rows = connection.execute(
            f"""
            SELECT 
                trade_id, item_name, seller, buyer, price, quantity,
                EXISTS (
                    SELECT 1 FROM trade_item_receipts
                    WHERE trade_item_receipts.trade_id = trades.trade_id
                    ) AS received,
                    COALESCE(
                        (
                            SELECT CASE
                                WHEN received_at IS NULL THEN 'pending'
                                ELSE 'received'
                            END
                            FROM trade_payouts
                            WHERE trade_payouts.trade_id = trades.trade_id
                    ),
                    'legacy'
                ) AS payout_status
            FROM trades -- 거래 기록 테이블 조회
            WHERE {column} = ? -- 해당 사용자가 구매자인 거래만 가져옴
            ORDER BY trade_id DESC -- 최근 거래부터 표시
            """,
            (user['username'],),
        ).fetchall()

        return {
            'total':len(rows),
            'trades': [dict(row) for row in rows],
        }

    finally:
        connection.close()
            
@app.get('/me/listings')
def get_user_listings(user: dict = Depends(get_current_user)):
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                listing_id,
                item_name,
                category,
                price,
                quantity,
                status
            FROM listings
            WHERE seller = ?
            ORDER BY listing_id DESC
            """,
            (user['username'],),
        ).fetchall()

        return {
            'total': len(rows),
            'listings': [dict(row) for row in rows],
        }

    finally:
        connection.close()


@app.post('/listings/{listing_id}/cancel')
def cancel_listing(
    listing_id: int,
    user: dict = Depends(get_current_user),
):
    connection = get_connection()
    
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            listing = connection.execute( 
                "SELECT * FROM listings WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()

            if listing is None:
                raise HTTPException(404,'판매 정보를 찾을 수 없습니다.') 

            if listing['seller'] != user['username']:
                raise HTTPException(403,'본인이 등록한 아이템만 취소할 수 있습니다.')

            if listing['status'] != '판매중':
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
                (listing_id,),
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
    secrets.token_urlsafe(32)
)

class LoginRequest(BaseModel):
    username: str = Field(
        min_length=3, max_length=32,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    password:SecretStr=Field(
        min_length=1, max_length=128,
    )

@app.post('/auth/login')
def login(request: LoginRequest):
    connection = get_connection()

    try:
        account = connection.execute(
            "SELECT username, password_hash FROM user_credentials WHERE username = ?",
            (request.username,),
        ).fetchone()

        stored_hash = (
            account['password_hash'] if account is not None
            else DUMMY_PASSWORD_HASH
        )

        password_matches = password_hasher.verify(
            request.password.get_secret_value(),
            stored_hash,
        )

        if account is None or not password_matches:
            raise HTTPException(
                status_code=401,
                detail='아이디 또는 비밀번호가 올바르지 않습니다.',
            )

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        now = int(time.time())
        expires_at = now + 3600

        with connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (now,),
            )

            connection.execute(
                "INSERT INTO auth_sessions (token_hash, username, expires_at) VALUES (?,?,?)",
                (token_hash, account['username'], expires_at),
            )

        return {
            'access_token': token,
            'token_type': 'bearer',
            'expires_in': 3600,
            'username': account['username'],
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

@app.post('/trades/{trade_id}/payout')
def receive_payout(
    trade_id: int,
    user: dict = Depends(get_current_user),
):
    connection = get_connection()

    try:
        with connection:
            connection.execute('BEGIN IMMEDIATE')

            trade = connection.execute(
                'SELECT seller FROM trades WHERE trade_id = ?',
                (trade_id,),
            ).fetchone()

            if trade is None:
                raise HTTPException(404,'거래를 찾을 수 없습니다.')

            if trade['seller'] != user['username']:
                raise HTTPException(403, '본인의 판매 대금만 수령할 수 있습니다.')

            payout = connection.execute(
                'SELECT amount, received_at FROM trade_payouts WHERE trade_id = ? AND seller = ?',
                (trade_id,user['username']),
            ).fetchone()

            if payout is None:
                raise HTTPException(409,'별도로 수령할 판매 대금이 없습니다.')

            if payout['received_at'] is not None:
                raise HTTPException(409,'이미 수령한 판매 대금입니다.')

            amount = payout['amount']
            balance_limit = 9007199254740991

            updated = connection.execute(
                """
                UPDATE users
                SET balance = balance + ?
                WHERE username = ?
                    AND balance <= ?
                """,
                (amount, user['username'],balance_limit - amount),
            )

            if updated.rowcount != 1:
                raise HTTPException(409,'보유 재화 한도를 초과하여 수령할 수 없습니다.')

            connection.execute(
                'UPDATE trade_payouts SET received_at =? WHERE trade_id = ?',
                (int(time.time()), trade_id),
            )

            balance = connection.execute(
                'SELECT balance FROM users WHERE username = ?',
                (user['username'],),
            ).fetchone()['balance']

            result = {
                'trade_id': trade_id,
                'received_amount': amount,
                'balance': balance,
                'message': '판매 대금을 수령했습니다.',
            }

        return result

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