import os
import sqlite3
import firebase_admin
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from firebase_admin import credentials, messaging

app = Flask(__name__) # python app.py
CORS(app)

# 파베 서비스키
cred = credentials.Certificate("firebase/smart-mailbox-2f172-firebase-adminsdk-fbsvc-16f083554b.json")
firebase_admin.initialize_app(cred)

# FCM에 알림 보내기기
def send_fcm_message(token, title, body):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )

    response = messaging.send(message)
    print('Successfully sent message:', response)

# DB 초기화 함수
def init_db():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        # 기존 이벤트 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                status TEXT,
                photo TEXT
            )
        ''')

        # 사용자 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

UPLOAD_FOLDER = 'static/photos'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 라우트: 홈페이지
@app.route('/')
def home():
    return "서버 작동 중"

# 회원가입 API
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': '아이디와 비밀번호를 모두 입력하세요.'}), 400

    try:
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
        return jsonify({'message': '회원가입 성공!'})
    except sqlite3.IntegrityError:
        return jsonify({'error': '이미 존재하는 사용자입니다.'}), 409

# 로그인 API
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()

    if user:
        return jsonify({'message': '로그인 성공!', 'username': username})
    else:
        return jsonify({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}), 401

# 업로드 API
@app.route('/upload', methods=['POST'])
def upload():
    photo = request.files.get('photo')
    status = request.form.get('status', 'unknown')
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    if not photo:
        return jsonify({'error': '사진 파일이 없습니다.'}), 400

    # 안전한 파일명 생성 및 저장
    filename = secure_filename(f"{timestamp}.jpg")
    path = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(path)

    # 이벤트 DB에 기록
    with sqlite3.connect('database.db') as conn:
        conn.execute('INSERT INTO events (timestamp, status, photo) VALUES (?, ?, ?)',
                     (timestamp, status, filename))

    return jsonify({
        'message': '업로드 완료!',
        'photo_url': f'/photo/{filename}'
    })

# 사진 제공 라우트
@app.route('/photo/<filename>')
def get_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# 메인 함수 호출할때 DB
if __name__ == '__main__':
    init_db()