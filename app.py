import os
import json
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_admin import credentials, messaging, firestore, storage, initialize_app
from datetime import datetime
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from uuid import uuid4

load_dotenv()

app = Flask(__name__)
CORS(app)

# Firebase Admin SDK 초기화
encoded = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64"]
decoded_json = base64.b64decode(encoded).decode("utf-8")
cred_info = json.loads(decoded_json)
cred = credentials.Certificate(cred_info)

initialize_app(cred, {
    'storageBucket': 'smart-mailbox-2f172.appspot.com'
})

# Firestore & Storage
db = firestore.client()

# FCM 알림 함수
def send_fcm_message(token, title, body, data):
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        token=token,
    )
    response = messaging.send(message)
    print('FCM 전송 성공!:', response)

# 홈페이지
@app.route('/')
def home():
    return "서버 작동 중"

# 회원가입
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

# 로그인
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

# 업로드
@app.route('/upload', methods=['POST'])
def upload():
    photo = request.files.get('photo')
    username = request.form.get('username')
    status = request.form.get('status', 'unknown')

    if not photo or not username:
        return jsonify({'error': '사진 또는 사용자 정보가 누락되었습니다.'}), 400

    # 업로드 시점에 timestamp 및 고유한 파일명 생성
    timestamp = datetime.now()
    filename = secure_filename(timestamp.strftime("%Y-%m-%d_%H-%M-%S") + f"_{uuid4().hex[:8]}.jpg")

    # Firebase Storage 업로드
    blob = storage.bucket().blob(f'photos/{filename}')
    blob.upload_from_file(photo, content_type=photo.content_type)
    blob.make_public()
    photo_url = blob.public_url

    # Firestore에 메타데이터 저장
    db.collection("photo").add({
        'filename': filename,
        'timestamp': timestamp,
        'status': status,
        'username': username,
        'url': photo_url
    })

    # 사용자 토큰으로 FCM 전송
    user_doc = db.collection('users').document(username).get()
    user_data = user_doc.to_dict()

    if user_data and 'token' in user_data:
        send_fcm_message(
            token=user_data['token'],
            title="새로운 우편 도착",
            body="우편함에 새로운 우편이 도착했어요. 사진을 확인하세요!",
            data={
                "photo_url": photo_url,
                "timestamp": timestamp.isoformat(),
                "status": status,
                "username": username
            }
        )
    else:
        print(f"사용자 {username}의 토큰이 Firestore에 존재하지 않음")

    return jsonify({
        'message': '사진 업로드 및 알림 전송 완료',
        'photo_url': photo_url
    }), 200
# 서버 지정
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
