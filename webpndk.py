# webpndk.py - Zalo Tool Treo Ngôn + Nhây Tag (Hiệu ứng siêu đẹp)
# -*- coding: utf-8 -*-

# ===== CHẶN LOG ZALO API =====
import logging
import sys
import os
import contextlib
import hashlib

# Tắt tất cả log của thư viện zlapi
logging.getLogger("zalo").setLevel(logging.ERROR)
logging.getLogger("zlapi").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("http.client").setLevel(logging.ERROR)

# Chặn stdout/stderr
@contextlib.contextmanager
def suppress_output():
    """Tạm thời chuyển hướng stdout/stderr vào /dev/null"""
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

# Ghi đè print để không in ra màn hình
def null_print(*args, **kwargs):
    pass

# Áp dụng cho toàn bộ module
import builtins
builtins.print = null_print

# ===== IMPORT THƯ VIỆN =====
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import json
import asyncio
import threading
import time
import random
from datetime import datetime
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
current_session = {}
spam_tasks = {}
nhaytag_tasks = {}

def get_account_manager():
    username = session.get('username')
    if not username:
        return None
    if username not in account_managers:
        account_managers[username] = AccountManager(username)
    return account_managers[username]

def get_tasks_files(username):
    return f"tasks_{username}.json", f"nhaytag_tasks_{username}.json"

def load_tasks():
    global spam_tasks, nhaytag_tasks
    username = session.get('username', 'default')
    TASKS_FILE, NHAYTAG_FILE = get_tasks_files(username)
    
    spam_tasks = {}
    nhaytag_tasks = {}
    
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                spam_tasks = data
                logger.info(f"✅ Đã load {len(spam_tasks)} treo ngôn tasks cho user {username}")
        except Exception as e:
            logger.error(f"❌ Lỗi load tasks cho {username}: {e}")
            spam_tasks = {}
    
    if os.path.exists(NHAYTAG_FILE):
        try:
            with open(NHAYTAG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                nhaytag_tasks = data
                logger.info(f"✅ Đã load {len(nhaytag_tasks)} nhây tag tasks cho user {username}")
        except Exception as e:
            logger.error(f"❌ Lỗi load nhaytag tasks cho {username}: {e}")
            nhaytag_tasks = {}

def save_tasks():
    try:
        username = session.get('username', 'default')
        TASKS_FILE, NHAYTAG_FILE = get_tasks_files(username)
        
        tasks_to_save = {}
        for task_id, task in spam_tasks.items():
            task_copy = task.copy()
            task_copy.pop('stop_flag', None)
            task_copy.pop('thread', None)
            tasks_to_save[task_id] = task_copy
        
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks_to_save, f, indent=2, ensure_ascii=False, default=str)
        
        ntags_to_save = {}
        for task_id, task in nhaytag_tasks.items():
            task_copy = task.copy()
            task_copy.pop('stop_flag', None)
            task_copy.pop('thread', None)
            ntags_to_save[task_id] = task_copy
        
        with open(NHAYTAG_FILE, 'w', encoding='utf-8') as f:
            json.dump(ntags_to_save, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"❌ Lỗi save tasks cho {session.get('username', 'default')}: {e}")

def cleanup_dead_tasks():
    for task_id, task in list(spam_tasks.items()):
        if task.get('status') in ['done', 'error', 'stopped']:
            if 'finished_at' in task:
                try:
                    elapsed = (datetime.now() - datetime.fromisoformat(task['finished_at'])).total_seconds()
                    if elapsed > 300:
                        del spam_tasks[task_id]
                except:
                    del spam_tasks[task_id]
        elif task.get('status') == 'running':
            thread = task.get('thread')
            if thread and not thread.is_alive():
                task['status'] = 'error'
                task['finished_at'] = datetime.now().isoformat()
                save_tasks()
    
    for task_id, task in list(nhaytag_tasks.items()):
        if task.get('status') in ['done', 'error', 'stopped']:
            if 'finished_at' in task:
                try:
                    elapsed = (datetime.now() - datetime.fromisoformat(task['finished_at'])).total_seconds()
                    if elapsed > 300:
                        del nhaytag_tasks[task_id]
                except:
                    del nhaytag_tasks[task_id]
        elif task.get('status') == 'running':
            thread = task.get('thread')
            if thread and not thread.is_alive():
                task['status'] = 'error'
                task['finished_at'] = datetime.now().isoformat()
                save_tasks()
    save_tasks()

# ===== WORKER NHAY TAG =====
def worker_nhaytag(imei: str, cookies: dict, group_id: str,
                   delay: float,
                   running_flag: threading.Event,
                   error_queue: list,
                   user_ids: list = None,
                   content_text: str = None):
    """Worker chạy nhây tag trong thread riêng"""
    try:
        with suppress_output():
            from zlapi import ZaloAPI, ThreadType, Message, Mention, MultiMention, MultiMsgStyle, MessageStyle
            
            bot = ZaloAPI("api_key", "secret_key", imei, cookies)
            
            if content_text:
                lines = [l.strip() for l in content_text.split('\n') if l.strip()]
            else:
                file_path = "nhay.txt"
                if not os.path.exists(file_path):
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("Nội dung nhây tag mặc định")
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
            
            if not lines:
                lines = ["Nội dung nhây tag mặc định"]
            
            profiles = {}
            if user_ids:
                for i in range(0, len(user_ids), 10):
                    if running_flag and running_flag.is_set():
                        return
                    batch = user_ids[i:i+10]
                    try:
                        profiles.update(bot.fetchUserInfo(*batch).changed_profiles)
                    except:
                        pass
                    time.sleep(0.3)
            
            line_index = 0
            while running_flag and not running_flag.is_set():
                try:
                    message_text = lines[line_index]
                    msg = "@All " + message_text
                    user_tags = []
                    if user_ids:
                        if not msg.endswith(" "):
                            msg += " "
                        for uid in user_ids:
                            name = profiles.get(uid, {}).get("displayName", f"User {uid[-4:]}")
                            tag = f"@{name}"
                            user_tags.append(tag)
                            msg += tag + " "
                        msg = msg.rstrip()
                    
                    mentions = []
                    all_mention = Mention(uid="-1", length=4, offset=0, auto_format=False)
                    mentions.append(all_mention)
                    
                    if user_ids:
                        for i, tag in enumerate(user_tags):
                            search_start = 5 + len(message_text)
                            if search_start < len(msg):
                                offset = msg.find(tag, search_start)
                                if offset != -1:
                                    mentions.append(Mention(
                                        uid=user_ids[i], length=len(tag), offset=offset, auto_format=False
                                    ))
                    
                    lines_split = msg.strip().split('\n')
                    colors = ["#db342e", "#f27806", "#f7b503", "#15a85f", "#1a73e8", "#9c27b0", "#00bcd4", "#ff5722"]
                    random.shuffle(colors)
                    styles_list = []
                    current_offset = 0
                    for i, line in enumerate(lines_split):
                        if not line:
                            current_offset += 1
                            continue
                        line_color = colors[i % len(colors)]
                        styles_list.append(
                            MessageStyle(offset=current_offset, length=len(line), style="color", color=line_color, auto_format=False)
                        )
                        styles_list.append(
                            MessageStyle(offset=current_offset, length=len(line), style="bold", auto_format=False)
                        )
                        current_offset += len(line) + 1
                    
                    style = MultiMsgStyle(styles_list)
                    bot.setTyping(group_id, ThreadType.GROUP)
                    time.sleep(1.5)
                    
                    if mentions and len(mentions) > 0:
                        m = Message(text=msg, mention=MultiMention(mentions), style=style)
                    else:
                        m = Message(text=msg, style=style)
                    
                    bot.send(m, thread_id=group_id, thread_type=ThreadType.GROUP)
                    
                    line_index += 1
                    if line_index >= len(lines):
                        line_index = 0
                        
                except Exception as e:
                    err = str(e)
                    if "zpw_sek" in err or "600" in err or "cookie" in err.lower():
                        error_queue.append("cookie_die")
                        running_flag.clear()
                        break
                    logger.error(f"Lỗi nhây tag: {e}")
                
                if running_flag and running_flag.is_set():
                    break
                time.sleep(delay)
    except Exception as e:
        logger.error(f"Worker nhaytag lỗi: {e}")

# ===== HTML LOGIN TEMPLATE =====
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập - WEB PNDK TOOL</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            background: #0a0a1a;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', sans-serif;
            position: relative;
            overflow: hidden;
        }

        /* ===== BACKGROUND 3D ===== */
        .bg-3d {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            background: linear-gradient(135deg, #0a0a1a 0%, #1a0a2e 25%, #16213e 50%, #0a0a1a 75%, #1a0a2e 100%);
            background-size: 400% 400%;
            animation: gradientShift 15s ease-in-out infinite;
        }

        @keyframes gradientShift {
            0% { background-position: 0% 0%; }
            25% { background-position: 100% 0%; }
            50% { background-position: 100% 100%; }
            75% { background-position: 0% 100%; }
            100% { background-position: 0% 0%; }
        }

        /* ===== FLOATING ORBS ===== */
        .orb {
            position: fixed;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.5;
            z-index: 0;
            animation: orbFloat 20s ease-in-out infinite;
        }
        .orb-1 { width: 400px; height: 400px; top: -100px; right: -100px; background: radial-gradient(circle, rgba(102, 126, 234, 0.3), transparent); }
        .orb-2 { width: 300px; height: 300px; bottom: -50px; left: -50px; background: radial-gradient(circle, rgba(118, 75, 162, 0.3), transparent); animation-delay: -5s; }
        .orb-3 { width: 200px; height: 200px; top: 50%; left: 50%; transform: translate(-50%, -50%); background: radial-gradient(circle, rgba(255,255,255,0.05), transparent); animation-delay: -10s; filter: blur(120px); }

        @keyframes orbFloat {
            0%, 100% { transform: translate(0, 0) scale(1); }
            25% { transform: translate(30px, -20px) scale(1.1); }
            50% { transform: translate(-20px, 30px) scale(0.9); }
            75% { transform: translate(20px, 20px) scale(1.05); }
        }

        /* ===== PARTICLES ===== */
        .particles-container {
            position: fixed;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
            z-index: 0;
            pointer-events: none;
            overflow: hidden;
        }

        .particle {
            position: absolute;
            width: 4px;
            height: 4px;
            background: white;
            border-radius: 50%;
            opacity: 0;
            animation: particleFloat linear infinite;
        }

        @keyframes particleFloat {
            0% { transform: translateY(100vh) scale(0); opacity: 0; }
            10% { opacity: 0.8; }
            90% { opacity: 0.8; }
            100% { transform: translateY(-10vh) scale(1); opacity: 0; }
        }

        .glow-ring {
            position: fixed;
            width: 600px;
            height: 600px;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            border-radius: 50%;
            border: 1px solid rgba(102, 126, 234, 0.05);
            z-index: 0;
            animation: ringRotate 30s linear infinite;
        }
        .glow-ring::before {
            content: '';
            position: absolute;
            top: -2px;
            left: 50%;
            width: 2px;
            height: 20px;
            background: linear-gradient(to bottom, rgba(102, 126, 234, 0.5), transparent);
            transform: translateX(-50%);
            border-radius: 2px;
            box-shadow: 0 0 20px rgba(102, 126, 234, 0.3);
        }
        @keyframes ringRotate {
            0% { transform: translate(-50%, -50%) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        .glow-ring-2 { width: 450px; height: 450px; animation-duration: 20s; animation-direction: reverse; border-color: rgba(118, 75, 162, 0.03); }
        .glow-ring-2::before { background: linear-gradient(to bottom, rgba(118, 75, 162, 0.5), transparent); box-shadow: 0 0 20px rgba(118, 75, 162, 0.3); }

        /* ===== LOGIN CARD ===== */
        .login-card {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(40px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 30px;
            padding: 45px 40px;
            max-width: 450px;
            width: 100%;
            box-shadow: 0 30px 80px rgba(0, 0, 0, 0.5);
            position: relative;
            z-index: 1;
            animation: slideUp 0.8s ease-out;
        }

        @keyframes slideUp {
            0% { transform: translateY(50px) scale(0.95); opacity: 0; }
            100% { transform: translateY(0) scale(1); opacity: 1; }
        }

        .login-card .logo { text-align: center; margin-bottom: 30px; }
        .login-card .logo .logo-icon {
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 15px;
            font-size: 40px;
            color: white;
            box-shadow: 0 20px 50px rgba(102, 126, 234, 0.3);
            animation: pulseLogo 2.5s ease-in-out infinite;
        }
        @keyframes pulseLogo {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        .login-card .logo h3 {
            font-family: 'Orbitron', monospace;
            font-weight: 900;
            font-size: 24px;
            background: linear-gradient(135deg, #fff, #a78bfa, #667eea);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            animation: textGradient 4s ease-in-out infinite;
        }
        @keyframes textGradient {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .login-card .logo .subtitle {
            color: rgba(255, 255, 255, 0.4);
            font-size: 12px;
            letter-spacing: 3px;
            margin-top: 5px;
            text-transform: uppercase;
        }
        .login-card .logo .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #28a745;
            animation: blink 1.5s ease-in-out infinite;
            margin-right: 6px;
            vertical-align: middle;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        .form-control {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 14px;
            padding: 13px 18px;
            color: #fff;
            transition: all 0.3s;
        }
        .form-control:focus {
            background: rgba(255, 255, 255, 0.06);
            border-color: #667eea;
            box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
            color: #fff;
        }
        .form-control::placeholder { color: rgba(255, 255, 255, 0.2); }
        .form-label {
            color: rgba(255, 255, 255, 0.5);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 6px;
        }

        .password-toggle { position: relative; }
        .password-toggle .toggle-eye {
            position: absolute;
            right: 15px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
            color: rgba(255, 255, 255, 0.25);
            transition: 0.3s;
            z-index: 2;
        }
        .password-toggle .toggle-eye:hover { color: rgba(255, 255, 255, 0.6); }

        .btn-login {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: white;
            padding: 15px;
            border-radius: 14px;
            font-weight: 700;
            width: 100%;
            transition: all 0.3s;
            font-size: 15px;
        }
        .btn-login:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(102, 126, 234, 0.35);
            color: white;
        }
        .btn-login:disabled { opacity: 0.7; transform: none; }

        .tab-header {
            display: flex;
            gap: 10px;
            margin-bottom: 25px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 16px;
            padding: 5px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .tab-header .tab-btn {
            flex: 1;
            padding: 10px;
            border: none;
            background: transparent;
            color: rgba(255, 255, 255, 0.4);
            font-weight: 600;
            font-size: 14px;
            border-radius: 12px;
            transition: all 0.3s;
            cursor: pointer;
        }
        .tab-header .tab-btn:hover { color: rgba(255, 255, 255, 0.7); }
        .tab-header .tab-btn.active {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(118, 75, 162, 0.2));
            color: #fff;
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.1);
        }

        .tab-content { display: none; animation: fadeIn 0.5s ease; }
        .tab-content.active { display: block; }
        @keyframes fadeIn {
            0% { opacity: 0; transform: translateY(10px); }
            100% { opacity: 1; transform: translateY(0); }
        }

        .switch-link {
            text-align: center;
            margin-top: 20px;
            color: rgba(255, 255, 255, 0.35);
            font-size: 14px;
        }
        .switch-link a { color: #a78bfa; text-decoration: none; font-weight: 600; transition: 0.3s; }
        .switch-link a:hover { color: #fff; }

        .alert {
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: rgba(255, 255, 255, 0.8);
            padding: 12px 16px;
            font-size: 13px;
        }
        .alert-success { border-color: rgba(40, 167, 69, 0.2); color: #28a745; }
        .alert-danger { border-color: rgba(220, 53, 69, 0.2); color: #dc3545; }

        .footer-text {
            text-align: center;
            margin-top: 25px;
            color: rgba(255, 255, 255, 0.12);
            font-size: 11px;
            letter-spacing: 1px;
        }
        .footer-text .heart {
            color: #ff4757;
            animation: heartBeat 1.5s ease-in-out infinite;
            display: inline-block;
        }
        @keyframes heartBeat {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.2); }
        }

        .spinner-border-sm { width: 1.2rem; height: 1.2rem; border-width: 0.15em; }

        @media (max-width: 480px) {
            .login-card { padding: 30px 25px; margin: 15px; border-radius: 20px; }
            .login-card .logo .logo-icon { width: 65px; height: 65px; font-size: 32px; }
            .login-card .logo h3 { font-size: 20px; }
            .tab-header .tab-btn { font-size: 12px; padding: 8px; }
            .form-control { padding: 11px 14px; }
            .btn-login { padding: 13px; font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="bg-3d"></div>
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
    <div class="glow-ring"></div>
    <div class="glow-ring glow-ring-2"></div>
    <div class="particles-container" id="particles"></div>

    <div class="login-card">
        <div class="logo">
            <div class="logo-icon"><i class="fas fa-robot"></i></div>
            <h3>WEB PNDK TOOL</h3>
            <div class="subtitle"><span class="status-dot"></span> Hệ thống tự động hóa Zalo</div>
        </div>

        <div class="tab-header">
            <button class="tab-btn active" onclick="switchTab('login')" id="loginTab"><i class="fas fa-sign-in-alt"></i> Đăng nhập</button>
            <button class="tab-btn" onclick="switchTab('register')" id="registerTab"><i class="fas fa-user-plus"></i> Đăng ký</button>
        </div>

        <div class="tab-content active" id="loginForm">
            <form onsubmit="login(event)">
                <div class="mb-3">
                    <label class="form-label"><i class="fas fa-user"></i> Tên đăng nhập</label>
                    <input type="text" class="form-control" id="loginUsername" placeholder="Nhập tên đăng nhập" required>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label"><i class="fas fa-lock"></i> Mật khẩu</label>
                    <input type="password" class="form-control" id="loginPassword" placeholder="Nhập mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('loginPassword', this)"><i class="fas fa-eye"></i></span>
                </div>
                <button type="submit" class="btn btn-login" id="loginBtn"><i class="fas fa-sign-in-alt"></i> Đăng nhập</button>
            </form>
            <div id="loginStatus" class="mt-3"></div>
        </div>

        <div class="tab-content" id="registerForm">
            <form onsubmit="register(event)">
                <div class="mb-3">
                    <label class="form-label"><i class="fas fa-user"></i> Tên đăng nhập</label>
                    <input type="text" class="form-control" id="registerUsername" placeholder="Chọn tên đăng nhập" required>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label"><i class="fas fa-lock"></i> Mật khẩu</label>
                    <input type="password" class="form-control" id="registerPassword" placeholder="Nhập mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('registerPassword', this)"><i class="fas fa-eye"></i></span>
                </div>
                <div class="mb-3 password-toggle">
                    <label class="form-label"><i class="fas fa-check-circle"></i> Xác nhận mật khẩu</label>
                    <input type="password" class="form-control" id="registerPassword2" placeholder="Nhập lại mật khẩu" required>
                    <span class="toggle-eye" onclick="togglePassword('registerPassword2', this)"><i class="fas fa-eye"></i></span>
                </div>
                <button type="submit" class="btn btn-login" id="registerBtn"><i class="fas fa-user-plus"></i> Đăng ký</button>
            </form>
            <div id="registerStatus" class="mt-3"></div>
        </div>

        <div class="footer-text"><span class="heart">❤</span> Phát triển bởi Phan Nguyễn Đăng Khoa</div>
    </div>

    <script>
        function createParticles() {
            const container = document.getElementById('particles');
            const colors = ['#667eea', '#764ba2', '#a78bfa', '#ffffff', '#4facfe'];
            for (let i = 0; i < 50; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                const size = Math.random() * 4 + 2;
                const color = colors[Math.floor(Math.random() * colors.length)];
                particle.style.width = size + 'px';
                particle.style.height = size + 'px';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.background = color;
                particle.style.boxShadow = `0 0 ${size * 2}px ${color}`;
                particle.style.animationDuration = (Math.random() * 15 + 10) + 's';
                particle.style.animationDelay = (Math.random() * 20) + 's';
                container.appendChild(particle);
            }
        }
        createParticles();

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

        function switchTab(tab) {
            const loginForm = document.getElementById('loginForm');
            const registerForm = document.getElementById('registerForm');
            const loginTab = document.getElementById('loginTab');
            const registerTab = document.getElementById('registerTab');

            if (tab === 'login') {
                loginForm.classList.add('active');
                registerForm.classList.remove('active');
                loginTab.classList.add('active');
                registerTab.classList.remove('active');
            } else {
                registerForm.classList.add('active');
                loginForm.classList.remove('active');
                registerTab.classList.add('active');
                loginTab.classList.remove('active');
            }
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
                    setTimeout(() => { 
                        switchTab('login');
                        document.getElementById('loginUsername').value = username;
                        status.innerHTML = '';
                    }, 1500);
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

# ===== HTML MAIN TEMPLATE =====
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
        :root {
            --primary: #667eea;
            --secondary: #764ba2;
            --danger: #dc3545;
            --success: #28a745;
            --warning: #ffc107;
            --glow: rgba(102, 126, 234, 0.4);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            background: #0a0a1a;
            min-height: 100vh;
            padding: 20px;
            font-family: 'Segoe UI', sans-serif;
            color: #fff;
            position: relative;
            overflow-x: hidden;
        }
        
        /* ===== ANIMATED BACKGROUND ===== */
        .bg-animated {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            background: 
                radial-gradient(ellipse at 20% 50%, rgba(102, 126, 234, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 20%, rgba(118, 75, 162, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 80%, rgba(102, 126, 234, 0.05) 0%, transparent 50%);
            animation: bgPulse 8s ease-in-out infinite alternate;
        }
        
        @keyframes bgPulse {
            0% { opacity: 0.5; transform: scale(1); }
            100% { opacity: 1; transform: scale(1.05); }
        }
        
        /* ===== FLOATING SHAPES ===== */
        .float-shape {
            position: fixed;
            border-radius: 50%;
            filter: blur(60px);
            opacity: 0.3;
            z-index: 0;
            animation: floatShape 15s ease-in-out infinite;
        }
        .float-shape-1 { width: 500px; height: 500px; top: -200px; right: -100px; background: rgba(102, 126, 234, 0.2); animation-delay: 0s; }
        .float-shape-2 { width: 400px; height: 400px; bottom: -150px; left: -100px; background: rgba(118, 75, 162, 0.2); animation-delay: -5s; }
        .float-shape-3 { width: 300px; height: 300px; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(255,255,255,0.03); animation-delay: -10s; filter: blur(80px); }
        
        @keyframes floatShape {
            0%, 100% { transform: translate(0, 0) scale(1); }
            25% { transform: translate(30px, -30px) scale(1.1); }
            50% { transform: translate(-20px, 20px) scale(0.9); }
            75% { transform: translate(20px, 30px) scale(1.05); }
        }
        
        /* ===== GRID LINES ===== */
        .grid-lines {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
            background-image: 
                linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
            background-size: 60px 60px;
        }
        
        .container-custom { max-width: 1400px; margin: 0 auto; position: relative; z-index: 1; }
        
        /* ===== HEADER ===== */
        .header-main {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(30px);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 24px;
            padding: 20px 30px;
            margin-bottom: 25px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideDown 0.6s ease-out;
            position: relative;
            overflow: hidden;
        }
        
        .header-main::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle at 30% 50%, rgba(102, 126, 234, 0.05), transparent 70%);
            animation: headerGlow 8s ease-in-out infinite alternate;
        }
        
        @keyframes headerGlow {
            0% { transform: translate(0, 0); }
            100% { transform: translate(10%, 10%); }
        }
        
        @keyframes slideDown {
            0% { transform: translateY(-30px) scale(0.98); opacity: 0; }
            100% { transform: translateY(0) scale(1); opacity: 1; }
        }
        
        .header-main .content {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
            position: relative;
            z-index: 1;
        }
        
        .logo-area {
            display: flex;
            align-items: center;
            gap: 18px;
        }
        
        .logo-icon {
            width: 55px;
            height: 55px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            color: #fff;
            box-shadow: 0 10px 30px rgba(102,126,234,0.3);
            animation: pulseLogo 2s ease-in-out infinite;
            position: relative;
        }
        
        .logo-icon::after {
            content: '';
            position: absolute;
            inset: -3px;
            border-radius: 19px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            z-index: -1;
            opacity: 0.3;
            filter: blur(15px);
            animation: glowPulse 2s ease-in-out infinite;
        }
        
        @keyframes glowPulse {
            0%, 100% { opacity: 0.3; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(1.1); }
        }
        
        @keyframes pulseLogo {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        .brand-title {
            font-family: 'Orbitron', monospace;
            font-weight: 900;
            font-size: 22px;
            background: linear-gradient(135deg, #fff, #a78bfa, #667eea);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: textShine 4s ease-in-out infinite;
        }
        
        @keyframes textShine {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        
        .brand-sub {
            font-size: 12px;
            color: rgba(255,255,255,0.4);
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        
        .brand-sub .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #28a745;
            animation: blink 1.5s ease-in-out infinite;
            margin-right: 6px;
        }
        
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        .header-info {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .info-badge {
            background: rgba(255,255,255,0.05);
            padding: 6px 16px;
            border-radius: 50px;
            font-size: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            display: flex;
            align-items: center;
            gap: 8px;
            color: rgba(255,255,255,0.5);
            transition: all 0.3s;
        }
        
        .info-badge:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.1);
            transform: translateY(-2px);
        }
        
        .info-badge i { color: var(--primary); }
        
        /* ===== USER HEADER ===== */
        .user-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 22px;
            background: rgba(255,255,255,0.04);
            border-radius: 14px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.05);
            animation: fadeInUp 0.8s ease-out;
            transition: all 0.3s;
        }
        
        .user-header:hover {
            background: rgba(255,255,255,0.06);
            border-color: rgba(255,255,255,0.08);
        }
        
        .user-header .user-info {
            display: flex;
            align-items: center;
            gap: 12px;
            color: rgba(255,255,255,0.6);
        }
        
        .user-header .user-info i {
            font-size: 24px;
            color: var(--primary);
            animation: userIconPulse 3s ease-in-out infinite;
        }
        
        @keyframes userIconPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        
        .user-header .user-info strong {
            color: #fff;
            font-size: 15px;
        }
        
        .btn-logout {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.5);
            padding: 6px 18px;
            border-radius: 10px;
            transition: all 0.3s;
            cursor: pointer;
            font-size: 13px;
        }
        
        .btn-logout:hover {
            background: rgba(220,53,69,0.15);
            border-color: rgba(220,53,69,0.3);
            color: #dc3545;
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(220,53,69,0.1);
        }
        
        /* ===== STATS ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
            animation: fadeInUp 0.8s ease-out;
        }
        
        @keyframes fadeInUp {
            0% { transform: translateY(20px); opacity: 0; }
            100% { transform: translateY(0); opacity: 1; }
        }
        
        .stat-card {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 18px;
            padding: 18px 20px;
            text-align: center;
            transition: all 0.4s;
            cursor: default;
            position: relative;
            overflow: hidden;
        }
        
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(102,126,234,0.05), transparent);
            opacity: 0;
            transition: 0.4s;
        }
        
        .stat-card:hover::before {
            opacity: 1;
        }
        
        .stat-card:hover {
            transform: translateY(-6px) scale(1.02);
            background: rgba(255,255,255,0.07);
            border-color: rgba(255,255,255,0.1);
            box-shadow: 0 20px 50px rgba(0,0,0,0.2);
        }
        
        .stat-card .stat-icon {
            font-size: 24px;
            margin-bottom: 5px;
            display: block;
            color: var(--primary);
        }
        
        .stat-card .stat-number {
            font-size: 30px;
            font-weight: 700;
            background: linear-gradient(135deg, #fff, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            transition: 0.3s;
        }
        
        .stat-card:hover .stat-number {
            transform: scale(1.05);
        }
        
        .stat-card .stat-label {
            font-size: 12px;
            color: rgba(255,255,255,0.35);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 2px;
        }
        
        /* ===== MAIN CARD ===== */
        .main-card {
            background: rgba(255,255,255,0.03);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 25px 60px rgba(0,0,0,0.3);
            animation: fadeInUp 1s ease-out;
        }
        
        .main-card .card-header-custom {
            background: rgba(255,255,255,0.03);
            padding: 15px 25px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .main-card .card-header-custom .nav-link {
            color: rgba(255,255,255,0.4);
            border: none;
            padding: 8px 22px;
            font-weight: 600;
            border-radius: 12px;
            transition: all 0.3s;
            font-size: 14px;
            position: relative;
        }
        
        .main-card .card-header-custom .nav-link::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 50%;
            width: 0;
            height: 2px;
            background: linear-gradient(90deg, var(--primary), var(--secondary));
            transition: 0.3s;
            transform: translateX(-50%);
        }
        
        .main-card .card-header-custom .nav-link:hover::after {
            width: 60%;
        }
        
        .main-card .card-header-custom .nav-link:hover {
            color: #fff;
            background: rgba(255,255,255,0.04);
        }
        
        .main-card .card-header-custom .nav-link.active {
            color: #fff;
            background: linear-gradient(135deg, rgba(102,126,234,0.15), rgba(118,75,162,0.15));
            box-shadow: 0 10px 30px rgba(102,126,234,0.05);
        }
        
        .main-card .card-header-custom .nav-link.active::after {
            width: 60%;
        }
        
        .main-card .card-body {
            padding: 25px;
        }
        
        /* ===== FOOTER ===== */
        .footer-main {
            margin-top: 25px;
            padding: 15px 30px;
            background: rgba(255,255,255,0.02);
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.03);
            text-align: center;
            color: rgba(255,255,255,0.2);
            font-size: 12px;
            animation: fadeInUp 1.2s ease-out;
        }
        
        .footer-main .heart {
            color: #ff4757;
            animation: heartBeat 1.5s ease-in-out infinite;
            display: inline-block;
        }
        
        @keyframes heartBeat {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.2); }
        }
        
        .footer-main a {
            color: rgba(255,255,255,0.3);
            text-decoration: none;
            transition: 0.3s;
        }
        
        .footer-main a:hover {
            color: #a78bfa;
        }
        
        /* ===== BOX ITEM ===== */
        .box-item {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 10px 16px;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: rgba(255,255,255,0.6);
        }
        
        .box-item:hover {
            background: rgba(255,255,255,0.06);
            border-color: var(--primary);
            transform: translateX(5px);
        }
        
        .box-item.selected {
            background: rgba(102,126,234,0.12);
            border-color: var(--primary);
            box-shadow: 0 0 30px rgba(102,126,234,0.05);
            color: #fff;
        }
        
        .box-item .box-check {
            color: var(--success);
            font-size: 16px;
        }
        
        /* ===== ACCOUNT ITEM ===== */
        .account-item {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 10px 16px;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s;
            color: rgba(255,255,255,0.6);
        }
        
        .account-item:hover {
            background: rgba(255,255,255,0.05);
            border-color: rgba(255,255,255,0.08);
        }
        
        .account-item .account-name {
            font-weight: 600;
            color: #a78bfa;
        }
        
        .account-status {
            padding: 2px 10px;
            border-radius: 50px;
            font-size: 10px;
            font-weight: 600;
        }
        .account-status.active { background: rgba(40,167,69,0.15); color: #28a745; }
        .account-status.inactive { background: rgba(220,53,69,0.15); color: #dc3545; }
        
        /* ===== TASK ITEM ===== */
        .task-item {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 14px;
            padding: 14px 18px;
            margin-bottom: 8px;
            transition: all 0.3s;
        }
        
        .task-item:hover {
            background: rgba(255,255,255,0.05);
            border-color: rgba(255,255,255,0.08);
            transform: translateX(3px);
        }
        
        .task-item .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        
        .task-progress {
            height: 4px;
            background: rgba(255,255,255,0.05);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 8px;
        }
        
        .task-progress .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--secondary));
            transition: width 0.5s;
            border-radius: 2px;
        }
        
        .task-status {
            padding: 2px 10px;
            border-radius: 50px;
            font-size: 10px;
            font-weight: 600;
        }
        .task-status.running { background: rgba(40,167,69,0.15); color: #28a745; }
        .task-status.done { background: rgba(102,126,234,0.15); color: #667eea; }
        .task-status.error { background: rgba(220,53,69,0.15); color: #dc3545; }
        .task-status.stopped { background: rgba(255,193,7,0.15); color: #ffc107; }
        .task-status.die { background: rgba(220,53,69,0.2); color: #ff6b6b; }
        
        /* ===== MEMBER ITEM ===== */
        .member-item {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 6px 12px;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: rgba(255,255,255,0.5);
            font-size: 13px;
        }
        
        .member-item:hover {
            background: rgba(255,255,255,0.06);
        }
        
        .member-item.selected {
            background: rgba(102,126,234,0.1);
            border-color: var(--primary);
            color: #fff;
        }
        
        /* ===== BUTTONS ===== */
        .btn-primary-custom {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border: none;
            color: #fff;
            padding: 10px 22px;
            border-radius: 14px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(102,126,234,0.15);
            position: relative;
            overflow: hidden;
        }
        
        .btn-primary-custom::after {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1), transparent 70%);
            opacity: 0;
            transition: 0.5s;
        }
        
        .btn-primary-custom:hover::after {
            opacity: 1;
        }
        
        .btn-primary-custom:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(102,126,234,0.3);
            color: #fff;
        }
        
        .btn-success-custom {
            background: linear-gradient(135deg, #28a745, #20c997);
            border: none;
            color: #fff;
            padding: 10px 22px;
            border-radius: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-success-custom:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(40,167,69,0.25);
            color: #fff;
        }
        
        .btn-danger-custom {
            background: linear-gradient(135deg, #dc3545, #c82333);
            border: none;
            color: #fff;
            padding: 10px 22px;
            border-radius: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-danger-custom:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(220,53,69,0.25);
            color: #fff;
        }
        
        .btn-warning-custom {
            background: linear-gradient(135deg, #ffc107, #f7b503);
            border: none;
            color: #333;
            padding: 10px 22px;
            border-radius: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-warning-custom:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(255,193,7,0.25);
            color: #333;
        }
        
        /* ===== FORM ===== */
        .form-control {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.05);
            color: #fff;
            border-radius: 12px;
            padding: 10px 15px;
            transition: all 0.3s;
        }
        
        .form-control:focus {
            background: rgba(255,255,255,0.06);
            border-color: var(--primary);
            color: #fff;
            box-shadow: 0 0 0 4px rgba(102,126,234,0.05);
        }
        
        .form-control::placeholder {
            color: rgba(255,255,255,0.2);
        }
        
        .form-label {
            color: rgba(255,255,255,0.4);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .form-check-label {
            color: rgba(255,255,255,0.5);
            font-size: 13px;
        }
        
        .form-check-input {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .form-check-input:checked {
            background-color: var(--primary);
            border-color: var(--primary);
        }
        
        /* ===== ALERT ===== */
        .alert {
            border-radius: 14px;
            border: none;
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.7);
            border: 1px solid rgba(255,255,255,0.05);
        }
        .alert-info { background: rgba(102,126,234,0.08); color: #a78bfa; border-color: rgba(102,126,234,0.1); }
        .alert-success { background: rgba(40,167,69,0.08); color: #28a745; border-color: rgba(40,167,69,0.1); }
        .alert-danger { background: rgba(220,53,69,0.08); color: #dc3545; border-color: rgba(220,53,69,0.1); }
        
        /* ===== SCROLLBAR ===== */
        .list-container::-webkit-scrollbar { width: 4px; }
        .list-container::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); border-radius: 2px; }
        .list-container::-webkit-scrollbar-thumb { background: var(--primary); border-radius: 2px; }
        .list-container { max-height: 400px; overflow-y: auto; padding-right: 5px; }
        .member-list { max-height: 300px; overflow-y: auto; }
        
        /* ===== EMPTY STATE ===== */
        .empty-state { text-align: center; padding: 30px 20px; color: rgba(255,255,255,0.15); }
        .empty-state i { font-size: 40px; display: block; margin-bottom: 10px; color: rgba(255,255,255,0.05); }
        .empty-state p { font-size: 14px; }
        .empty-state small { color: rgba(255,255,255,0.1); }
        
        /* ===== FILE UPLOAD ===== */
        .file-upload-area {
            border: 2px dashed rgba(255,255,255,0.06);
            padding: 15px;
            text-align: center;
            border-radius: 14px;
            cursor: pointer;
            transition: all 0.3s;
            color: rgba(255,255,255,0.2);
        }
        .file-upload-area:hover {
            border-color: var(--primary);
            background: rgba(255,255,255,0.03);
            color: rgba(255,255,255,0.4);
        }
        
        /* ===== MISC ===== */
        .color-picker { width: 50px; height: 36px; padding: 2px; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; cursor: pointer; background: transparent; }
        .spinner-small { width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.1); border-top: 2px solid #fff; border-radius: 50%; animation: spin 1s linear infinite; display: inline-block; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* ===== RESPONSIVE ===== */
        @media (max-width: 768px) {
            .brand-title { font-size: 16px; }
            .header-info { gap: 8px; }
            .info-badge { font-size: 10px; padding: 4px 12px; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .logo-icon { width: 40px; height: 40px; font-size: 20px; }
            .main-card .card-body { padding: 15px; }
            .user-header { flex-wrap: wrap; gap: 10px; }
        }
        
        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr; }
            .header-main .content { flex-direction: column; text-align: center; }
            .logo-area { flex-direction: column; }
        }
    </style>
</head>
<body>
    <!-- ===== BACKGROUND EFFECTS ===== -->
    <div class="bg-animated"></div>
    <div class="grid-lines"></div>
    <div class="float-shape float-shape-1"></div>
    <div class="float-shape float-shape-2"></div>
    <div class="float-shape float-shape-3"></div>

    <div class="container-custom">
        <!-- HEADER -->
        <div class="header-main">
            <div class="content">
                <div class="logo-area">
                    <div class="logo-icon"><i class="fas fa-robot"></i></div>
                    <div>
                        <div class="brand-title">WEB PNDK TOOL</div>
                        <div class="brand-sub"><span class="status-dot"></span> Hệ thống tự động hóa Zalo</div>
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
                <span class="badge bg-success" style="font-size: 10px; background: rgba(40,167,69,0.15) !important; color: #28a745;"><i class="fas fa-check-circle"></i> Đã đăng nhập</span>
            </div>
            <div>
                <button class="btn-logout" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Đăng xuất</button>
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
                <ul class="nav nav-tabs" id="myTab" role="tablist" style="border: none; gap: 3px;">
                    <li class="nav-item"><button class="nav-link active" id="accounts-tab" data-bs-toggle="tab" data-bs-target="#accounts" type="button" role="tab"><i class="fas fa-users"></i> Tài khoản</button></li>
                    <li class="nav-item"><button class="nav-link" id="treongon-tab" data-bs-toggle="tab" data-bs-target="#treongon" type="button" role="tab"><i class="fas fa-paper-plane"></i> Treo Ngôn</button></li>
                    <li class="nav-item"><button class="nav-link" id="nhaytag-tab" data-bs-toggle="tab" data-bs-target="#nhaytag" type="button" role="tab"><i class="fas fa-tags"></i> Nhây Tag</button></li>
                    <li class="nav-item"><button class="nav-link" id="tasks-tab" data-bs-toggle="tab" data-bs-target="#tasks" type="button" role="tab"><i class="fas fa-tasks"></i> Quản Lý Task <span class="badge bg-danger" id="taskBadge" style="font-size: 10px;">0</span></button></li>
                </ul>
            </div>
            
            <div class="card-body">
                <div class="tab-content">
                    <!-- ACCOUNTS -->
                    <div class="tab-pane fade show active" id="accounts" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-plus-circle"></i> Thêm tài khoản Zalo</div>
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
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-list"></i> Danh sách tài khoản Zalo <span class="badge bg-light text-dark" id="accountListCount" style="float: right; font-size: 11px;">0</span></div>
                                    <div class="card-body">
                                        <div class="list-container" id="accountList">
                                            <div class="empty-state"><i class="fas fa-users"></i><p>Chưa có tài khoản Zalo nào</p><small>Thêm tài khoản Zalo để bắt đầu</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TREO NGÔN -->
                    <div class="tab-pane fade" id="treongon" role="tabpanel">
                        <div class="row">
                            <div class="col-md-4">
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-comments"></i> Box chat</div>
                                    <div class="card-body">
                                        <button class="btn btn-primary-custom w-100 mb-3" onclick="refreshBoxes('treongon')"><i class="fas fa-sync"></i> Làm mới box chat</button>
                                        <div id="boxListContainer_treongon" class="list-container">
                                            <div class="empty-state"><i class="fas fa-inbox"></i><p>Chưa có box chat</p><small>Chọn tài khoản Zalo và làm mới</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-8">
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-paper-plane"></i> Treo Ngôn <span class="badge bg-light text-dark" id="sessionStatus_treongon" style="float: right; font-size: 11px;">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-user"></i> Tài khoản đang dùng</label><input type="text" class="form-control" id="currentAccountDisplay_treongon" readonly value="Chưa chọn"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-comment"></i> Box đã chọn</label><input type="text" class="form-control" id="selectedBox_treongon" readonly placeholder="Chọn box"></div></div>
                                        </div>
                                        
                                        <div class="row mb-3">
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="tagAllCheck" checked><label class="form-check-label" for="tagAllCheck">Tag All</label></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-pencil-alt"></i> Chữ tag</label><input type="text" class="form-control" id="tagText" value="@All" style="font-size: 13px;"></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-palette"></i> Màu tag</label><div class="d-flex align-items-center"><input type="color" class="color-picker me-2" id="tagColorPicker" value="#db342e"><input type="text" class="form-control" id="tagColorInput" value="#db342e" style="width:80px; font-size:12px;"></div></div></div>
                                        </div>
                                        
                                        <div class="row mb-3">
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="colorCheck" checked><label class="form-check-label" for="colorCheck">Màu nội dung</label></div></div>
                                            <div class="col-md-4"><div class="form-check"><input class="form-check-input" type="checkbox" id="boldCheck" checked><label class="form-check-label" for="boldCheck">In đậm</label></div></div>
                                            <div class="col-md-4"><div class="form-group"><label class="form-label"><i class="fas fa-palette"></i> Màu nội dung</label><div class="d-flex align-items-center"><input type="color" class="color-picker me-2" id="colorPicker" value="#db342e"><input type="text" class="form-control" id="colorInput" value="#db342e" style="width:80px; font-size:12px;"></div></div></div>
                                        </div>
                                        
                                        <div class="row">
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label><input type="number" class="form-control" id="delayInput_treongon" value="2" min="0.5" step="0.5"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-redo"></i> Số lần gửi</label><input type="number" class="form-control" id="totalInput_treongon" value="1" min="1"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-font"></i> Size chữ</label><input type="number" class="form-control" id="fontSizeInput" value="15" min="8" max="30"></div></div>
                                            <div class="col-md-3"><div class="mb-3"><label class="form-label"><i class="fas fa-layer-group"></i> Màu mỗi dòng</label><div class="form-check"><input class="form-check-input" type="checkbox" id="multiColorCheck"><label class="form-check-label" for="multiColorCheck">Nhiều màu</label></div></div></div>
                                        </div>
                                        
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-file-alt"></i> Nội dung</label><textarea class="form-control" id="contentInput_treongon" rows="4" placeholder="pndkdzcute&#10;pndkdzcute&#10;22:22"></textarea></div>
                                        
                                        <div class="mb-3"><label class="form-label"><i class="fas fa-upload"></i> Hoặc tải file .txt</label>
                                            <div class="file-upload-area" onclick="document.getElementById('fileInput_treongon').click()">
                                                <i class="fas fa-cloud-upload-alt fa-2x"></i>
                                                <p style="margin: 5px 0 0 0; font-size: 13px;">Nhấn để chọn file .txt</p>
                                                <input type="file" id="fileInput_treongon" accept=".txt" style="display:none;" onchange="loadFileContent(event, 'contentInput_treongon', 'fileName_treongon', 'fileText_treongon')">
                                            </div>
                                            <div id="fileName_treongon" class="mt-2 text-success" style="display:none; font-size: 13px;">📎 Đã chọn: <span id="fileText_treongon"></span></div>
                                        </div>
                                        
                                        <button class="btn btn-primary-custom w-100" onclick="startTreongon()" id="treongonBtn"><i class="fas fa-play"></i> Bắt đầu treo</button>
                                        <div id="treongonStatus" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- NHAY TAG -->
                    <div class="tab-pane fade" id="nhaytag" role="tabpanel">
                        <div class="row">
                            <div class="col-md-5">
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-comments"></i> Box chat</div>
                                    <div class="card-body">
                                        <button class="btn btn-primary-custom w-100 mb-3" onclick="refreshBoxes('nhaytag')"><i class="fas fa-sync"></i> Làm mới box chat</button>
                                        <div id="boxListContainer_nhaytag" class="list-container">
                                            <div class="empty-state"><i class="fas fa-inbox"></i><p>Chưa có box chat</p><small>Chọn tài khoản Zalo và làm mới</small></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-7">
                                <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                                    <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-tags"></i> Nhây Tag <span class="badge bg-light text-dark" id="sessionStatus_nhaytag" style="float: right; font-size: 11px;">Chưa đăng nhập</span></div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-user"></i> Tài khoản đang dùng</label><input type="text" class="form-control" id="currentAccountDisplay_nhaytag" readonly value="Chưa chọn"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-comment"></i> Box đã chọn</label><input type="text" class="form-control" id="selectedBox_nhaytag" readonly placeholder="Chọn box"></div></div>
                                        </div>
                                        
                                        <div class="row">
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-clock"></i> Delay (giây)</label><input type="number" class="form-control" id="delayInput_nhaytag" value="5" min="1" step="0.5"></div></div>
                                            <div class="col-md-6"><div class="mb-3"><label class="form-label"><i class="fas fa-file-alt"></i> File nội dung</label>
                                                <div class="file-upload-area" onclick="document.getElementById('fileInput_nhaytag').click()" style="padding: 10px;">
                                                    <i class="fas fa-cloud-upload-alt"></i>
                                                    <span style="font-size: 13px;">Nhấn để chọn file .txt</span>
                                                    <input type="file" id="fileInput_nhaytag" accept=".txt" style="display:none;" onchange="loadNhayFile(event)">
                                                </div>
                                                <div id="fileName_nhaytag" class="mt-2 text-success" style="display:none; font-size: 13px;">📎 Đã chọn: <span id="fileText_nhaytag"></span></div>
                                                <div id="nhayFilePreview" class="mt-2"></div>
                                                <input type="hidden" id="nhayFileContent" value="">
                                                <small style="color: rgba(255,255,255,0.3); font-size: 11px;">Mỗi dòng là 1 đoạn nội dung sẽ được gửi</small>
                                            </div></div>
                                        </div>
                                        
                                        <div class="mb-3">
                                            <label class="form-label"><i class="fas fa-users"></i> Thành viên (chọn người tag)</label>
                                            <button class="btn btn-sm btn-primary-custom mb-2" onclick="fetchMembers('nhaytag')" style="font-size: 12px; padding: 5px 15px;"><i class="fas fa-sync"></i> Lấy danh sách thành viên</button>
                                            <div id="memberListContainer_nhaytag" class="member-list">
                                                <div class="empty-state"><i class="fas fa-users"></i><p>Chưa có thành viên</p><small>Nhấn nút trên để lấy</small></div>
                                            </div>
                                            <div class="mt-2">
                                                <button class="btn btn-sm btn-outline-success" onclick="selectAllMembers('nhaytag')" style="border-color: rgba(40,167,69,0.3); color: #28a745; font-size: 12px;">Chọn tất cả</button>
                                                <button class="btn btn-sm btn-outline-secondary" onclick="deselectAllMembers('nhaytag')" style="border-color: rgba(255,255,255,0.1); color: rgba(255,255,255,0.4); font-size: 12px;">Bỏ chọn</button>
                                                <span class="ms-2" id="memberCount_nhaytag" style="color: rgba(255,255,255,0.4); font-size: 13px;">Đã chọn: 0</span>
                                            </div>
                                        </div>
                                        
                                        <button class="btn btn-warning-custom w-100" onclick="startNhaytag()" id="nhaytagBtn"><i class="fas fa-play"></i> Bắt đầu nhây tag</button>
                                        <div id="nhaytagStatus" class="mt-3"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TASKS -->
                    <div class="tab-pane fade" id="tasks" role="tabpanel">
                        <div class="card" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px;">
                            <div class="card-header" style="background: transparent; border: none; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 14px;"><i class="fas fa-tasks"></i> Quản Lý Task <span class="badge bg-light text-dark" id="taskListCount" style="float: right; font-size: 11px;">0</span></div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <button class="btn btn-sm btn-outline-secondary" onclick="refreshTasks()" style="border-color: rgba(255,255,255,0.1); color: rgba(255,255,255,0.4); font-size: 12px;"><i class="fas fa-sync"></i> Làm mới</button>
                                    <button class="btn btn-sm btn-outline-danger" onclick="stopAllTasks()" style="border-color: rgba(255,193,7,0.2); color: #ffc107; font-size: 12px;"><i class="fas fa-stop"></i> Dừng tất cả</button>
                                    <button class="btn btn-sm btn-outline-danger" onclick="clearFinishedTasks()" style="border-color: rgba(220,53,69,0.2); color: #dc3545; font-size: 12px;"><i class="fas fa-trash"></i> Xóa task hoàn thành</button>
                                </div>
                                <div class="list-container" id="taskList" style="max-height: 500px;">
                                    <div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task nào</p><small>Bắt đầu treo ngôn hoặc nhây tag để tạo task</small></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer-main">
            <p style="margin: 0;">
                <i class="fas fa-crown" style="color: #f7b503;"></i>
                <strong style="color: rgba(255,255,255,0.3);">WEB PNDK TOOL</strong>
                <span class="heart">❤️</span>
                Phát triển bởi <a href="#">Phan Nguyễn Đăng Khoa</a>
                <span style="margin: 0 8px;">|</span>
                <i class="fas fa-code"></i> v3.0
                <span style="margin: 0 8px;">|</span>
                <i class="fas fa-shield-alt"></i> Bảo mật & An toàn
            </p>
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
        let selectedBox_treongon = '', selectedBoxId_treongon = '';
        let selectedBox_nhaytag = '', selectedBoxId_nhaytag = '';
        let members_nhaytag = [], selectedMembers_nhaytag = [];

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
                    `<div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 8px 12px; margin-top: 8px; border: 1px solid rgba(255,255,255,0.05);">
                        <small style="color: rgba(255,255,255,0.4);"><strong>📄 ${lines.length} dòng</strong></small>
                        <pre style="max-height:100px; overflow-y:auto; font-size:12px; margin:5px 0 0 0; background: rgba(0,0,0,0.2); padding:8px; border-radius:4px; color: rgba(255,255,255,0.5);">${preview}${lines.length > 10 ? '\\n...' : ''}</pre>
                    </div>`;
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

        // ===== START TREO NGÔN =====
        function startTreongon() {
            if (!selectedBoxId_treongon) { alert('⚠️ Chọn box chat!'); return; }
            const content = document.getElementById('contentInput_treongon').value;
            if (!content.trim()) { alert('⚠️ Nhập nội dung!'); return; }
            
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
                    content, delay, total, tag_all: tagAll, tag_text: tagText,
                    tag_color: tagColor, colored, bold, color, font_size: fontSize, multi_color: multiColor
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
            if (!selectedBoxId_nhaytag) { alert('⚠️ Chọn box chat!'); return; }
            if (selectedMembers_nhaytag.length === 0) { alert('⚠️ Chọn ít nhất 1 thành viên để tag!'); return; }
            const delay = parseFloat(document.getElementById('delayInput_nhaytag').value) || 5;
            const content = document.getElementById('nhayFileContent').value;
            if (!content.trim()) { alert('⚠️ Vui lòng upload file nội dung!'); return; }

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
                    container.innerHTML = `<div class="empty-state"><i class="fas fa-tasks"></i><p>Chưa có task nào</p><small>Bắt đầu treo ngôn hoặc nhây tag để tạo task</small></div>`;
                    return;
                }
                
                let html = '';
                tasks.forEach(task => {
                    const statusClass = task.status;
                    const statusLabel = { 'running': '🟢 Đang chạy', 'done': '✅ Hoàn thành', 'error': '❌ Lỗi', 'stopped': '⏹ Đã dừng', 'die': '🔴 Cookie Die' }[task.status] || task.status;
                    const progress = task.progress || 0;
                    const typeIcon = task.type === 'nhaytag' ? '🏷' : '📨';
                    const tagInfo = task.tag_text ? ` | 🏷 ${task.tag_text}` : '';
                    const memberInfo = task.member_count ? ` | 👥 ${task.member_count} người` : '';
                    
                    html += `<div class="task-item" id="task_${task.id}">
                        <div class="task-header">
                            <div><strong style="font-size: 14px;">${typeIcon} #${task.id} — ${task.box_name}</strong><span class="task-status ${statusClass}">${statusLabel}</span></div>
                            ${task.status === 'running' ? `<button class="btn btn-danger btn-sm" onclick="stopTask('${task.id}', '${task.type}')" style="font-size: 11px; padding: 4px 12px;"><i class="fas fa-stop"></i> Dừng</button>` : `<button class="btn btn-outline-secondary btn-sm" onclick="removeTask('${task.id}')" style="font-size: 11px; padding: 4px 12px; border-color: rgba(255,255,255,0.1); color: rgba(255,255,255,0.4);"><i class="fas fa-trash"></i></button>`}
                        </div>
                        <div class="text-muted small" style="color: rgba(255,255,255,0.3); font-size: 12px;">
                            ${task.type === 'treongon' ? `Đã gửi: ${task.sent}/${task.total} | Delay: ${task.delay}s` : `Delay: ${task.delay}s`}
                            ${tagInfo}${memberInfo}
                            ${task.error ? ' | ❌ ' + task.error : ''}
                        </div>
                        <div class="task-progress"><div class="progress-fill" style="width: ${progress}%;"></div></div>
                    </div>`;
                });
                container.innerHTML = html;
            })
            .catch(err => console.error('Lỗi refresh tasks:', err));
        }

        function removeTask(taskId) {
            if (!confirm('Xóa task #' + taskId + '?')) return;
            fetch('/remove_task/' + taskId, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => { if (data.success) refreshTasks(); });
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
                            <div class="account-name">
                                <i class="fas fa-user"></i> ${acc.name} 
                                ${isCurrent ? '<span class="badge bg-primary" style="font-size: 10px;">Đang dùng</span>' : ''}
                                ${acc.login_success ? '<span class="badge bg-success" style="font-size: 10px;"><i class="fas fa-check"></i></span>' : ''}
                            </div>
                            <div class="text-muted small" style="color: rgba(255,255,255,0.2); font-size: 11px;">
                                <i class="fas fa-mobile-alt"></i> ${(acc.imei || '').substring(0,20)}... 
                                <span class="ms-2"><i class="far fa-clock"></i> ${(acc.created_at || '').substring(0,10)}</span>
                            </div>
                        </div>
                        <div>
                            <span class="account-status ${statusClass}">${acc.status}</span>
                            <button class="btn btn-sm btn-primary ms-2" onclick="useAccount('${acc.id}')" title="Sử dụng" style="background: var(--primary); border: none; padding: 4px 10px; font-size: 12px;"><i class="fas fa-play"></i></button>
                            <button class="btn btn-sm btn-danger ms-1" onclick="deleteAccount('${acc.id}')" title="Xóa" style="background: var(--danger); border: none; padding: 4px 10px; font-size: 12px;"><i class="fas fa-trash"></i></button>
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
        setInterval(refreshTasks, 3000);

        // ===== INIT =====
        window.onload = function() {
            loadAccounts();
            refreshTasks();
        };
    </script>
</body>
</html>
"""

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
        load_tasks()
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
    if username and username in account_managers:
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

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    load_tasks()
    return render_template_string(HTML_TEMPLATE, username=session.get('username', 'User'))

# ===== ACCOUNT ROUTES =====
@app.route('/add_account', methods=['POST'])
def add_account():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        cookies = data.get('cookies', '').strip()
        imei = data.get('imei', '').strip()
        note = data.get('note', '').strip()
        
        if not name or not cookies or not imei:
            return jsonify({'success': False, 'message': 'Thiếu thông tin!'})
        
        am = get_account_manager()
        if not am:
            return jsonify({'success': False, 'message': 'Vui lòng đăng nhập!'})
        
        success, result = am.add_account(name, cookies, imei, note)
        if success:
            return jsonify({'success': True, 'message': f'Đã thêm {name}!', 'account_id': result})
        else:
            return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_accounts', methods=['GET'])
def get_accounts():
    am = get_account_manager()
    if not am:
        return jsonify({'accounts': [], 'current_id': None, 'current_name': None})
    
    accounts = am.list_accounts()
    current = am.get_current_account()
    return jsonify({
        'accounts': accounts,
        'current_id': current.get('id') if current else None,
        'current_name': current.get('name') if current else None
    })

@app.route('/use_account/<account_id>', methods=['POST'])
def use_account(account_id):
    global current_session
    
    am = get_account_manager()
    if not am:
        return jsonify({'success': False, 'message': 'Vui lòng đăng nhập!'})
    
    try:
        account = am.get_account(account_id)
        if not account:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản!'})
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            login_with_cookies_imei_async(account['cookies'], account['imei'])
        )
        loop.close()
        
        if result.get('success'):
            current_session = {
                'account_id': account_id,
                'cookies': result.get('cookies', {}),
                'user_info': result.get('user_info', {}),
                'imei': account['imei']
            }
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            boxes = loop.run_until_complete(
                get_box_chats_async(account['imei'], result.get('cookies', {}))
            )
            loop.close()
            
            am.update_login_status(account_id, True, len(boxes))
            am.set_current_account(account_id)
            return jsonify({
                'success': True, 
                'message': f'Đăng nhập thành công! {len(boxes)} box chat',
                'boxes': boxes
            })
        else:
            am.update_login_status(account_id, False)
            return jsonify({'success': False, 'message': result.get('message', 'Đăng nhập thất bại!')})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/delete_account/<account_id>', methods=['DELETE'])
def delete_account(account_id):
    am = get_account_manager()
    if not am:
        return jsonify({'success': False, 'message': 'Vui lòng đăng nhập!'})
    
    try:
        success = am.delete_account(account_id)
        return jsonify({'success': success, 'message': 'Đã xóa!' if success else 'Không tìm thấy!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ===== BOX ROUTES =====
@app.route('/get_boxes', methods=['GET'])
def get_boxes():
    global current_session
    try:
        if not current_session or not current_session.get('cookies'):
            return jsonify({'success': False, 'message': 'Chưa đăng nhập!'})
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        boxes = loop.run_until_complete(
            get_box_chats_async(current_session.get('imei', ''), current_session.get('cookies', {}))
        )
        loop.close()
        return jsonify({'success': True, 'boxes': boxes})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_members/<group_id>', methods=['GET'])
def get_members(group_id):
    global current_session
    try:
        if not current_session or not current_session.get('cookies'):
            return jsonify({'success': False, 'message': 'Chưa đăng nhập!'})
        
        from zlapi import ZaloAPI
        bot = ZaloAPI("api_key", "secret_key", current_session.get('imei', ''), current_session.get('cookies', {}))
        
        info = bot.fetchGroupInfo(group_id)
        members = []
        for mem in info.gridInfoMap[group_id]["memVerList"]:
            uid = mem.split("_")[0]
            try:
                user_info = bot.fetchUserInfo(uid)
                name = user_info.changed_profiles[uid]["displayName"]
            except:
                name = f"User_{uid}"
            members.append({"id": uid, "name": name})
        
        return jsonify({'success': True, 'members': members})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ===== TREO NGÔN ROUTES =====
@app.route('/start_treongon', methods=['POST'])
def start_treongon():
    global current_session, spam_tasks
    try:
        data = request.get_json()
        box_id = data.get('box_id')
        box_name = data.get('box_name')
        content = data.get('content')
        delay = float(data.get('delay', 2))
        total = int(data.get('total', 1))
        tag_all = data.get('tag_all', True)
        tag_text = data.get('tag_text', '@All').strip()
        tag_color = data.get('tag_color', '#db342e')
        colored = data.get('colored', True)
        bold = data.get('bold', True)
        color = data.get('color', '#db342e')
        font_size = str(data.get('font_size', '15'))
        multi_color = data.get('multi_color', False)

        if not box_id or not content:
            return jsonify({'success': False, 'message': 'Thiếu thông tin!'})
        if not current_session or not current_session.get('cookies'):
            return jsonify({'success': False, 'message': 'Chưa đăng nhập!'})

        username = session.get('username', 'default')
        task_id = f"treongon_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        stop_flag = threading.Event()
        
        spam_tasks[task_id] = {
            'type': 'treongon',
            'status': 'running',
            'box_name': box_name,
            'box_id': box_id,
            'total': total,
            'delay': delay,
            'sent': 0,
            'progress': 0,
            'content': content,
            'tag_all': tag_all,
            'tag_text': tag_text,
            'tag_color': tag_color,
            'colored': colored,
            'bold': bold,
            'color': color,
            'font_size': font_size,
            'multi_color': multi_color,
            'imei': current_session.get('imei', ''),
            'stop_flag': stop_flag,
            'thread': None,
            'finished_at': None,
            'error': None,
            'username': username
        }
        
        save_tasks()

        thread = threading.Thread(
            target=run_treongon_task, 
            args=(task_id, current_session.get('imei', ''), current_session.get('cookies', {}))
        )
        thread.daemon = True
        thread.start()
        spam_tasks[task_id]['thread'] = thread

        tag_info = f"🏷 {tag_text}" if tag_all else "🔕 Không tag"
        return jsonify({
            'success': True, 
            'message': f'Đã bắt đầu treo vào {box_name} ({tag_info}) | Delay: {delay}s | {total} lần',
            'task_id': task_id
        })
    except Exception as e:
        logger.error(f"Lỗi start_treongon: {e}")
        return jsonify({'success': False, 'message': str(e)})

def run_treongon_task(task_id, imei, cookies):
    try:
        task = spam_tasks.get(task_id)
        if not task:
            return
        
        box_id = task['box_id']
        content = task['content']
        total = task['total']
        delay = task['delay']
        stop_flag = task.get('stop_flag')
        tag_all = task.get('tag_all', True)
        tag_text = task.get('tag_text', '@All')
        tag_color = task.get('tag_color', '#db342e')
        colored = task.get('colored', True)
        bold = task.get('bold', True)
        color = task.get('color', '#db342e')
        font_size = task.get('font_size', '15')
        multi_color = task.get('multi_color', False)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        sent = loop.run_until_complete(
            send_full_message_with_style_async(
                imei, cookies, box_id, content, 
                delay, total, stop_flag, 
                tag_all, tag_text, tag_color,
                colored, bold, color, font_size, multi_color
            )
        )
        loop.close()

        task['sent'] = sent
        task['progress'] = 100 if sent > 0 else 0
        task['finished_at'] = datetime.now().isoformat()
        
        if stop_flag and stop_flag.is_set():
            task['status'] = 'stopped'
        else:
            task['status'] = 'done' if sent > 0 else 'error'
        
        save_tasks()
        logger.info(f"Treo ngôn task {task_id} hoàn thành: {sent}/{total}")
        
    except Exception as e:
        logger.error(f"Lỗi run_treongon_task {task_id}: {e}")
        if task_id in spam_tasks:
            spam_tasks[task_id]['status'] = 'error'
            spam_tasks[task_id]['error'] = str(e)
            spam_tasks[task_id]['finished_at'] = datetime.now().isoformat()
            save_tasks()

# ===== NHAY TAG ROUTES =====
@app.route('/start_nhaytag', methods=['POST'])
def start_nhaytag():
    global current_session, nhaytag_tasks
    try:
        data = request.get_json()
        box_id = data.get('box_id')
        box_name = data.get('box_name')
        delay = float(data.get('delay', 5))
        user_ids = data.get('user_ids', [])
        content_text = data.get('content_text', '')

        if not box_id:
            return jsonify({'success': False, 'message': 'Thiếu box_id!'})
        if not user_ids:
            return jsonify({'success': False, 'message': 'Chọn ít nhất 1 thành viên!'})
        if not content_text:
            return jsonify({'success': False, 'message': 'Vui lòng upload file nội dung!'})
        if not current_session or not current_session.get('cookies'):
            return jsonify({'success': False, 'message': 'Chưa đăng nhập!'})

        username = session.get('username', 'default')
        task_id = f"nhaytag_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        stop_flag = threading.Event()
        
        nhaytag_tasks[task_id] = {
            'type': 'nhaytag',
            'status': 'running',
            'box_name': box_name,
            'box_id': box_id,
            'delay': delay,
            'user_ids': user_ids,
            'member_count': len(user_ids),
            'content_text': content_text,
            'imei': current_session.get('imei', ''),
            'stop_flag': stop_flag,
            'thread': None,
            'finished_at': None,
            'error': None,
            'username': username
        }
        
        save_tasks()

        thread = threading.Thread(
            target=run_nhaytag_task,
            args=(task_id, current_session.get('imei', ''), current_session.get('cookies', {}))
        )
        thread.daemon = True
        thread.start()
        nhaytag_tasks[task_id]['thread'] = thread

        return jsonify({
            'success': True,
            'message': f'Đã bắt đầu nhây tag vào {box_name} | Delay: {delay}s | Tag {len(user_ids)} người',
            'task_id': task_id
        })
    except Exception as e:
        logger.error(f"Lỗi start_nhaytag: {e}")
        return jsonify({'success': False, 'message': str(e)})

def run_nhaytag_task(task_id, imei, cookies):
    try:
        task = nhaytag_tasks.get(task_id)
        if not task:
            return
        
        box_id = task['box_id']
        delay = task['delay']
        user_ids = task['user_ids']
        content_text = task.get('content_text', '')
        stop_flag = task.get('stop_flag')
        
        error_queue = []
        worker_nhaytag(imei, cookies, box_id, delay, stop_flag, error_queue, user_ids, content_text)
        
        if error_queue and 'cookie_die' in error_queue:
            task['status'] = 'die'
        else:
            task['status'] = 'done'
        
        task['finished_at'] = datetime.now().isoformat()
        save_tasks()
        logger.info(f"Nhây tag task {task_id} hoàn thành")
        
    except Exception as e:
        logger.error(f"Lỗi run_nhaytag_task {task_id}: {e}")
        if task_id in nhaytag_tasks:
            nhaytag_tasks[task_id]['status'] = 'error'
            nhaytag_tasks[task_id]['error'] = str(e)
            nhaytag_tasks[task_id]['finished_at'] = datetime.now().isoformat()
            save_tasks()

# ===== TASK MANAGEMENT =====
@app.route('/stop_spam/<task_id>', methods=['POST'])
def stop_spam(task_id):
    global spam_tasks
    try:
        task = spam_tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': 'Không tìm thấy task'})
        
        username = session.get('username', 'default')
        if task.get('username') != username:
            return jsonify({'success': False, 'message': 'Bạn không có quyền dừng task này!'})
        
        stop_flag = task.get('stop_flag')
        if stop_flag:
            stop_flag.set()
        
        task['status'] = 'stopped'
        task['finished_at'] = datetime.now().isoformat()
        save_tasks()
        
        return jsonify({'success': True, 'message': f'Đã dừng task {task_id}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop_nhaytag/<task_id>', methods=['POST'])
def stop_nhaytag(task_id):
    global nhaytag_tasks
    try:
        task = nhaytag_tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': 'Không tìm thấy task'})
        
        username = session.get('username', 'default')
        if task.get('username') != username:
            return jsonify({'success': False, 'message': 'Bạn không có quyền dừng task này!'})
        
        stop_flag = task.get('stop_flag')
        if stop_flag:
            stop_flag.set()
        
        task['status'] = 'stopped'
        task['finished_at'] = datetime.now().isoformat()
        save_tasks()
        
        return jsonify({'success': True, 'message': f'Đã dừng nhây tag task {task_id}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop_all_tasks', methods=['POST'])
def stop_all_tasks():
    global spam_tasks, nhaytag_tasks
    load_tasks()
    try:
        stopped = 0
        username = session.get('username', 'default')
        
        for task_id, task in list(spam_tasks.items()):
            if task.get('username') == username and task.get('status') == 'running':
                stop_flag = task.get('stop_flag')
                if stop_flag:
                    stop_flag.set()
                task['status'] = 'stopped'
                task['finished_at'] = datetime.now().isoformat()
                stopped += 1
        
        for task_id, task in list(nhaytag_tasks.items()):
            if task.get('username') == username and task.get('status') == 'running':
                stop_flag = task.get('stop_flag')
                if stop_flag:
                    stop_flag.set()
                task['status'] = 'stopped'
                task['finished_at'] = datetime.now().isoformat()
                stopped += 1
        
        save_tasks()
        return jsonify({'success': True, 'message': f'Đã dừng {stopped} task của bạn'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/remove_task/<task_id>', methods=['DELETE'])
def remove_task(task_id):
    global spam_tasks, nhaytag_tasks
    try:
        username = session.get('username', 'default')
        
        if task_id in spam_tasks:
            if spam_tasks[task_id].get('username') != username:
                return jsonify({'success': False, 'message': 'Bạn không có quyền xóa task này!'})
            del spam_tasks[task_id]
        elif task_id in nhaytag_tasks:
            if nhaytag_tasks[task_id].get('username') != username:
                return jsonify({'success': False, 'message': 'Bạn không có quyền xóa task này!'})
            del nhaytag_tasks[task_id]
        else:
            return jsonify({'success': False, 'message': 'Không tìm thấy task'})
        save_tasks()
        return jsonify({'success': True, 'message': 'Đã xóa task'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/clear_finished_tasks', methods=['POST'])
def clear_finished_tasks():
    global spam_tasks, nhaytag_tasks
    load_tasks()
    try:
        finished = ['done', 'error', 'stopped']
        username = session.get('username', 'default')
        to_remove = []
        
        for tid, task in spam_tasks.items():
            if task.get('username') == username and task.get('status') in finished:
                to_remove.append(('spam', tid))
        
        for tid, task in nhaytag_tasks.items():
            if task.get('username') == username and task.get('status') in finished:
                to_remove.append(('nhaytag', tid))
        
        for type_, tid in to_remove:
            if type_ == 'spam':
                del spam_tasks[tid]
            else:
                del nhaytag_tasks[tid]
        
        save_tasks()
        return jsonify({'success': True, 'message': f'Đã xóa {len(to_remove)} task của bạn'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_all_tasks', methods=['GET'])
def get_all_tasks():
    global spam_tasks, nhaytag_tasks
    load_tasks()
    cleanup_dead_tasks()
    
    all_tasks = []
    username = session.get('username', 'default')
    
    for tid, task in spam_tasks.items():
        if task.get('username') != username:
            continue
            
        thread = task.get('thread')
        if task.get('status') == 'running' and thread and not thread.is_alive():
            task['status'] = 'error'
            task['finished_at'] = datetime.now().isoformat()
            save_tasks()
        
        all_tasks.append({
            'id': tid,
            'type': 'treongon',
            'box_name': task.get('box_name', ''),
            'total': task.get('total', 0),
            'sent': task.get('sent', 0),
            'delay': task.get('delay', 0),
            'progress': task.get('progress', 0),
            'status': task.get('status', 'unknown'),
            'error': task.get('error', None),
            'finished_at': task.get('finished_at', None),
            'tag_text': task.get('tag_text', ''),
            'member_count': 0
        })
    
    for tid, task in nhaytag_tasks.items():
        if task.get('username') != username:
            continue
            
        thread = task.get('thread')
        if task.get('status') == 'running' and thread and not thread.is_alive():
            task['status'] = 'error'
            task['finished_at'] = datetime.now().isoformat()
            save_tasks()
        
        all_tasks.append({
            'id': tid,
            'type': 'nhaytag',
            'box_name': task.get('box_name', ''),
            'total': 0,
            'sent': 0,
            'delay': task.get('delay', 0),
            'progress': 50,
            'status': task.get('status', 'unknown'),
            'error': task.get('error', None),
            'finished_at': task.get('finished_at', None),
            'tag_text': '',
            'member_count': task.get('member_count', 0)
        })
    
    all_tasks.sort(key=lambda x: (
        0 if x['status'] == 'running' else 1,
        x.get('finished_at', '') or ''
    ))
    
    return jsonify({'tasks': all_tasks})

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 WEB PNDK TOOL ĐA APP")
    print("📱 http://localhost:5000")
    print("🔐 Đăng nhập để sử dụng")
    print("✨ Hiệu ứng siêu đẹp")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
