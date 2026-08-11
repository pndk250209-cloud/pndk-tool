# webpndk.py - Zalo Tool Treo Ngôn + Nhây Tag + Messenger Spam
# -*- coding: utf-8 -*-

# ===== CHẶN LOG =====
import logging
import sys
import os
import contextlib
import hashlib
import uuid
import ssl
import json
import time
import threading
import base64
import requests
from datetime import datetime
from Crypto.Cipher import AES
import paho.mqtt.client as mqtt

# Tắt tất cả log
logging.getLogger("zalo").setLevel(logging.ERROR)
logging.getLogger("zlapi").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("http.client").setLevel(logging.ERROR)
logging.getLogger("paho-mqtt").setLevel(logging.WARNING)

# Chặn stdout/stderr
@contextlib.contextmanager
def suppress_output():
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

def null_print(*args, **kwargs):
    pass

import builtins
builtins.print = null_print

# ===== IMPORT THƯ VIỆN =====
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import asyncio
import random
from account_manager import AccountManager
from zalo_login_zlapi import (
    login_with_cookies_imei_async,
    get_box_chats_async,
    send_full_message_with_style_async
)

# ===== LOGGING CHO WEB =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('web.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== FLASK APP =====
app = Flask(__name__)
app.secret_key = 'pndk_zalo_tool_secret_key_2024_v2'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===== USER MANAGER =====
USER_FILE = "users.json"

def load_users():
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    with open(USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ===== ACCOUNT MANAGER =====
account_managers = {}

def get_account_manager():
    username = session.get('username')
    if not username:
        return None
    if username not in account_managers:
        account_managers[username] = AccountManager(username)
    return account_managers[username]

# ===== SESSION =====
current_session = {}
spam_tasks = {}
nhaytag_tasks = {}

# ===== MESSENGER SPAM ENGINE =====
class MQTTSpamEngine:
    def __init__(self, cookie, id_boxes, message, delay):
        self.cookie = cookie
        self.id_boxes = id_boxes if isinstance(id_boxes, list) else [id_boxes]
        self.message = message
        self.delay = max(0.1, float(delay))
        self.running = True
        self.threads = []
        self.client = None
        self.token = None

    def _get_token(self, cookie):
        parts = cookie.split(';')
        c_user = xs = None
        for part in parts:
            part = part.strip()
            if part.startswith('c_user='):
                c_user = part.split('=')[1]
            elif part.startswith('xs='):
                xs = part.split('=')[1]
        return f"{c_user}|{xs}" if c_user and xs else cookie

    def _create_mqtt(self, cookie):
        try:
            token = self._get_token(cookie)
            client_id = f"mqttwsclient_{uuid.uuid4().hex[:8]}"
            client = mqtt.Client(
                client_id=client_id,
                transport="websockets",
                protocol=mqtt.MQTTv31
            )
            client.username_pw_set(
                username=json.dumps({
                    "u": token.split('|')[0] if '|' in token else token,
                    "s": 1,
                    "chat_on": True,
                    "fg": True,
                    "d": str(uuid.uuid4()),
                    "ct": "websocket",
                    "mqtt_sid": "",
                    "aid": 219994525426954,
                    "st": [],
                    "pm": [],
                    "cp": 3,
                    "ecp": 10,
                    "pack": []
                }),
                password=""
            )
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
            client.ws_set_options(path="/chat", headers={
                "Cookie": cookie,
                "Origin": "https://www.facebook.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            client.connect("edge-chat.facebook.com", 443, 60)
            client.loop_start()
            time.sleep(2)
            if client.is_connected():
                return client, token
            else:
                client.loop_stop()
                client.disconnect()
                return None, None
        except:
            return None, None

    def _send_message(self, client, token, thread_id, message, box_id):
        while self.running:
            try:
                if not client.is_connected():
                    try:
                        client.reconnect()
                        time.sleep(1)
                        if not client.is_connected():
                            new_client, new_token = self._create_mqtt(self.cookie)
                            if new_client is None:
                                time.sleep(5)
                                continue
                            client = new_client
                            token = new_token
                    except:
                        time.sleep(5)
                        continue

                while self.running:
                    try:
                        msg_id = str(int(time.time() * 1000))
                        payload = {
                            "body": message,
                            "msgid": msg_id,
                            "sender_fbid": token.split('|')[0] if '|' in token else token,
                            "to": thread_id,
                            "offline_threading_id": msg_id
                        }
                        result = client.publish("/send_message2", json.dumps(payload), qos=1)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            logger.info(f"[MQTT] Thanh cong box {box_id}")
                        else:
                            logger.warning(f"[MQTT] That bai box {box_id} ma loi {result.rc}")
                            if result.rc in (mqtt.MQTT_ERR_CONN_LOST, mqtt.MQTT_ERR_NO_CONN):
                                break
                        time.sleep(self.delay)
                    except Exception as e:
                        logger.error(f"[MQTT] Loi gui: {e}")
                        time.sleep(self.delay)
                        break
            except Exception as e:
                logger.error(f"[MQTT] Loi nghiem trong: {e}")
                time.sleep(5)

    def start(self):
        self.client, self.token = self._create_mqtt(self.cookie)
        if self.client is None:
            logger.error("[MQTT] Khong the tao client ban dau")
            return
        for box_id in self.id_boxes:
            t = threading.Thread(
                target=self._send_message,
                args=(self.client, self.token, box_id, self.message, box_id),
                daemon=True
            )
            t.start()
            self.threads.append(t)

    def stop(self):
        self.running = False
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=1)
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except:
            pass

# ===== ZALO API =====
def now():
    return int(time.time() * 1000)

def zalo_encode(params, key):
    key = base64.b64decode(key)
    iv = bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = json.dumps(params).encode()
    pad_len = AES.block_size - len(plaintext) % AES.block_size
    padded = plaintext + bytes([pad_len] * pad_len)
    return base64.b64encode(cipher.encrypt(padded)).decode()

def zalo_decode(encrypted_data, key):
    key = base64.b64decode(key)
    iv = bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(base64.b64decode(encrypted_data))
    pad_len = decrypted[-1]
    return decrypted[:-pad_len].decode('utf-8', errors='ignore')

def parse_cookie_string_zalo(cookie_str):
    try:
        cookie_str = cookie_str.strip()
        if cookie_str.startswith("{") and cookie_str.endswith("}"):
            return json.loads(cookie_str)
        data = {}
        for part in cookie_str.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                data[k.strip()] = v.strip()
        return data if data else None
    except:
        return None

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://chat.zalo.me",
    "Referer": "https://chat.zalo.me/",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}

class ZaloAPIBot:
    def __init__(self, imei, cookies):
        self.session = requests.Session()
        self.imei = imei
        self.secret_key = None
        self.uid = None
        self.session.headers.update(HEADERS)
        self.session.cookies.update(cookies)
        self.login()

    def login(self):
        url = "https://wpa.chat.zalo.me/api/login/getLoginInfo"
        params = {"imei": self.imei, "type": 30, "client_version": 645, "ts": now()}
        response = self.session.get(url, params=params)
        try:
            data = response.json()
        except Exception:
            raise Exception("❌ Không thể phân tích JSON từ phản hồi!")
        user_data = data.get("data")
        if not isinstance(user_data, dict):
            raise Exception("❌ Không nhận được thông tin người dùng")
        self.uid = user_data.get("send2me_id")
        self.secret_key = user_data.get("zpw_enk")
        if not self.secret_key:
            raise Exception("❌ Không lấy được secret_key")

    def fetch_groups(self):
        url = "https://tt-group-wpa.chat.zalo.me/api/group/getlg/v4"
        params = {"zpw_ver": 645, "zpw_type": 30}
        response = self.session.get(url, params=params)
        data = response.json()
        decoded = zalo_decode(data["data"], self.secret_key)
        parsed = json.loads(decoded)
        grid_map = parsed.get("data", {}).get("gridVerMap", {})
        groups = []
        for group_id in sorted(grid_map.keys(), key=lambda x: int(x)):
            info = self.fetch_group_info(group_id)
            groups.append({
                "id": group_id,
                "name": info["name"],
                "members": info["totalMember"]
            })
        return groups

    def fetch_group_info(self, group_id):
        url = "https://tt-group-wpa.chat.zalo.me/api/group/getmg-v2"
        params = {"zpw_ver": 645, "zpw_type": 30}
        encoded = zalo_encode({"gridVerMap": json.dumps({str(group_id): 0})}, self.secret_key)
        response = self.session.post(url, params=params, data={"params": encoded})
        result = response.json()
        decoded = zalo_decode(result["data"], self.secret_key)
        parsed = json.loads(decoded)
        info = parsed.get("data", {}).get("gridInfoMap", {}).get(str(group_id), {})
        return {
            "name": info.get("name", "(Không rõ tên)"),
            "totalMember": info.get("totalMember", "?")
        }

    def send_message(self, message, thread_id):
        url = "https://tt-group-wpa.chat.zalo.me/api/group/sendmsg"
        payload = {
            "message": message,
            "clientId": str(now()),
            "imei": self.imei,
            "visibility": 0,
            "grid": str(thread_id)
        }
        encoded = zalo_encode(payload, self.secret_key)
        response = self.session.post(url, params={"zpw_ver": 645, "zpw_type": 30}, data={"params": encoded})
        return response.json()

class SpamToolZalo:
    def __init__(self, imei, cookies, thread_ids, messages):
        self.imei = imei
        self.cookies = cookies
        self.thread_ids = thread_ids
        self.messages = messages
        self.api = None
        self.running = False

    def start_spam(self, delay):
        self.api = ZaloAPIBot(self.imei, self.cookies)
        self.running = True
        while self.running:
            for thread_id in self.thread_ids:
                for message in self.messages:
                    if not self.running:
                        break
                    try:
                        self.api.send_message(message, thread_id)
                        logger.info(f"[ZALO] Gửi thành công vào nhóm {thread_id}")
                    except Exception as e:
                        logger.error(f"[ZALO] Lỗi: {e}")
                    time.sleep(delay)

    def stop(self):
        self.running = False

# ===== BIẾN LƯU TASK =====
messenger_tasks = {}
zalo_spam_tasks = {}

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, username=session.get('username', 'User'))

# ===== AUTH ROUTES =====
@app.route('/login')
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ!'})
        
        users = load_users()
        user = users.get(username)
        
        if not user or user.get('password') != hash_password(password):
            return jsonify({'success': False, 'message': 'Sai tên đăng nhập hoặc mật khẩu!'})
        
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': 'Đăng nhập thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ!'})
        
        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Tên đăng nhập phải có ít nhất 3 ký tự!'})
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Mật khẩu phải có ít nhất 6 ký tự!'})
        
        users = load_users()
        
        if username in users:
            return jsonify({'success': False, 'message': 'Tên đăng nhập đã tồn tại!'})
        
        users[username] = {
            'password': hash_password(password),
            'created_at': datetime.now().isoformat()
        }
        save_users(users)
        return jsonify({'success': True, 'message': 'Đăng ký thành công! Vui lòng đăng nhập.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    username = session.get('username')
    if username:
        if username in account_managers:
            del account_managers[username]
    session.clear()
    return jsonify({'success': True, 'message': 'Đã đăng xuất!'})

@app.before_request
def require_login():
    allowed_routes = ['login_page', 'api_login', 'api_register', 'static']
    if request.endpoint in allowed_routes:
        return
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))

# ===== FILE MANAGEMENT =====
@app.route('/upload_content', methods=['POST'])
def upload_content():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'Không có file!'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'Chưa chọn file!'})
        
        username = session.get('username', 'default')
        platform = request.form.get('platform', 'zalo')
        folder = f"uploads/{username}/{platform}"
        os.makedirs(folder, exist_ok=True)
        
        path = os.path.join(folder, file.filename)
        file.save(path)
        
        return jsonify({'success': True, 'message': f'Đã upload {file.filename}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_files/<platform>', methods=['GET'])
def get_files(platform):
    try:
        username = session.get('username', 'default')
        folder = f"uploads/{username}/{platform}"
        if not os.path.exists(folder):
            return jsonify({'files': []})
        
        files = os.listdir(folder)
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'files': [], 'error': str(e)})

@app.route('/delete_file/<platform>/<filename>', methods=['DELETE'])
def delete_file(platform, filename):
    try:
        username = session.get('username', 'default')
        path = f"uploads/{username}/{platform}/{filename}"
        if os.path.exists(path):
            os.remove(path)
            return jsonify({'success': True, 'message': 'Đã xóa file!'})
        return jsonify({'success': False, 'message': 'File không tồn tại!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/read_file/<platform>/<filename>', methods=['GET'])
def read_file(platform, filename):
    try:
        username = session.get('username', 'default')
        path = f"uploads/{username}/{platform}/{filename}"
        if not os.path.exists(path):
            return jsonify({'success': False, 'message': 'File không tồn tại!'})
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ===== MESSENGER ROUTES =====
@app.route('/start_messenger_spam', methods=['POST'])
def start_messenger_spam():
    try:
        data = request.get_json()
        cookie = data.get('cookie', '').strip()
        box_ids = data.get('box_ids', [])
        content = data.get('content', '')
        delay = float(data.get('delay', 2))
        filename = data.get('filename', '')
        
        if not cookie:
            return jsonify({'success': False, 'message': 'Thiếu cookie!'})
        if not box_ids:
            return jsonify({'success': False, 'message': 'Chọn ít nhất 1 box!'})
        if not content:
            return jsonify({'success': False, 'message': 'Không có nội dung!'})
        
        username = session.get('username', 'default')
        
        if filename:
            path = f"uploads/{username}/messenger/{filename}"
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
        
        task_id = f"messenger_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        engine = MQTTSpamEngine(cookie, box_ids, content, delay)
        messenger_tasks[task_id] = {
            'engine': engine,
            'box_ids': box_ids,
            'delay': delay,
            'filename': filename,
            'status': 'running',
            'started_at': datetime.now().isoformat()
        }
        
        engine.start()
        
        return jsonify({'success': True, 'message': f'Đã bắt đầu spam Messenger!', 'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop_messenger_spam/<task_id>', methods=['POST'])
def stop_messenger_spam(task_id):
    try:
        if task_id not in messenger_tasks:
            return jsonify({'success': False, 'message': 'Task không tồn tại!'})
        
        messenger_tasks[task_id]['engine'].stop()
        messenger_tasks[task_id]['status'] = 'stopped'
        
        return jsonify({'success': True, 'message': f'Đã dừng task {task_id}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_messenger_tasks', methods=['GET'])
def get_messenger_tasks():
    tasks = []
    for tid, task in messenger_tasks.items():
        tasks.append({
            'id': tid,
            'box_count': len(task.get('box_ids', [])),
            'delay': task.get('delay', 0),
            'filename': task.get('filename', ''),
            'status': task.get('status', 'unknown'),
            'started_at': task.get('started_at', '')
        })
    return jsonify({'tasks': tasks})

# ===== ZALO SPAM ROUTES =====
@app.route('/get_zalo_groups', methods=['POST'])
def get_zalo_groups():
    try:
        data = request.get_json()
        imei = data.get('imei', '').strip()
        cookie = data.get('cookie', '').strip()
        
        if not imei or not cookie:
            return jsonify({'success': False, 'message': 'Thiếu IMEI hoặc Cookie!'})
        
        cookies = parse_cookie_string_zalo(cookie)
        if not cookies:
            return jsonify({'success': False, 'message': 'Cookie Zalo không hợp lệ!'})
        
        bot = ZaloAPIBot(imei, cookies)
        groups = bot.fetch_groups()
        
        return jsonify({'success': True, 'groups': groups})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/start_zalo_spam', methods=['POST'])
def start_zalo_spam():
    try:
        data = request.get_json()
        imei = data.get('imei', '').strip()
        cookie = data.get('cookie', '').strip()
        group_ids = data.get('group_ids', [])
        content = data.get('content', '')
        delay = float(data.get('delay', 2))
        filename = data.get('filename', '')
        
        if not imei or not cookie:
            return jsonify({'success': False, 'message': 'Thiếu IMEI hoặc Cookie!'})
        if not group_ids:
            return jsonify({'success': False, 'message': 'Chọn ít nhất 1 nhóm!'})
        if not content:
            return jsonify({'success': False, 'message': 'Không có nội dung!'})
        
        username = session.get('username', 'default')
        
        if filename:
            path = f"uploads/{username}/zalo/{filename}"
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
        
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        cookies = parse_cookie_string_zalo(cookie)
        
        task_id = f"zalospam_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        tool = SpamToolZalo(imei, cookies, group_ids, lines)
        thread = threading.Thread(target=tool.start_spam, args=(delay,), daemon=True)
        thread.start()
        
        zalo_spam_tasks[task_id] = {
            'tool': tool,
            'thread': thread,
            'group_ids': group_ids,
            'delay': delay,
            'filename': filename,
            'status': 'running',
            'started_at': datetime.now().isoformat()
        }
        
        return jsonify({'success': True, 'message': f'Đã bắt đầu spam Zalo!', 'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop_zalo_spam/<task_id>', methods=['POST'])
def stop_zalo_spam(task_id):
    try:
        if task_id not in zalo_spam_tasks:
            return jsonify({'success': False, 'message': 'Task không tồn tại!'})
        
        zalo_spam_tasks[task_id]['tool'].stop()
        zalo_spam_tasks[task_id]['status'] = 'stopped'
        
        return jsonify({'success': True, 'message': f'Đã dừng task {task_id}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_zalo_spam_tasks', methods=['GET'])
def get_zalo_spam_tasks():
    tasks = []
    for tid, task in zalo_spam_tasks.items():
        tasks.append({
            'id': tid,
            'group_count': len(task.get('group_ids', [])),
            'delay': task.get('delay', 0),
            'filename': task.get('filename', ''),
            'status': task.get('status', 'unknown'),
            'started_at': task.get('started_at', '')
        })
    return jsonify({'tasks': tasks})

# ===== HTML TEMPLATE (RÚT GỌN) =====
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập - WEB PNDK TOOL ĐA APP</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', sans-serif;
            position: relative;
            overflow: hidden;
        }
        body::before {
            content: '';
            position: absolute;
            width: 200%;
            height: 200%;
            top: -50%;
            left: -50%;
            background: radial-gradient(ellipse at 30% 50%, rgba(102, 126, 234, 0.15), transparent 60%),
                        radial-gradient(ellipse at 70% 50%, rgba(118, 75, 162, 0.15), transparent 60%);
            animation: rotateBg 20s linear infinite;
        }
        @keyframes rotateBg { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .login-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(30px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 30px;
            padding: 45px 40px;
            max-width: 440px;
            width: 100%;
            box-shadow: 0 30px 80px rgba(0,0,0,0.5);
            position: relative;
            z-index: 1;
            animation: slideUp 0.8s ease-out;
        }
        @keyframes slideUp { 0% { transform: translateY(50px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }
        .login-card .logo { text-align: center; margin-bottom: 30px; }
        .login-card .logo .logo-icon {
            width: 80px; height: 80px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 15px;
            font-size: 40px;
            color: white;
            box-shadow: 0 15px 40px rgba(102,126,234,0.3);
            animation: pulseLogo 2s ease-in-out infinite;
        }
        @keyframes pulseLogo { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        .login-card .logo h3 {
            font-family: 'Orbitron', monospace;
            font-weight: 900;
            font-size: 24px;
            background: linear-gradient(135deg, #fff, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: none;
            margin: 0;
        }
        .login-card .logo p { color: rgba(255,255,255,0.5); font-size: 13px; letter-spacing: 2px; margin-top: 5px; }
        .form-control {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 12px 16px;
            color: #fff;
            transition: all 0.3s;
        }
        .form-control:focus {
            background: rgba(255,255,255,0.08);
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102,126,234,0.2);
            color: #fff;
        }
        .form-control::placeholder { color: rgba(255,255,255,0.3); }
        .form-label { color: rgba(255,255,255,0.6); font-weight: 600; font-size: 13px; }
        .btn-login {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: white;
            padding: 14px;
            border-radius: 12px;
            font-weight: 700;
            width: 100%;
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        .btn-login:hover { transform: translateY(-3px); box-shadow: 0 15px 40px rgba(102,126,234,0.4); color: white; }
        .btn-login:disabled { opacity: 0.7; transform: none; }
        .switch-link { text-align: center; margin-top: 20px; color: rgba(255,255,255,0.5); }
        .switch-link a { color: #a78bfa; text-decoration: none; font-weight: 600; transition: 0.3s; }
        .switch-link a:hover { color: #fff; text-decoration: underline; }
        .alert { border-radius: 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.8); }
        .alert-success { border-color: rgba(40,167,69,0.3); color: #28a745; }
        .alert-danger { border-color: rgba(220,53,69,0.3); color: #dc3545; }
        .password-toggle { position: relative; }
        .password-toggle .toggle-eye {
            position: absolute;
            right: 15px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
            color: rgba(255,255,255,0.4);
            transition: 0.3s;
        }
        .password-toggle .toggle-eye:hover { color: rgba(255,255,255,0.8); }
        .footer-text { text-align: center; margin-top: 20px; color: rgba(255,255,255,0.2); font-size: 12px; letter-spacing: 1px; }
        .footer-text .heart { color: #ff4757; animation: heartBeat 1.5s ease-in-out infinite; display: inline-block; }
        @keyframes heartBeat { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.2); } }
        .spinner-border-sm { width: 1.2rem; height: 1.2rem; border-width: 0.15em; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo">
            <div class="logo-icon"><i class="fas fa-robot"></i></div>
            <h3>WEB PNDK TOOL ĐA APP</h3>
            <p><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#28a745;animation:blink 1.5s ease-in-out infinite;margin-right:5px;"></span> Hệ thống tự động hóa</p>
        </div>
        
        <div id="loginForm">
            <h5><i class="fas fa-sign-in-alt"></i> Đăng nhập</h5>
            <form onsubmit="login(event)">
                <div class="mb-3">
                    <label class="form-label">Tên đăng nhập</label>
                    <input type="text" class="form-control" id="loginUsername" placeholder="Nhập tên đăng nhập" required>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label">Mật khẩu</label>
                    <input type="password" class="form-control" id="loginPassword" placeholder="Nhập mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('loginPassword', this)"><i class="fas fa-eye"></i></span>
                </div>
                <button type="submit" class="btn btn-login" id="loginBtn">
                    <i class="fas fa-sign-in-alt"></i> Đăng nhập
                </button>
            </form>
            <div id="loginStatus" class="mt-3"></div>
            <div class="switch-link">
                Chưa có tài khoản? <a href="#" onclick="showRegister()">Đăng ký ngay</a>
            </div>
        </div>
        
        <div id="registerForm" style="display:none;">
            <h5><i class="fas fa-user-plus"></i> Đăng ký</h5>
            <form onsubmit="register(event)">
                <div class="mb-3">
                    <label class="form-label">Tên đăng nhập</label>
                    <input type="text" class="form-control" id="registerUsername" placeholder="Chọn tên đăng nhập" required>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label">Mật khẩu</label>
                    <input type="password" class="form-control" id="registerPassword" placeholder="Nhập mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('registerPassword', this)"><i class="fas fa-eye"></i></span>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label">Xác nhận mật khẩu</label>
                    <input type="password" class="form-control" id="registerPassword2" placeholder="Nhập lại mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('registerPassword2', this)"><i class="fas fa-eye"></i></span>
                </div>
                <button type="submit" class="btn btn-login" id="registerBtn">
                    <i class="fas fa-user-plus"></i> Đăng ký
                </button>
            </form>
            <div id="registerStatus" class="mt-3"></div>
            <div class="switch-link">
                Đã có tài khoản? <a href="#" onclick="showLogin()">Đăng nhập</a>
            </div>
        </div>
        
        <div class="footer-text">
            <span class="heart">❤️</span> Phát triển bởi Phan Nguyễn Đăng Khoa
        </div>
    </div>

    <script>
        function togglePassword(inputId, eye) {
            const input = document.getElementById(inputId);
            if (input.type === 'password') {
                input.type = 'text';
                eye.innerHTML = '<i class="fas fa-eye-slash"></i>';
            } else {
                input.type = 'password';
                eye.innerHTML = '<i class="fas fa-eye"></i>';
            }
        }
        function showRegister() {
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('registerForm').style.display = 'block';
        }
        function showLogin() {
            document.getElementById('registerForm').style.display = 'none';
            document.getElementById('loginForm').style.display = 'block';
        }
        function login(e) {
            e.preventDefault();
            const username = document.getElementById('loginUsername').value.trim();
            const password = document.getElementById('loginPassword').value;
            const btn = document.getElementById('loginBtn');
            const status = document.getElementById('loginStatus');
            if (!username || !password) {
                status.innerHTML = '<div class="alert alert-danger">⚠️ Vui lòng nhập đầy đủ!</div>';
                return;
            }
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Đang đăng nhập...';
            btn.disabled = true;
            status.innerHTML = '';
            fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Đăng nhập';
                btn.disabled = false;
                if (data.success) {
                    status.innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    setTimeout(() => { window.location.href = '/'; }, 1000);
                } else {
                    status.innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Đăng nhập';
                btn.disabled = false;
                status.innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }
        function register(e) {
            e.preventDefault();
            const username = document.getElementById('registerUsername').value.trim();
            const password = document.getElementById('registerPassword').value;
            const password2 = document.getElementById('registerPassword2').value;
            const btn = document.getElementById('registerBtn');
            const status = document.getElementById('registerStatus');
            if (!username || !password || !password2) {
                status.innerHTML = '<div class="alert alert-danger">⚠️ Vui lòng nhập đầy đủ!</div>';
                return;
            }
            if (password !== password2) {
                status.innerHTML = '<div class="alert alert-danger">⚠️ Mật khẩu xác nhận không khớp!</div>';
                return;
            }
            if (password.length < 6) {
                status.innerHTML = '<div class="alert alert-danger">⚠️ Mật khẩu phải có ít nhất 6 ký tự!</div>';
                return;
            }
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Đang đăng ký...';
            btn.disabled = true;
            status.innerHTML = '';
            fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-user-plus"></i> Đăng ký';
                btn.disabled = false;
                if (data.success) {
                    status.innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    setTimeout(() => { showLogin(); }, 1500);
                } else {
                    status.innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-user-plus"></i> Đăng ký';
                btn.disabled = false;
                status.innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }
    </script>
</body>
</html>
"""

# ===== HTML TEMPLATE CHÍNH =====
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WEB PNDK TOOL ĐA APP</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
        :root { --primary: #667eea; --secondary: #764ba2; --danger: #dc3545; --success: #28a745; --warning: #ffc107; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            padding: 20px;
            font-family: 'Segoe UI', sans-serif;
            color: #fff;
            position: relative;
            overflow-x: hidden;
        }
        body::before {
            content: '';
            position: fixed;
            width: 200%;
            height: 200%;
            top: -50%;
            left: -50%;
            background: radial-gradient(ellipse at 30% 50%, rgba(102,126,234,0.08), transparent 60%),
                        radial-gradient(ellipse at 70% 50%, rgba(118,75,162,0.08), transparent 60%);
            animation: rotateBg 30s linear infinite;
            z-index: 0;
            pointer-events: none;
        }
        @keyframes rotateBg { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .container-custom { max-width: 1400px; margin: 0 auto; position: relative; z-index: 1; }
        .header-main {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 20px 30px;
            margin-bottom: 25px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideDown 0.6s ease-out;
        }
        @keyframes slideDown { 0% { transform: translateY(-30px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }
        .header-main .content { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px; }
        .logo-area { display: flex; align-items: center; gap: 18px; }
        .logo-icon {
            width: 55px; height: 55px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            color: #fff;
            box-shadow: 0 10px 30px rgba(102,126,234,0.3);
            animation: pulseLogo 2s ease-in-out infinite;
        }
        @keyframes pulseLogo { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        .brand-title {
            font-family: 'Orbitron', monospace;
            font-weight: 900;
            font-size: 22px;
            background: linear-gradient(135deg, #fff, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: none;
        }
        .brand-sub { font-size: 12px; color: rgba(255,255,255,0.4); letter-spacing: 2px; text-transform: uppercase; }
        .header-info { display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
        .info-badge {
            background: rgba(255,255,255,0.06);
            padding: 6px 16px;
            border-radius: 50px;
            font-size: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            display: flex;
            align-items: center;
            gap: 8px;
            color: rgba(255,255,255,0.6);
        }
        .info-badge i { color: var(--primary); }
        .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #28a745; animation: blink 1.5s ease-in-out infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .user-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .user-header .user-info { display: flex; align-items: center; gap: 12px; color: rgba(255,255,255,0.7); }
        .user-header .user-info i { font-size: 22px; color: var(--primary); }
        .user-header .user-info strong { color: #fff; }
        .btn-logout {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.6);
            padding: 6px 18px;
            border-radius: 8px;
            transition: all 0.3s;
            cursor: pointer;
            font-size: 13px;
        }
        .btn-logout:hover { background: rgba(220,53,69,0.2); border-color: rgba(220,53,69,0.3); color: #dc3545; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
            animation: fadeInUp 0.8s ease-out;
        }
        @keyframes fadeInUp { 0% { transform: translateY(20px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }
        .stat-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 15px 20px;
            text-align: center;
            transition: all 0.4s;
            cursor: default;
        }
        .stat-card:hover { transform: translateY(-5px) scale(1.02); background: rgba(255,255,255,0.08); box-shadow: 0 15px 40px rgba(0,0,0,0.2); }
        .stat-card .stat-icon { font-size: 22px; margin-bottom: 5px; display: block; }
        .stat-card .stat-number { font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #fff, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat-card .stat-label { font-size: 11px; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }
        .main-card {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 25px 60px rgba(0,0,0,0.3);
            animation: fadeInUp 1s ease-out;
        }
        .main-card .card-header-custom {
            background: rgba(255,255,255,0.04);
            padding: 12px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .main-card .card-header-custom .nav-link {
            color: rgba(255,255,255,0.5);
            border: none;
            padding: 6px 16px;
            font-weight: 600;
            border-radius: 10px;
            transition: all 0.3s;
            font-size: 13px;
        }
        .main-card .card-header-custom .nav-link:hover { color: #fff; background: rgba(255,255,255,0.05); }
        .main-card .card-header-custom .nav-link.active {
            color: #fff;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            box-shadow: 0 10px 30px rgba(102,126,234,0.25);
        }
        .main-card .card-body { padding: 20px; }
        .footer-main {
            margin-top: 25px;
            padding: 15px 30px;
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.04);
            text-align: center;
            color: rgba(255,255,255,0.3);
            font-size: 12px;
            animation: fadeInUp 1.2s ease-out;
        }
        .footer-main .heart { color: #ff4757; animation: heartBeat 1.5s ease-in-out infinite; display: inline-block; }
        @keyframes heartBeat { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.2); } }
        .footer-main a { color: rgba(255,255,255,0.4); text-decoration: none; transition: 0.3s; }
        .footer-main a:hover { color: #a78bfa; }
        .box-item {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 8px 14px;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: rgba(255,255,255,0.7);
        }
        .box-item:hover { background: rgba(255,255,255,0.08); border-color: var(--primary); transform: translateX(5px); }
        .box-item.selected { background: rgba(102,126,234,0.15); border-color: var(--primary); box-shadow: 0 0 20px rgba(102,126,234,0.1); }
        .box-item .box-check { color: var(--success); font-size: 16px; }
        .account-item {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 8px 14px;
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s;
            color: rgba(255,255,255,0.7);
        }
        .account-item:hover { background: rgba(255,255,255,0.06); }
        .account-item .account-name { font-weight: 600; color: #a78bfa; }
        .account-status { padding: 2px 10px; border-radius: 50px; font-size: 10px; font-weight: 600; }
        .account-status.active { background: rgba(40,167,69,0.2); color: #28a745; }
        .account-status.inactive { background: rgba(220,53,69,0.2); color: #dc3545; }
        .task-item {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 8px;
            transition: all 0.3s;
        }
        .task-item:hover { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.08); }
        .task-item .task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
        .task-progress { height: 4px; background: rgba(255,255,255,0.06); border-radius: 2px; overflow: hidden; margin-top: 6px; }
        .task-progress .progress-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--secondary)); transition: width 0.5s; }
        .task-status { padding: 2px 10px; border-radius: 50px; font-size: 10px; font-weight: 600; }
        .task-status.running { background: rgba(40,167,69,0.2); color: #28a745; }
        .task-status.done { background: rgba(102,126,234,0.2); color: #667eea; }
        .task-status.error { background: rgba(220,53,69,0.2); color: #dc3545; }
        .task-status.stopped { background: rgba(255,193,7,0.2); color: #ffc107; }
        .task-status.die { background: rgba(220,53,69,0.3); color: #ff6b6b; }
        .member-item {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 8px;
            padding: 5px 10px;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: rgba(255,255,255,0.6);
            font-size: 13px;
        }
        .member-item:hover { background: rgba(255,255,255,0.08); }
        .member-item.selected { background: rgba(102,126,234,0.12); border-color: var(--primary); }
        .btn-primary-custom {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border: none;
            color: #fff;
            padding: 8px 18px;
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(102,126,234,0.2);
        }
        .btn-primary-custom:hover { transform: translateY(-2px); box-shadow: 0 15px 40px rgba(102,126,234,0.3); color: #fff; }
        .btn-success-custom {
            background: linear-gradient(135deg, #28a745, #20c997);
            border: none;
            color: #fff;
            padding: 8px 18px;
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-success-custom:hover { transform: translateY(-2px); box-shadow: 0 15px 40px rgba(40,167,69,0.25); color: #fff; }
        .btn-danger-custom {
            background: linear-gradient(135deg, #dc3545, #c82333);
            border: none;
            color: #fff;
            padding: 8px 18px;
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-danger-custom:hover { transform: translateY(-2px); box-shadow: 0 15px 40px rgba(220,53,69,0.25); color: #fff; }
        .btn-warning-custom {
            background: linear-gradient(135deg, #ffc107, #f7b503);
            border: none;
            color: #333;
            padding: 8px 18px;
            border-radius: 10px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-warning-custom:hover { transform: translateY(-2px); box-shadow: 0 15px 40px rgba(255,193,7,0.25); color: #333; }
        .form-control {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.06);
            color: #fff;
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 13px;
        }
        .form-control:focus { background: rgba(255,255,255,0.08); border-color: var(--primary); color: #fff; box-shadow: 0 0 0 3px rgba(102,126,234,0.15); }
        .form-control::placeholder { color: rgba(255,255,255,0.2); }
        .form-label { color: rgba(255,255,255,0.5); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
        .form-check-label { color: rgba(255,255,255,0.5); font-size: 13px; }
        .form-check-input { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); }
        .form-check-input:checked { background-color: var(--primary); border-color: var(--primary); }
        .alert { border-radius: 10px; border: none; background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); font-size: 13px; padding: 10px 14px; }
        .alert-info { background: rgba(102,126,234,0.1); color: #a78bfa; border: 1px solid rgba(102,126,234,0.1); }
        .alert-success { background: rgba(40,167,69,0.1); color: #28a745; border: 1px solid rgba(40,167,69,0.1); }
        .alert-danger { background: rgba(220,53,69,0.1); color: #dc3545; border: 1px solid rgba(220,53,69,0.1); }
        .list-container::-webkit-scrollbar { width: 4px; }
        .list-container::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); border-radius: 2px; }
        .list-container::-webkit-scrollbar-thumb { background: var(--primary); border-radius: 2px; }
        .list-container { max-height: 350px; overflow-y: auto; padding-right: 5px; }
        .member-list { max-height: 250px; overflow-y: auto; }
        .empty-state { text-align: center; padding: 25px 20px; color: rgba(255,255,255,0.2); }
        .empty-state i { font-size: 35px; display: block; margin-bottom: 8px; }
        .empty-state p { font-size: 13px; margin: 0; }
        .empty-state small { color: rgba(255,255,255,0.15); font-size: 11px; }
        .file-upload-area {
            border: 2px dashed rgba(255,255,255,0.08);
            padding: 12px;
            text-align: center;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
            color: rgba(255,255,255,0.3);
            font-size: 13px;
        }
        .file-upload-area:hover { border-color: var(--primary); background: rgba(255,255,255,0.03); }
        .color-picker { width: 45px; height: 32px; padding: 2px; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; cursor: pointer; background: transparent; }
        .spinner-small { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.1); border-top: 2px solid #fff; border-radius: 50%; animation: spin 1s linear infinite; display: inline-block; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @media (max-width: 768px) {
            .brand-title { font-size: 16px; }
            .header-info { gap: 8px; }
            .info-badge { font-size: 10px; padding: 4px 12px; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .logo-icon { width: 40px; height: 40px; font-size: 20px; }
            .main-card .card-body { padding: 12px; }
            .user-header { flex-wrap: wrap; gap: 10px; }
        }
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr; }
            .header-main .content { flex-direction: column; text-align: center; }
            .logo-area { flex-direction: column; }
        }
        .card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; }
        .card-header { background: transparent; border: none; color: #fff; padding: 12px 16px; font-weight: 600; font-size: 13px; }
        .card-body { padding: 12px 16px; }
        .badge-float { float: right; font-size: 10px; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); }
        .col-md-3, .col-md-4, .col-md-5, .col-md-6, .col-md-7, .col-md-8 { padding: 0 8px; }
        .row { margin: 0 -8px; }
        .mb-3 { margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container-custom">
        <!-- HEADER -->
        <div class="header-main">
            <div class="content">
                <div class="logo-area">
                    <div class="logo-icon"><i class="fas fa-robot"></i></div>
                    <div>
                        <div class="brand-title">WEB PNDK TOOL ĐA APP</div>
                        <div class="brand-sub"><span class="status-dot"></span> Hệ thống tự động hóa</div>
                    </div>
                </div>
                <div class="header-info">
                    <div class="info-badge"><i class="fas fa-user"></i><span>Phan Nguyễn Đăng Khoa</span></div>
                    <div class="info-badge"><i class="fas fa-code"></i><span>v3.0</span></div>
                    <div class="info-badge"><i class="fas fa-clock"></i><span id="liveTime">Đang tải...</span></div>
                </div>
            </div>
        </div>

        <!-- USER HEADER -->
        <div class="user-header">
            <div class="user-info">
                <i class="fas fa-user-circle"></i>
                <span><strong id="userDisplay">{{ username }}</strong></span>
                <span class="badge bg-success" style="font-size: 9px;"><i class="fas fa-check-circle"></i> Đã đăng nhập</span>
            </div>
            <div>
                <button class="btn-logout" onclick="logout()">
                    <i class="fas fa-sign-out-alt"></i> Đăng xuất
                </button>
            </div>
        </div>

        <!-- STATS -->
        <div class="stats-grid">
            <div class="stat-card"><span class="stat-icon"><i class="fas fa-users"></i></span><div class="stat-number" id="accCount">0</div><div class="stat-label">Tài khoản Zalo</div></div>
            <div class="stat-card"><span class="stat-icon"><i class="fas fa-check-circle"></i></span><div class="stat-number" id="activeCount">0</div><div class="stat-label">Đang hoạt động</div></div>
            <div class="stat-card"><span class="stat-icon"><i class="fas fa-tasks"></i></span><div class="stat-number" id="taskCount">0</div><div class="stat-label">Tổng Tasks</div></div>
            <div class="stat-card"><span class="stat-icon"><i class="fas fa-play-circle"></i></span><div class="stat-number" id="runningCount">0</div><div class="stat-label">Đang chạy</div></div>
        </div>

        <!-- MAIN CARD -->
        <div class="main-card">
            <div class="card-header-custom">
                <ul class="nav nav-tabs" id="myTab" role="tablist" style="border: none; gap: 2px;">
                    <li class="nav-item"><button class="nav-link active" id="accounts-tab" data-bs-toggle="tab" data-bs-target="#accounts" type="button" role="tab"><i class="fas fa-users"></i> Tài khoản</button></li>
                    <li class="nav-item"><button class="nav-link" id="treongon-tab" data-bs-toggle="tab" data-bs-target="#treongon" type="button" role="tab"><i class="fas fa-paper-plane"></i> Treo Ngôn</button></li>
                    <li class="nav-item"><button class="nav-link" id="nhaytag-tab" data-bs-toggle="tab" data-bs-target="#nhaytag" type="button" role="tab"><i class="fas fa-tags"></i> Nhây Tag</button></li>
                    <li class="nav-item"><button class="nav-link" id="messenger-tab" data-bs-toggle="tab" data-bs-target="#messenger" type="button" role="tab"><i class="fab fa-facebook-messenger"></i> Messenger</button></li>
                    <li class="nav-item"><button class="nav-link" id="zalospam-tab" data-bs-toggle="tab" data-bs-target="#zalospam" type="button" role="tab"><i class="fas fa-comment-dots"></i> Zalo Spam</button></li>
                    <li class="nav-item"><button class="nav-link" id="tasks-tab" data-bs-toggle="tab" data-bs-target="#tasks" type="button" role="tab"><i class="fas fa-tasks"></i> Task <span class="badge bg-danger" id="taskBadge" style="font-size: 9px;">0</span></button></li>
                </ul>
            </div>
            
            <div class="card-body">
                <div class="tab-content">
                    <!-- ACCOUNTS TAB -->
                    <div class="tab-pane fade show active" id="accounts" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-plus-circle"></i> Thêm tài khoản Zalo</div>
                                    <div class="card-body">
                                        <div class="alert alert-info"><i class="fas fa-info-circle"></i> <strong>Định dạng cookies:</strong> {"name":"value","name2":"value2"}</div>
                                        <form id="addAccountForm" onsubmit="addAccount(event)">
                                            <div class="mb-3"><label class="form-label">Tên tài khoản <span class="text-danger">*</span></label><input type="text" class="form-control" id="accName" placeholder="VD: Zalo_01" required></div>
                                            <div class="mb-3"><label class="form-label">Cookies <span class="text-danger">*</span></label><textarea class="form-control" id="accCookies" rows="3" placeholder='{"zpsid":"xxx","zpw_sek":"xxx"}' required></textarea></div>
                                            <div class="mb-3"><label class="form-label">IMEI <span class="text-danger">*</span></label><input type="text" class="form-control" id="accImei" placeholder="Nhập IMEI..." required></div>
                                            <div class="mb-3"><label class="form-label">Ghi chú</label><input type="text" class="form-control" id="accNote" placeholder="Ghi chú thêm..."></div>
                                            <button type="submit" class="btn btn-success-custom w-100"><i class="fas fa-save"></i> Lưu tài khoản</button>
                                        </form>
                                        <div id="addAccountStatus" class="mt-2"></div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-7">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-list"></i> Danh sách tài khoản Zalo <span class="badge bg-light text-dark badge-float" id="accountListCount">0</span></div>
                                    <div class="card-body">
                                        <div class="list-container" id="accountList">
                                            <div class="empty-state"><i class="fas fa-users"></i><p>Chưa có tài khoản Zalo nào</p><small>Thêm tài khoản Zalo để bắt đầu</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TREO NGÔN TAB -->
                    <div class="tab-pane fade" id="treongon" role="tabpanel">
                        <div class="row">
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-comments"></i> Box chat</div>
                                    <div class="card-body">
                                        <button class="btn btn-primary-custom w-100 mb-3" onclick="refreshBoxes('treongon')"><i class="fas fa-sync"></i> Làm mới box chat</button>
                                        <div id="boxListContainer_treongon" class="list-container">
                                            <div class="empty-state"><i class="fas fa-inbox"></i><p>Chưa có box chat</p><small>Chọn tài khoản Zalo và làm mới</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-8">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-paper-plane"></i> Treo Ngôn <span class="badge bg-light text-dark badge-float" id="sessionStatus_treongon">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-user"></i> Tài khoản đang dùng</label><input type="text" class="form-control" id="currentAccountDisplay_treongon" readonly value="Chưa chọn"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-comment"></i> Box đã chọn</label><input type="text" class="form-control" id="selectedBox_treongon" readonly placeholder="Chọn box"></div></div>
                                        </div>
                                        <div class="row mb-3">
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="tagAllCheck" checked><label class="form-check-label" for="tagAllCheck">Tag All</label></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-pencil-alt"></i> Chữ tag</label><input type="text" class="form-control" id="tagText" value="@All" style="font-size:13px;"></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-palette"></i> Màu tag</label><div class="d-flex align-items-center"><input type="color" class="color-picker me-2" id="tagColorPicker" value="#db342e"><input type="text" class="form-control" id="tagColorInput" value="#db342e" style="width:70px;font-size:12px;"></div></div></div>
                                        </div>
                                        <div class="row mb-3">
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="colorCheck" checked><label class="form-check-label" for="colorCheck">Màu nội dung</label></div></div>
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="boldCheck" checked><label class="form-check-label" for="boldCheck">In đậm</label></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-palette"></i> Màu nội dung</label><div class="d-flex align-items-center"><input type="color" class="color-picker me-2" id="colorPicker" value="#db342e"><input type="text" class="form-control" id="colorInput" value="#db342e" style="width:70px;font-size:12px;"></div></div></div>
                                        </div>
                                        <div class="row">
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label><input type="number" class="form-control" id="delayInput_treongon" value="2" min="0.5" step="0.5"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-redo"></i> Số lần gửi</label><input type="number" class="form-control" id="totalInput_treongon" value="1" min="1"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-font"></i> Size chữ</label><input type="number" class="form-control" id="fontSizeInput" value="15" min="8" max="30"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-layer-group"></i> Màu mỗi dòng</label><div class="form-check"><input class="form-check-input" type="checkbox" id="multiColorCheck"><label class="form-check-label" for="multiColorCheck">Nhiều màu</label></div></div></div>
                                        </div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-file-alt"></i> Nội dung</label><textarea class="form-control" id="contentInput_treongon" rows="3" placeholder="pndkdzcute&#10;pndkdzcute&#10;22:22"></textarea></div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-upload"></i> Hoặc tải file .txt</label><div class="file-upload-area" onclick="document.getElementById('fileInput_treongon').click()"><i class="fas fa-cloud-upload-alt fa-2x"></i><p style="margin:3px 0 0 0;font-size:13px;">Nhấn để chọn file .txt</p><input type="file" id="fileInput_treongon" accept=".txt" style="display:none;" onchange="loadFileContent(event, 'contentInput_treongon', 'fileName_treongon', 'fileText_treongon')"></div>
                                        <div id="fileName_treongon" class="mt-2 text-success" style="display:none;font-size:13px;">📎 Đã chọn: <span id="fileText_treongon"></span></div></div>
                                        <button class="btn btn-primary-custom w-100" onclick="startTreongon()" id="treongonBtn"><i class="fas fa-play"></i> Bắt đầu treo</button>
                                        <div id="treongonStatus" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- NHAY TAG TAB -->
                    <div class="tab-pane fade" id="nhaytag" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-comments"></i> Box chat</div>
                                    <div class="card-body">
                                        <button class="btn btn-primary-custom w-100 mb-3" onclick="refreshBoxes('nhaytag')"><i class="fas fa-sync"></i> Làm mới box chat</button>
                                        <div id="boxListContainer_nhaytag" class="list-container">
                                            <div class="empty-state"><i class="fas fa-inbox"></i><p>Chưa có box chat</p><small>Chọn tài khoản Zalo và làm mới</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-7">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-tags"></i> Nhây Tag <span class="badge bg-light text-dark badge-float" id="sessionStatus_nhaytag">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-user"></i> Tài khoản đang dùng</label><input type="text" class="form-control" id="currentAccountDisplay_nhaytag" readonly value="Chưa chọn"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-comment"></i> Box đã chọn</label><input type="text" class="form-control" id="selectedBox_nhaytag" readonly placeholder="Chọn box"></div></div>
                                        </div>
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label><input type="number" class="form-control" id="delayInput_nhaytag" value="5" min="1" step="0.5"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-file-alt"></i> File nội dung</label><div class="file-upload-area" onclick="document.getElementById('fileInput_nhaytag').click()" style="padding:8px;"><i class="fas fa-cloud-upload-alt"></i><span style="font-size:13px;">Nhấn để chọn file .txt</span><input type="file" id="fileInput_nhaytag" accept=".txt" style="display:none;" onchange="loadNhayFile(event)"></div>
                                            <div id="fileName_nhaytag" class="mt-2 text-success" style="display:none;font-size:13px;">📎 Đã chọn: <span id="fileText_nhaytag"></span></div>
                                            <div id="nhayFilePreview" class="mt-2"></div>
                                            <input type="hidden" id="nhayFileContent" value="">
                                            <small style="color:rgba(255,255,255,0.3);font-size:11px;">Mỗi dòng là 1 đoạn nội dung sẽ được gửi</small></div></div>
                                        </div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-users"></i> Thành viên (chọn người tag)</label>
                                            <button class="btn btn-sm btn-primary-custom mb-2" onclick="fetchMembers('nhaytag')" style="font-size:12px;padding:4px 12px;"><i class="fas fa-sync"></i> Lấy danh sách thành viên</button>
                                            <div id="memberListContainer_nhaytag" class="member-list"><div class="empty-state"><i class="fas fa-users"></i><p>Chưa có thành viên</p><small>Nhấn nút trên để lấy</small></div></div>
                                            <div class="mt-2">
                                                <button class="btn btn-sm btn-outline-success" onclick="selectAllMembers('nhaytag')" style="border-color:rgba(40,167,69,0.3);color:#28a745;font-size:12px;">Chọn tất cả</button>
                                                <button class="btn btn-sm btn-outline-secondary" onclick="deselectAllMembers('nhaytag')" style="border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.4);font-size:12px;">Bỏ chọn</button>
                                                <span class="ms-2" id="memberCount_nhaytag" style="color:rgba(255,255,255,0.4);font-size:13px;">Đã chọn: 0</span>
                                            </div>
                                        </div>
                                        <button class="btn btn-warning-custom w-100" onclick="startNhaytag()" id="nhaytagBtn"><i class="fas fa-play"></i> Bắt đầu nhây tag</button>
                                        <div id="nhaytagStatus" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- MESSENGER TAB -->
                    <div class="tab-pane fade" id="messenger" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card">
                                    <div class="card-header"><i class="fab fa-facebook-messenger"></i> Cookie & Box ID</div>
                                    <div class="card-body">
                                        <div class="mb-3">
                                            <label class="form-label"><i class="fas fa-cookie-bite"></i> Cookie Facebook</label>
                                            <textarea class="form-control" id="messengerCookie" rows="3" placeholder="c_user=...; xs=...; ..." style="font-size:12px;"></textarea>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label"><i class="fas fa-id-card"></i> ID Box (cách nhau bằng dấu phẩy)</label>
                                            <input type="text" class="form-control" id="messengerBoxIds" placeholder="VD: 123456789, 987654321, 111111111">
                                            <small style="color:rgba(255,255,255,0.3);font-size:11px;">Nhập ID box chat Facebook (mỗi ID cách nhau dấu phẩy)</small>
                                        </div>
                                        <div class="alert alert-info" style="font-size:12px;">
                                            <i class="fas fa-info-circle"></i> 
                                            <strong>Cách lấy ID box:</strong> Vào Facebook → click vào tin nhắn → xem URL: facebook.com/messages/t/<strong>123456789</strong>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-7">
                                <div class="card">
                                    <div class="card-header"><i class="fab fa-facebook-messenger"></i> Treo Messenger <span class="badge bg-light text-dark badge-float" id="messengerStatus">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label>
                                                    <input type="number" class="form-control" id="messengerDelay" value="2" min="0.5" step="0.5">
                                                </div>
                                            </div>
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label"><i class="fas fa-file-alt"></i> File nội dung</label>
                                                    <div class="file-upload-area" onclick="document.getElementById('messengerFileInput').click()" style="padding:8px;">
                                                        <i class="fas fa-cloud-upload-alt"></i>
                                                        <span style="font-size:13px;">Chọn file .txt</span>
                                                        <input type="file" id="messengerFileInput" accept=".txt" style="display:none;" onchange="loadMessengerFile(event)">
                                                    </div>
                                                    <div id="messengerFileName" class="mt-2 text-success" style="display:none;font-size:13px;">
                                                        📎 Đã chọn: <span id="messengerFileText"></span>
                                                    </div>
                                                    <input type="hidden" id="messengerFileContent" value="">
                                                </div>
                                            </div>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label"><i class="fas fa-comment"></i> Nội dung (nếu không có file)</label>
                                            <textarea class="form-control" id="messengerContent" rows="3" placeholder="Nội dung tin nhắn..."></textarea>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label"><i class="fas fa-list"></i> Box ID đã nhập</label>
                                            <input type="text" class="form-control" id="selectedMessengerBoxes" readonly placeholder="Nhập ID box ở bên trái">
                                        </div>
                                        <button class="btn btn-primary-custom w-100" onclick="startMessengerSpam()" id="messengerBtn">
                                            <i class="fas fa-play"></i> Bắt đầu treo Messenger
                                        </button>
                                        <div id="messengerStatusMsg" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="row mt-3">
                            <div class="col-12">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-tasks"></i> Task Messenger <span class="badge bg-light text-dark badge-float" id="messengerTaskCount">0</span></div>
                                    <div class="card-body">
                                        <div id="messengerTaskList" class="list-container" style="max-height:200px;">
                                            <div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task Messenger nào</p></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- ZALO SPAM TAB -->
                    <div class="tab-pane fade" id="zalospam" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-comment-dots"></i> Cookie & Nhóm</div>
                                    <div class="card-body">
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-mobile-alt"></i> IMEI</label><input type="text" class="form-control" id="zaloSpamImei" placeholder="Nhập IMEI Zalo..."></div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-cookie-bite"></i> Cookie Zalo</label><textarea class="form-control" id="zaloSpamCookie" rows="3" placeholder='{"zpsid":"xxx","zpw_sek":"xxx"}' style="font-size:12px;"></textarea></div>
                                        <button class="btn btn-primary-custom w-100 mb-3" onclick="getZaloGroups()"><i class="fas fa-sync"></i> Lấy danh sách nhóm</button>
                                        <div id="zaloGroupList" class="list-container">
                                            <div class="empty-state"><i class="fas fa-users"></i><p>Chưa có nhóm</p><small>Nhập IMEI/Cookie và nhấn lấy danh sách</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-7">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-comment-dots"></i> Spam Zalo <span class="badge bg-light text-dark badge-float" id="zaloSpamStatus">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label><input type="number" class="form-control" id="zaloSpamDelay" value="2" min="0.5" step="0.5"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-file-alt"></i> File nội dung</label>
                                                <div class="file-upload-area" onclick="document.getElementById('zaloSpamFileInput').click()" style="padding:8px;"><i class="fas fa-cloud-upload-alt"></i><span style="font-size:13px;">Chọn file .txt</span><input type="file" id="zaloSpamFileInput" accept=".txt" style="display:none;" onchange="loadZaloSpamFile(event)"></div>
                                                <div id="zaloSpamFileName" class="mt-2 text-success" style="display:none;font-size:13px;">📎 Đã chọn: <span id="zaloSpamFileText"></span></div>
                                                <input type="hidden" id="zaloSpamFileContent" value="">
                                            </div></div>
                                        </div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-comment"></i> Nội dung (nếu không có file)</label><textarea class="form-control" id="zaloSpamContent" rows="3" placeholder="Nội dung tin nhắn..."></textarea></div>
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-list"></i> Nhóm đã chọn</label><input type="text" class="form-control" id="selectedZaloGroups" readonly placeholder="Chọn nhóm ở bên trái"></div>
                                        <button class="btn btn-primary-custom w-100" onclick="startZaloSpam()" id="zaloSpamBtn"><i class="fas fa-play"></i> Bắt đầu spam Zalo</button>
                                        <div id="zaloSpamStatusMsg" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="row mt-3">
                            <div class="col-12">
                                <div class="card">
                                    <div class="card-header"><i class="fas fa-tasks"></i> Task Zalo Spam <span class="badge bg-light text-dark badge-float" id="zaloSpamTaskCount">0</span></div>
                                    <div class="card-body">
                                        <div id="zaloSpamTaskList" class="list-container" style="max-height:200px;">
                                            <div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task Zalo Spam nào</p></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TASKS TAB -->
                    <div class="tab-pane fade" id="tasks" role="tabpanel">
                        <div class="card">
                            <div class="card-header"><i class="fas fa-tasks"></i> Quản Lý Task <span class="badge bg-light text-dark badge-float" id="taskListCount">0</span></div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <button class="btn btn-sm btn-outline-secondary" onclick="refreshTasks()" style="border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.5);font-size:12px;"><i class="fas fa-sync"></i> Làm mới</button>
                                    <button class="btn btn-sm btn-outline-danger" onclick="stopAllTasks()" style="border-color:rgba(255,193,7,0.2);color:#ffc107;font-size:12px;"><i class="fas fa-stop"></i> Dừng tất cả</button>
                                    <button class="btn btn-sm btn-outline-danger" onclick="clearFinishedTasks()" style="border-color:rgba(220,53,69,0.2);color:#dc3545;font-size:12px;"><i class="fas fa-trash"></i> Xóa task hoàn thành</button>
                                </div>
                                <div class="list-container" id="taskList" style="max-height:500px;">
                                    <div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task nào</p><small>Bắt đầu treo ngôn, nhây tag, messenger hoặc spam zalo</small></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer-main">
            <p style="margin:0;"><i class="fas fa-crown" style="color:#f7b503;"></i> <strong style="color:rgba(255,255,255,0.4);">WEB PNDK TOOL ĐA APP</strong> <span class="heart">❤️</span> Phát triển bởi <a href="#">Phan Nguyễn Đăng Khoa</a> <span style="margin:0 8px;">|</span> <i class="fas fa-code"></i> v3.0 <span style="margin:0 8px;">|</span> <i class="fas fa-shield-alt"></i> Bảo mật & An toàn</p>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // ===== LIVE TIME =====
        function updateTime() {
            const now = new Date();
            document.getElementById('liveTime').textContent = now.toLocaleTimeString('vi-VN');
        }
        setInterval(updateTime, 1000);
        updateTime();

        // ===== LOGOUT =====
        function logout() {
            if (!confirm('Bạn có chắc muốn đăng xuất?')) return;
            fetch('/api/logout', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) window.location.href = '/login';
            });
        }

        // ===== VARIABLES =====
        let selectedBox_treongon = '';
        let selectedBoxId_treongon = '';
        let selectedBox_nhaytag = '';
        let selectedBoxId_nhaytag = '';
        let members_nhaytag = [];
        let selectedMembers_nhaytag = [];
        let selectedMessengerBoxes = [];
        let selectedZaloGroups = [];

        // ===== SYNC COLOR =====
        document.getElementById('colorPicker').addEventListener('input', function() {
            document.getElementById('colorInput').value = this.value;
        });
        document.getElementById('colorInput').addEventListener('input', function() {
            document.getElementById('colorPicker').value = this.value;
        });
        document.getElementById('tagColorPicker').addEventListener('input', function() {
            document.getElementById('tagColorInput').value = this.value;
        });
        document.getElementById('tagColorInput').addEventListener('input', function() {
            document.getElementById('tagColorPicker').value = this.value;
        });

        // ===== LOAD FILE =====
        function loadFileContent(event, targetId, nameId, textId) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                document.getElementById(targetId).value = e.target.result;
                document.getElementById(nameId).style.display = 'block';
                document.getElementById(textId).textContent = file.name;
            };
            reader.readAsText(file);
        }

        // ===== LOAD NHAY FILE =====
        function loadNhayFile(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                const content = e.target.result;
                document.getElementById('nhayFileContent').value = content;
                document.getElementById('fileName_nhaytag').style.display = 'block';
                document.getElementById('fileText_nhaytag').textContent = file.name;
                const lines = content.split('\\n').filter(l => l.trim());
                const preview = lines.slice(0, 10).map(l => l.trim()).join('\\n');
                document.getElementById('nhayFilePreview').innerHTML = 
                    `<div style="background:rgba(255,255,255,0.03);border-radius:8px;padding:6px 10px;margin-top:6px;border:1px solid rgba(255,255,255,0.05);">
                        <small style="color:rgba(255,255,255,0.4);"><strong>📄 ${lines.length} dòng</strong></small>
                        <pre style="max-height:80px;overflow-y:auto;font-size:12px;margin:4px 0 0 0;background:rgba(0,0,0,0.2);padding:6px;border-radius:4px;color:rgba(255,255,255,0.5);">${preview}${lines.length > 10 ? '\\n...' : ''}</pre>
                    </div>`;
            };
            reader.readAsText(file);
        }

        // ===== LOAD MESSENGER FILE =====
        function loadMessengerFile(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                document.getElementById('messengerFileContent').value = e.target.result;
                document.getElementById('messengerFileName').style.display = 'block';
                document.getElementById('messengerFileText').textContent = file.name;
            };
            reader.readAsText(file);
        }

        // ===== LOAD ZALO SPAM FILE =====
        function loadZaloSpamFile(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                document.getElementById('zaloSpamFileContent').value = e.target.result;
                document.getElementById('zaloSpamFileName').style.display = 'block';
                document.getElementById('zaloSpamFileText').textContent = file.name;
            };
            reader.readAsText(file);
        }

        // ===== ACCOUNT =====
        function addAccount(e) {
            e.preventDefault();
            const name = document.getElementById('accName').value.trim();
            const cookies = document.getElementById('accCookies').value.trim();
            const imei = document.getElementById('accImei').value.trim();
            const note = document.getElementById('accNote').value.trim();
            if (!name || !cookies || !imei) {
                document.getElementById('addAccountStatus').innerHTML = '<div class="alert alert-danger">⚠️ Vui lòng nhập đầy đủ!</div>';
                return;
            }
            document.getElementById('addAccountStatus').innerHTML = '<div class="text-center"><div class="spinner-small"></div> Đang lưu...</div>';
            fetch('/add_account', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, cookies, imei, note })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('addAccountStatus').innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    setTimeout(() => location.reload(), 1000);
                } else {
                    document.getElementById('addAccountStatus').innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                document.getElementById('addAccountStatus').innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }

        function useAccount(accountId) {
            document.getElementById('accountList').innerHTML = '<div class="text-center"><div class="spinner-small"></div> Đang đăng nhập...</div>';
            fetch('/use_account/' + accountId, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) location.reload();
                else { alert('❌ ' + data.message); location.reload(); }
            });
        }

        function deleteAccount(accountId) {
            if (!confirm('Xóa tài khoản Zalo này?')) return;
            fetch('/delete_account/' + accountId, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                if (data.success) location.reload();
                else alert('❌ ' + data.message);
            });
        }

        // ===== BOX =====
        function refreshBoxes(mode) {
            const containerId = mode === 'treongon' ? 'boxListContainer_treongon' : 'boxListContainer_nhaytag';
            const container = document.getElementById(containerId);
            container.innerHTML = '<div class="text-center"><div class="spinner-small"></div> Đang lấy box...</div>';
            fetch('/get_boxes')
            .then(res => res.json())
            .then(data => {
                if (data.success && data.boxes && data.boxes.length > 0) {
                    let html = '';
                    data.boxes.forEach((box, index) => {
                        const boxId = 'box_' + mode + '_' + index;
                        const name = box.name.replace(/'/g, "\\'");
                        html += `<div class="box-item" onclick="selectBox('${mode}', '${name}', '${box.id}', '${boxId}')" id="${boxId}">
                            <div><i class="fas fa-comment"></i> ${box.name}</div>
                            <div class="box-check"></div>
                        </div>`;
                    });
                    container.innerHTML = html;
                } else {
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-inbox"></i><p>${data.message || 'Không tìm thấy box chat'}</p></div>`;
                }
            })
            .catch(err => {
                container.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Lỗi: ${err}</p></div>`;
            });
        }

        function selectBox(mode, name, id, boxId) {
            if (mode === 'treongon') {
                selectedBox_treongon = name;
                selectedBoxId_treongon = id;
                document.getElementById('selectedBox_treongon').value = name;
                document.querySelectorAll('#boxListContainer_treongon .box-item').forEach(el => {
                    el.classList.remove('selected');
                    el.querySelector('.box-check').textContent = '';
                });
            } else {
                selectedBox_nhaytag = name;
                selectedBoxId_nhaytag = id;
                document.getElementById('selectedBox_nhaytag').value = name;
                document.querySelectorAll('#boxListContainer_nhaytag .box-item').forEach(el => {
                    el.classList.remove('selected');
                    el.querySelector('.box-check').textContent = '';
                });
            }
            const el = document.getElementById(boxId);
            if (el) {
                el.classList.add('selected');
                el.querySelector('.box-check').textContent = '✅';
            }
        }

        // ===== FETCH MEMBERS =====
        function fetchMembers(mode) {
            if (mode !== 'nhaytag') return;
            if (!selectedBoxId_nhaytag) {
                alert('⚠️ Chọn box chat trước!');
                return;
            }
            const container = document.getElementById('memberListContainer_nhaytag');
            container.innerHTML = '<div class="text-center"><div class="spinner-small"></div> Đang lấy thành viên...</div>';
            fetch('/get_members/' + selectedBoxId_nhaytag)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.members && data.members.length > 0) {
                    members_nhaytag = data.members;
                    selectedMembers_nhaytag = [];
                    renderMembers('nhaytag');
                } else {
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-users"></i><p>${data.message || 'Không lấy được thành viên'}</p></div>`;
                }
            })
            .catch(err => {
                container.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Lỗi: ${err}</p></div>`;
            });
        }

        function renderMembers(mode) {
            const container = document.getElementById('memberListContainer_nhaytag');
            if (members_nhaytag.length === 0) {
                container.innerHTML = '<div class="empty-state"><i class="fas fa-users"></i><p>Chưa có thành viên</p></div>';
                return;
            }
            let html = '';
            members_nhaytag.forEach((member, index) => {
                const isSelected = selectedMembers_nhaytag.includes(member.id);
                html += `<div class="member-item ${isSelected ? 'selected' : ''}" onclick="toggleMember('${member.id}')">
                    <span>${index + 1}. ${member.name}</span>
                    <span>${isSelected ? '✅' : '⬜'}</span>
                </div>`;
            });
            container.innerHTML = html;
            document.getElementById('memberCount_nhaytag').textContent = 'Đã chọn: ' + selectedMembers_nhaytag.length;
        }

        function toggleMember(memberId) {
            const idx = selectedMembers_nhaytag.indexOf(memberId);
            if (idx === -1) selectedMembers_nhaytag.push(memberId);
            else selectedMembers_nhaytag.splice(idx, 1);
            renderMembers('nhaytag');
        }

        function selectAllMembers(mode) {
            selectedMembers_nhaytag = members_nhaytag.map(m => m.id);
            renderMembers('nhaytag');
        }

        function deselectAllMembers(mode) {
            selectedMembers_nhaytag = [];
            renderMembers('nhaytag');
        }

        // ===== MESSENGER =====
        function updateMessengerBoxes() {
            const boxIds = document.getElementById('messengerBoxIds').value.trim();
            document.getElementById('selectedMessengerBoxes').value = boxIds || 'Chưa nhập ID box';
        }

        // Gắn sự kiện khi nhập ID box
        document.getElementById('messengerBoxIds').addEventListener('input', updateMessengerBoxes);

        function startMessengerSpam() {
            const cookie = document.getElementById('messengerCookie').value.trim();
            const boxIdsInput = document.getElementById('messengerBoxIds').value.trim();
            const delay = parseFloat(document.getElementById('messengerDelay').value) || 2;
            const content = document.getElementById('messengerContent').value.trim();
            const fileContent = document.getElementById('messengerFileContent').value;
            
            if (!cookie) {
                alert('⚠️ Nhập cookie Facebook!');
                return;
            }
            
            const boxIds = boxIdsInput.split(',').map(id => id.trim()).filter(id => id);
            if (boxIds.length === 0) {
                alert('⚠️ Nhập ít nhất 1 ID box! (cách nhau bằng dấu phẩy)');
                return;
            }
            
            const finalContent = fileContent || content;
            if (!finalContent) {
                alert('⚠️ Nhập nội dung hoặc upload file!');
                return;
            }
            
            const btn = document.getElementById('messengerBtn');
            btn.innerHTML = '<span class="spinner-small"></span> Đang khởi động...';
            btn.disabled = true;
            document.getElementById('messengerStatusMsg').innerHTML = '';
            
            fetch('/start_messenger_spam', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cookie: cookie,
                    box_ids: boxIds,
                    content: finalContent,
                    delay: delay,
                    filename: ''
                })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu treo Messenger';
                btn.disabled = false;
                if (data.success) {
                    document.getElementById('messengerStatusMsg').innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    refreshMessengerTasks();
                } else {
                    document.getElementById('messengerStatusMsg').innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu treo Messenger';
                btn.disabled = false;
                document.getElementById('messengerStatusMsg').innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }

        function stopMessengerTask(taskId) {
            if (!confirm('Dừng task Messenger #' + taskId + '?')) return;
            fetch('/stop_messenger_spam/' + taskId, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshMessengerTasks();
                    alert('✅ ' + data.message);
                } else {
                    alert('❌ ' + data.message);
                }
            });
        }

        function refreshMessengerTasks() {
            fetch('/get_messenger_tasks')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('messengerTaskList');
                const count = document.getElementById('messengerTaskCount');
                const tasks = data.tasks || [];
                count.textContent = tasks.length;
                if (tasks.length === 0) {
                    container.innerHTML = '<div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task Messenger nào</p></div>';
                    return;
                }
                let html = '';
                tasks.forEach(task => {
                    const statusClass = task.status;
                    const statusLabel = {
                        'running': '🟢 Đang chạy',
                        'stopped': '⏹ Đã dừng',
                        'done': '✅ Hoàn thành',
                        'error': '❌ Lỗi'
                    }[task.status] || task.status;
                    html += `<div class="task-item" id="msg_task_${task.id}">
                        <div class="task-header">
                            <div><strong style="font-size:13px;">📨 #${task.id}</strong> <span class="task-status ${statusClass}">${statusLabel}</span></div>
                            ${task.status === 'running' ? 
                                `<button class="btn btn-danger btn-sm" onclick="stopMessengerTask('${task.id}')" style="font-size:10px;padding:2px 10px;"><i class="fas fa-stop"></i> Dừng</button>` : 
                                `<button class="btn btn-outline-secondary btn-sm" onclick="removeTask('${task.id}')" style="font-size:10px;padding:2px 10px;border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.4);"><i class="fas fa-trash"></i></button>`
                            }
                        </div>
                        <div style="color:rgba(255,255,255,0.3);font-size:11px;">Box: ${task.box_count} | Delay: ${task.delay}s | File: ${task.filename || 'N/A'}</div>
                    </div>`;
                });
                container.innerHTML = html;
            });
        }

        // ===== ZALO SPAM =====
        function getZaloGroups() {
            const imei = document.getElementById('zaloSpamImei').value.trim();
            const cookie = document.getElementById('zaloSpamCookie').value.trim();
            if (!imei || !cookie) {
                alert('⚠️ Nhập đầy đủ IMEI và Cookie!');
                return;
            }
            const container = document.getElementById('zaloGroupList');
            container.innerHTML = '<div class="text-center"><div class="spinner-small"></div> Đang lấy nhóm...</div>';
            document.getElementById('zaloSpamStatus').textContent = 'Đang lấy...';
            
            fetch('/get_zalo_groups', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ imei: imei, cookie: cookie })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success && data.groups && data.groups.length > 0) {
                    let html = '';
                    data.groups.forEach((group, index) => {
                        const groupId = 'zalo_group_' + index;
                        html += `<div class="box-item" onclick="selectZaloGroup('${group.id}', '${group.name}', '${groupId}')" id="${groupId}">
                            <div><i class="fas fa-users"></i> ${group.name} (${group.members || '?'})</div>
                            <div class="box-check"></div>
                        </div>`;
                    });
                    container.innerHTML = html;
                    document.getElementById('zaloSpamStatus').textContent = '✅ Đã lấy ' + data.groups.length + ' nhóm';
                } else {
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-users"></i><p>${data.message || 'Không tìm thấy nhóm'}</p></div>`;
                    document.getElementById('zaloSpamStatus').textContent = '❌ Không tìm thấy nhóm';
                }
            })
            .catch(err => {
                container.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Lỗi: ${err}</p></div>`;
                document.getElementById('zaloSpamStatus').textContent = '❌ Lỗi: ' + err;
            });
        }

        function selectZaloGroup(id, name, groupId) {
            const idx = selectedZaloGroups.findIndex(g => g.id === id);
            if (idx === -1) {
                selectedZaloGroups.push({ id: id, name: name });
            } else {
                selectedZaloGroups.splice(idx, 1);
            }
            const el = document.getElementById(groupId);
            if (el) {
                if (idx === -1) {
                    el.classList.add('selected');
                    el.querySelector('.box-check').textContent = '✅';
                } else {
                    el.classList.remove('selected');
                    el.querySelector('.box-check').textContent = '';
                }
            }
            const names = selectedZaloGroups.map(g => g.name).join(', ');
            document.getElementById('selectedZaloGroups').value = names || 'Chưa chọn nhóm nào';
        }

        function startZaloSpam() {
            const imei = document.getElementById('zaloSpamImei').value.trim();
            const cookie = document.getElementById('zaloSpamCookie').value.trim();
            const delay = parseFloat(document.getElementById('zaloSpamDelay').value) || 2;
            const content = document.getElementById('zaloSpamContent').value.trim();
            const fileContent = document.getElementById('zaloSpamFileContent').value;
            const groupIds = selectedZaloGroups.map(g => g.id);
            
            if (!imei || !cookie) {
                alert('⚠️ Nhập đầy đủ IMEI và Cookie!');
                return;
            }
            if (groupIds.length === 0) {
                alert('⚠️ Chọn ít nhất 1 nhóm!');
                return;
            }
            const finalContent = fileContent || content;
            if (!finalContent) {
                alert('⚠️ Nhập nội dung hoặc upload file!');
                return;
            }
            
            const btn = document.getElementById('zaloSpamBtn');
            btn.innerHTML = '<span class="spinner-small"></span> Đang khởi động...';
            btn.disabled = true;
            document.getElementById('zaloSpamStatusMsg').innerHTML = '';
            
            fetch('/start_zalo_spam', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    imei: imei,
                    cookie: cookie,
                    group_ids: groupIds,
                    content: finalContent,
                    delay: delay,
                    filename: ''
                })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu spam Zalo';
                btn.disabled = false;
                if (data.success) {
                    document.getElementById('zaloSpamStatusMsg').innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    refreshZaloSpamTasks();
                } else {
                    document.getElementById('zaloSpamStatusMsg').innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu spam Zalo';
                btn.disabled = false;
                document.getElementById('zaloSpamStatusMsg').innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }

        function stopZaloSpamTask(taskId) {
            if (!confirm('Dừng task Zalo Spam #' + taskId + '?')) return;
            fetch('/stop_zalo_spam/' + taskId, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshZaloSpamTasks();
                    alert('✅ ' + data.message);
                } else {
                    alert('❌ ' + data.message);
                }
            });
        }

        function refreshZaloSpamTasks() {
            fetch('/get_zalo_spam_tasks')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('zaloSpamTaskList');
                const count = document.getElementById('zaloSpamTaskCount');
                const tasks = data.tasks || [];
                count.textContent = tasks.length;
                if (tasks.length === 0) {
                    container.innerHTML = '<div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task Zalo Spam nào</p></div>';
                    return;
                }
                let html = '';
                tasks.forEach(task => {
                    const statusClass = task.status;
                    const statusLabel = {
                        'running': '🟢 Đang chạy',
                        'stopped': '⏹ Đã dừng',
                        'done': '✅ Hoàn thành',
                        'error': '❌ Lỗi'
                    }[task.status] || task.status;
                    html += `<div class="task-item" id="zalo_task_${task.id}">
                        <div class="task-header">
                            <div><strong style="font-size:13px;">📨 #${task.id}</strong> <span class="task-status ${statusClass}">${statusLabel}</span></div>
                            ${task.status === 'running' ? 
                                `<button class="btn btn-danger btn-sm" onclick="stopZaloSpamTask('${task.id}')" style="font-size:10px;padding:2px 10px;"><i class="fas fa-stop"></i> Dừng</button>` : 
                                `<button class="btn btn-outline-secondary btn-sm" onclick="removeTask('${task.id}')" style="font-size:10px;padding:2px 10px;border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.4);"><i class="fas fa-trash"></i></button>`
                            }
                        </div>
                        <div style="color:rgba(255,255,255,0.3);font-size:11px;">Nhóm: ${task.group_count} | Delay: ${task.delay}s | File: ${task.filename || 'N/A'}</div>
                    </div>`;
                });
                container.innerHTML = html;
            });
        }

        // ===== START TREO NGÔN =====
        function startTreongon() {
            if (!selectedBoxId_treongon) {
                alert('⚠️ Chọn box chat!');
                return;
            }
            const content = document.getElementById('contentInput_treongon').value;
            if (!content.trim()) {
                alert('⚠️ Nhập nội dung!');
                return;
            }
            const delay = parseFloat(document.getElementById('delayInput_treongon').value) || 2;
            const total = parseInt(document.getElementById('totalInput_treongon').value) || 1;
            const tagAll = document.getElementById('tagAllCheck').checked;
            const tagText = document.getElementById('tagText').value.trim() || '@All';
            const tagColor = document.getElementById('tagColorInput').value || '#db342e';
            const colored = document.getElementById('colorCheck').checked;
            const bold = document.getElementById('boldCheck').checked;
            const color = document.getElementById('colorInput').value.trim() || '#db342e';
            const fontSize = parseInt(document.getElementById('fontSizeInput').value) || 15;
            const multiColor = document.getElementById('multiColorCheck').checked;

            const btn = document.getElementById('treongonBtn');
            btn.innerHTML = '<span class="spinner-small"></span> Đang gửi...';
            btn.disabled = true;

            fetch('/start_treongon', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    box_id: selectedBoxId_treongon,
                    box_name: selectedBox_treongon,
                    content: content,
                    delay: delay,
                    total: total,
                    tag_all: tagAll,
                    tag_text: tagText,
                    tag_color: tagColor,
                    colored: colored,
                    bold: bold,
                    color: color,
                    font_size: fontSize,
                    multi_color: multiColor
                })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu treo';
                btn.disabled = false;
                const status = document.getElementById('treongonStatus');
                if (data.success) {
                    status.innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    setTimeout(() => { status.innerHTML = ''; refreshTasks(); }, 2000);
                } else {
                    status.innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu treo';
                btn.disabled = false;
                document.getElementById('treongonStatus').innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }

        // ===== START NHAY TAG =====
        function startNhaytag() {
            if (!selectedBoxId_nhaytag) {
                alert('⚠️ Chọn box chat!');
                return;
            }
            if (selectedMembers_nhaytag.length === 0) {
                alert('⚠️ Chọn ít nhất 1 thành viên để tag!');
                return;
            }
            const delay = parseFloat(document.getElementById('delayInput_nhaytag').value) || 5;
            const content = document.getElementById('nhayFileContent').value;
            if (!content.trim()) {
                alert('⚠️ Vui lòng upload file nội dung!');
                return;
            }
            const btn = document.getElementById('nhaytagBtn');
            btn.innerHTML = '<span class="spinner-small"></span> Đang khởi động...';
            btn.disabled = true;

            fetch('/start_nhaytag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    box_id: selectedBoxId_nhaytag,
                    box_name: selectedBox_nhaytag,
                    delay: delay,
                    user_ids: selectedMembers_nhaytag,
                    content_text: content
                })
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu nhây tag';
                btn.disabled = false;
                const status = document.getElementById('nhaytagStatus');
                if (data.success) {
                    status.innerHTML = '<div class="alert alert-success">✅ ' + data.message + '</div>';
                    setTimeout(() => { status.innerHTML = ''; refreshTasks(); }, 2000);
                } else {
                    status.innerHTML = '<div class="alert alert-danger">❌ ' + data.message + '</div>';
                }
            })
            .catch(err => {
                btn.innerHTML = '<i class="fas fa-play"></i> Bắt đầu nhây tag';
                btn.disabled = false;
                document.getElementById('nhaytagStatus').innerHTML = '<div class="alert alert-danger">❌ Lỗi: ' + err + '</div>';
            });
        }

        // ===== TASKS =====
        function stopTask(taskId, type) {
            if (!confirm('Dừng task #' + taskId + '?')) return;
            const endpoint = type === 'nhaytag' ? '/stop_nhaytag/' : '/stop_spam/';
            fetch(endpoint + taskId, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) { refreshTasks(); alert('✅ Đã dừng task #' + taskId); }
                else alert('❌ ' + data.message);
            });
        }

        function stopAllTasks() {
            if (!confirm('Dừng tất cả task của bạn?')) return;
            fetch('/stop_all_tasks', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) { refreshTasks(); alert('✅ ' + data.message); }
                else alert('❌ ' + data.message);
            });
        }

        function clearFinishedTasks() {
            if (!confirm('Xóa task đã hoàn thành?')) return;
            fetch('/clear_finished_tasks', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) { refreshTasks(); alert('✅ ' + data.message); }
            });
        }

        function removeTask(taskId) {
            if (!confirm('Xóa task #' + taskId + '?')) return;
            fetch('/remove_task/' + taskId, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshTasks();
                    refreshMessengerTasks();
                    refreshZaloSpamTasks();
                }
            });
        }

        function refreshTasks() {
            fetch('/get_all_tasks')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('taskList');
                const count = document.getElementById('taskListCount');
                const badge = document.getElementById('taskBadge');
                const totalCount = document.getElementById('taskCount');
                const runningCount = document.getElementById('runningCount');
                const tasks = data.tasks || [];
                const running = tasks.filter(t => t.status === 'running');
                count.textContent = tasks.length;
                badge.textContent = tasks.length;
                totalCount.textContent = tasks.length;
                runningCount.textContent = running.length;
                if (tasks.length === 0) {
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task nào</p><small>Bắt đầu treo ngôn, nhây tag, messenger hoặc spam zalo</small></div>`;
                    return;
                }
                let html = '';
                tasks.forEach(task => {
                    const statusClass = task.status;
                    const statusLabel = {
                        'running': '🟢 Đang chạy',
                        'done': '✅ Hoàn thành',
                        'error': '❌ Lỗi',
                        'stopped': '⏹ Đã dừng',
                        'die': '🔴 Cookie Die'
                    }[task.status] || task.status;
                    const progress = task.progress || 0;
                    const typeIcon = task.type === 'nhaytag' ? '🏷' : task.type === 'messenger' ? '💬' : '📨';
                    const tagInfo = task.tag_text ? ` | 🏷 ${task.tag_text}` : '';
                    const memberInfo = task.member_count ? ` | 👥 ${task.member_count} người` : '';
                    html += `<div class="task-item" id="task_${task.id}">
                        <div class="task-header">
                            <div><strong style="font-size:13px;">${typeIcon} #${task.id} — ${task.box_name}</strong> <span class="task-status ${statusClass}">${statusLabel}</span></div>
                            ${task.status === 'running' ? 
                                `<button class="btn btn-danger btn-sm" onclick="stopTask('${task.id}', '${task.type}')" style="font-size:10px;padding:2px 10px;"><i class="fas fa-stop"></i> Dừng</button>` : 
                                `<button class="btn btn-outline-secondary btn-sm" onclick="removeTask('${task.id}')" style="font-size:10px;padding:2px 10px;border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.4);"><i class="fas fa-trash"></i></button>`
                            }
                        </div>
                        <div style="color:rgba(255,255,255,0.3);font-size:11px;">
                            ${task.type === 'treongon' ? `Đã gửi: ${task.sent}/${task.total} | Delay: ${task.delay}s` : `Delay: ${task.delay}s`}
                            ${tagInfo}${memberInfo}
                            ${task.error ? ' | ❌ ' + task.error : ''}
                        </div>
                        <div class="task-progress"><div class="progress-fill" style="width:${progress}%;"></div></div>
                    </div>`;
                });
                container.innerHTML = html;
            })
            .catch(err => console.error('Lỗi refresh tasks:', err));
        }

        // ===== LOAD DATA =====
        function loadAccounts() {
            fetch('/get_accounts')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('accountList');
                const count = document.getElementById('accountListCount');
                const accCount = document.getElementById('accCount');
                const activeCount = document.getElementById('activeCount');
                const accounts = data.accounts || [];
                accCount.textContent = accounts.length;
                activeCount.textContent = accounts.filter(a => a.status === 'active').length;
                if (accounts.length === 0) {
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-users"></i><p>Chưa có tài khoản Zalo nào</p><small>Thêm tài khoản Zalo để bắt đầu</small></div>`;
                    count.textContent = '0';
                    return;
                }
                let html = '';
                accounts.forEach(acc => {
                    const statusClass = acc.status === 'active' ? 'active' : 'inactive';
                    const isCurrent = acc.id === data.current_id;
                    html += `<div class="account-item" id="acc_${acc.id}">
                        <div>
                            <div class="account-name"><i class="fas fa-user"></i> ${acc.name} ${isCurrent ? '<span class="badge bg-primary" style="font-size:9px;">Đang dùng</span>' : ''} ${acc.login_success ? '<span class="badge bg-success" style="font-size:9px;"><i class="fas fa-check"></i></span>' : ''}</div>
                            <div style="color:rgba(255,255,255,0.2);font-size:10px;"><i class="fas fa-mobile-alt"></i> ${(acc.imei || '').substring(0,20)}... <span class="ms-2"><i class="far fa-clock"></i> ${(acc.created_at || '').substring(0,10)}</span></div>
                        </div>
                        <div>
                            <span class="account-status ${statusClass}">${acc.status}</span>
                            <button class="btn btn-sm btn-primary ms-2" onclick="useAccount('${acc.id}')" title="Sử dụng" style="background:var(--primary);border:none;padding:3px 8px;font-size:11px;"><i class="fas fa-play"></i></button>
                            <button class="btn btn-sm btn-danger ms-1" onclick="deleteAccount('${acc.id}')" title="Xóa" style="background:var(--danger);border:none;padding:3px 8px;font-size:11px;"><i class="fas fa-trash"></i></button>
                        </div>
                    </div>`;
                });
                container.innerHTML = html;
                count.textContent = accounts.length;
                if (data.current_name) {
                    document.getElementById('currentAccountDisplay_treongon').value = data.current_name;
                    document.getElementById('sessionStatus_treongon').textContent = '✅ ' + data.current_name;
                    document.getElementById('currentAccountDisplay_nhaytag').value = data.current_name;
                    document.getElementById('sessionStatus_nhaytag').textContent = '✅ ' + data.current_name;
                }
            });
        }

        // ===== AUTO REFRESH =====
        setInterval(refreshTasks, 5000);
        setInterval(refreshMessengerTasks, 5000);
        setInterval(refreshZaloSpamTasks, 5000);

        // ===== INIT =====
        window.onload = function() {
            loadAccounts();
            refreshTasks();
            refreshMessengerTasks();
            refreshZaloSpamTasks();
        };
    </script>
</body>
</html>
"""

# ===== ACCOUNT ROUTES (GIỮ NGUYÊN) =====
# ... (giữ nguyên các route account cũ)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 WEB PNDK TOOL ĐA APP")
    print("📱 https://pndk-tool.onrender.com")
    print("🔐 Đăng nhập để sử dụng")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=10000, threaded=True)
