import os
import json
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_admin import credentials, messaging, firestore, initialize_app
from google.cloud import storage
from google.oauth2 import service_account
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
initialize_app(cred)

credentials_gcp = service_account.Credentials.from_service_account_info(cred_info)
storage_client = storage.Client(credentials=credentials_gcp, project="smart-mailbox-2f172")
bucket = storage_client.get_bucket("smart-mailbox-user-content")

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

    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).get()
    if query:
        return jsonify({'error': '이미 존재하는 사용자입니다.'}), 409

    uid = str(uuid4())
    user_ref = db.collection('users').document(uid)
    user_ref.set({
        'uid': uid,
        'username': username,
        'password': password,
        'created_at': firestore.SERVER_TIMESTAMP
    })

    return jsonify({'message': '회원가입 성공!', 'uid': uid}), 200

# 로그인
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).get()

    for doc in query:
        user = doc.to_dict()
        if user.get('password') == password:
            return jsonify({'message': '로그인 성공!', 'username': username, 'uid': user.get('uid')}), 200

    return jsonify({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}), 401

# 사진 업로드 (uid 기반 경로 사용)
@app.route('/upload', methods=['POST'])
def upload():
    try:
        photo = request.files.get('photo')
        uid = request.form.get('uid')
        status = request.form.get('status', 'unknown')

        if not photo or not uid:
            return jsonify({'error': '사진 또는 사용자 정보가 누락되었습니다.'}), 400

        user_doc = db.collection('users').document(uid).get()
        if not user_doc.exists:
            return jsonify({'error': '유효하지 않은 사용자입니다.'}), 404

        username = user_doc.to_dict().get('username')
        timestamp = datetime.now()
        filename = secure_filename(timestamp.strftime("%Y-%m-%d_%H-%M-%S") + f"_{uuid4().hex[:8]}.jpg")
        content_type = photo.content_type or 'image/jpeg'

        blob = bucket.blob(f'photos/{uid}/{filename}')
        blob.upload_from_file(photo, content_type=content_type)

        # 퍼블릭 권한 부여
        blob.make_public()

        # 만료 없는 퍼블릭 URL 사용
        photo_url = blob.public_url

        print(f"[디버깅] 최종 photo_url 값: {photo_url}")

        db.collection("photo").add({
            'uid': uid,
            'username': username,
            'filename': filename,
            'timestamp': timestamp,
            'status': status,
            'url': photo_url
        })

        token = user_doc.to_dict().get('token')
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
                        "uid": uid
                    }
                )
            except Exception as fcm_error:
                print(f"[경고] FCM 메시지 전송 실패: {fcm_error}")

        return jsonify({'message': '사진 업로드 및 알림 전송 완료', 'photo_url': photo_url}), 200

    except Exception as e:
        print("서버 오류 발생:", e)
        return jsonify({'error': f'서버 오류 발생: {str(e)}'}), 500

@app.route('/photos', methods=['GET'])
def get_photos():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({'error': 'uid 파라미터가 필요합니다.'}), 400

    try:
        query = db.collection('photo')\
            .where('uid', '==', uid)\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
        results = query.stream()

        photo_list = [doc.to_dict() for doc in results]
        return jsonify(photo_list), 200
    
    except Exception as e:

        import traceback
        print("[인덱스 오류 가능성 있음] 사진 조회 실패:")
        traceback.print_exc()  # <- 예외 전체 메시지 출력
    return jsonify({'error': str(e)}), 500

# FCM 토큰 등록용 API
@app.route('/register_token', methods=['POST'])
def register_token():
    data = request.get_json()
    uid = data.get('uid')
    token = data.get('token')

    if not uid or not token:
        return jsonify({'error': 'uid와 token이 필요합니다.'}), 400

    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return jsonify({'error': '해당 uid의 사용자가 존재하지 않습니다.'}), 404

    user_ref.update({'token': token})

    return jsonify({'message': '토큰 등록 성공'}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

#서버 최신 업데이트 덮어쓰기기