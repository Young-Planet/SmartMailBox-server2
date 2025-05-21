import os
import json
import firebase_admin
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from firebase_admin import credentials, messaging, firestore, initialize_app
from datetime import datetime
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__) # python app.py
CORS(app)

# 파베 서비스키
cred_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
cred = credentials.Certificate(cred_info)
firebase_admin.initialize_app(cred)
db = firestore.client()

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

    user_ref = db.collection('users').document(username)
    if user_ref.get().exists:
        return jsonify({'error': '이미 존재하는 사용자입니다.'}), 409

    user_ref.set({
        'username': username,
        'password': password,
        'created_at': firestore.SERVER_TIMESTAMP
    })

    return jsonify({'message': '회원가입 성공!'}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user_ref = db.collection('users').document(username)
    doc = user_ref.get()

    if doc.exists and doc.to_dict().get('password') == password:
        return jsonify({'message': '로그인 성공!', 'username': username}), 200
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render가 지정한 포트 사용
    app.run(host='0.0.0.0', port=port)
