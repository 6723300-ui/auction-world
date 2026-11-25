import database
from main import app
from fastapi.testclient import TestClient

def test_logout_and_expired_token(tmp_path,monkeypatch):
    monkeypatch.setattr(database,'DB_PATH', tmp_path / 'auth.db')

    with TestClient(app) as client:
        account = {
            'username':'auth_test',
            'password':'TestAuction!2026',
        }
        signup = client.post('/auth/signup',json=account)
        assert signup.status_code == 201, signup.text

        assert client.get('/auth/me').status_code == 401
        assert client.post('/auth/logout').status_code == 401

        wrong_login = client.post('/auth/login',json={
            'username':'auth_test',
            'password':'WrongPassword!2026',
        })
        assert wrong_login.status_code == 401

        first_login = client.post('/auth/login',json=account)
        assert first_login.status_code == 200, first_login.text
        first_headers = {
            'Authorization':'Bearer ' + first_login.json()['access_token'],
        }
        assert client.get('/auth/me', headers=first_headers).status_code == 200

        second_login = client.post('/auth/login', json=account)
        assert second_login.status_code == 200, second_login.text
        second_headers = {
            'Authorization': 'Bearer ' + second_login.json()['access_token'],
        }

        logout = client.post('/auth/logout',headers=first_headers)
        assert logout.status_code == 200, logout.text
        assert client.get('/auth/me', headers=first_headers).status_code == 401
        assert client.get('/auth/me', headers=second_headers).status_code == 200

        connection = database.get_connection()
        try:
            with connection:
                connection.execute(
                    'UPDATE auth_sessions SET expires_at = ? WHERE username = ?',
                    (0,'auth_test'),
                )
        finally:
            connection.close()

        expired = client.get('/auth/me', headers=second_headers)
        assert expired.status_code == 401

        fake_headers = {'Authorization':'Bearer invalid-test-token'}
        assert client.get('/auth/me',headers=fake_headers).status_code == 401