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
encoded = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64")
if not encoded:
    raise ValueError("환경변수 'GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64'가 설정되지 않았습니다.")
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
    try:
        # 데이터 수신
        photo = request.files.get('photo')
        username = request.form.get('username')
        status = request.form.get('status', 'unknown')

        if not photo or not username:
            return jsonify({'error': '사진 또는 사용자 정보가 누락되었습니다.'}), 400

        # 파일 이름 생성
        timestamp = datetime.now()
        filename = secure_filename(timestamp.strftime("%Y-%m-%d_%H-%M-%S") + f"_{uuid4().hex[:8]}.jpg")

        # content_type이 없으면 기본 설정
        content_type = photo.content_type or 'image/jpeg'

        # Firebase Storage 업로드
        blob = storage.bucket().blob(f'photos/{filename}')
        blob.upload_from_file(photo, content_type=content_type)
        blob.make_public()
        photo_url = blob.public_url

        # Firestore 저장
        db.collection("photo").add({
            'filename': filename,
            'timestamp': timestamp,
            'status': status,
            'username': username,
            'url': photo_url
        })

        # 사용자 토큰 확인 후 FCM 발송
        user_doc = db.collection('users').document(username).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            token = user_data.get('token')
            if token:
                try:
                    send_fcm_message(
                        token=token,
                        title="새로운 우편 도착",
                        body="우편함에 새로운 우편이 도착했어요. 사진을 확인하세요!",
                        data={
                            "photo_url": photo_url,
                            "timestamp": timestamp.isoformat(),
                            "status": status,
                            "username": username
                        }
                    )
                except Exception as fcm_error:
                    print(f"[경고] FCM 메시지 전송 실패: {fcm_error}")
            else:
                print(f"[경고] 사용자 {username}에게 등록된 FCM 토큰 없음")
        else:
            print(f"[경고] 사용자 {username} 정보가 Firestore에 없음")

        return jsonify({
            'message': '사진 업로드 및 알림 전송 완료',
            'photo_url': photo_url
        }), 200

    except Exception as e:
        print("서버 오류 발생:", e)
        return jsonify({'error': f'서버 오류 발생: {str(e)}'}), 500
    
@app.route('/photos', methods=['GET'])
def get_photos():
    username = request.args.get('username')
    if not username:
        return jsonify({'error': 'username 파라미터가 필요합니다.'}), 400

    try:
        query = db.collection('photo')\
            .where('username', '==', username)\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
        results = query.stream()

        photo_list = [doc.to_dict() for doc in results]
        return jsonify(photo_list), 200
    except Exception as e:
        print("사진 조회 실패:", e)
        return jsonify({'error': str(e)}), 500

# 서버 지정
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
