import os
import ssl
import smtplib
from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / '.env'
load_dotenv(ENV_PATH)

def send_email(to_address: str, subject: str, body: str) -> None:
    host = os.getenv('SMTP_HOST', 'smtp.naver.com')
    port = int(os.getenv('SMTP_PORT', '587'))
    username = os.getenv('SMTP_USERNAME','')
    password = os.getenv('SMTP_PASSWORD','')
    from_address = os.getenv('SMTP_FROM','')

    if  not username or not password or not from_address:
        raise RuntimeError('메일 설정이 누락되었습니다. .env를 확인하세요.')

    message = EmailMessage()
    message['Subject'] = subject 
    message['From'] = from_address
    message['To'] = to_address
    message.set_content(body)

    context = ssl.create_default_context()

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)
