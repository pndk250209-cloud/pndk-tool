# zalo_login_zlapi.py
import json
import logging
import time
import traceback
from typing import List, Dict
from zlapi import ZaloAPI, ThreadType
from zlapi.models import Message

# Cấu hình logging để in ra terminal
logger = logging.getLogger("zalo")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

API_KEY = "api_key"
SECRET_KEY = "secret_key"

def make_bot(imei: str, cookies: dict) -> ZaloAPI:
    return ZaloAPI(API_KEY, SECRET_KEY, imei, cookies)

def parse_cookies(cookies_string: str) -> dict:
    cookies_dict = {}
    if ';' in cookies_string:
        for part in cookies_string.split(';'):
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                cookies_dict[key.strip()] = value.strip()
    else:
        try:
            cookies_dict = json.loads(cookies_string)
        except:
            cookies_dict = {}
    return cookies_dict

def login_with_cookies_imei(cookies_string: str, imei: str) -> dict:
    try:
        logger.info("=" * 60)
        logger.info("🍪 Đang kiểm tra cookies...")
        logger.info(f"📱 IMEI: {imei}")
        cookies_dict = parse_cookies(cookies_string)
        bot = make_bot(imei, cookies_dict)
        info = bot.fetchAccountInfo()
        if info and hasattr(info, "profile") and info.profile:
            phone = info.profile.get("phoneNumber") or info.profile.get("phone") or "Không rõ"
            name = info.profile.get("displayName") or info.profile.get("zaloName") or "Không rõ"
            logger.info(f"✅ Đăng nhập thành công: {name} ({phone})")
            return {"success": True, "cookies": cookies_dict, "user_info": {"phone": phone, "displayName": name}, "imei": imei}
        else:
            logger.error("❌ Cookies không hợp lệ!")
            return {"success": False, "message": "Cookies đã hết hạn!"}
    except Exception as e:
        logger.error(f"❌ Lỗi login: {e}\n{traceback.format_exc()}")
        return {"success": False, "message": str(e)}

def get_box_chats(imei: str, cookies_dict: dict) -> List[dict]:
    try:
        bot = make_bot(imei, cookies_dict)
        all_groups = bot.fetchAllGroups()
        result = []
        for gid in all_groups.gridVerMap.keys():
            try:
                info = bot.fetchGroupInfo(gid)
                name = info.gridInfoMap[gid]["name"]
                result.append({"id": gid, "name": name})
            except Exception as e:
                logger.warning(f"Không lấy được thông tin nhóm {gid}: {e}")
        logger.info(f"✅ Lấy được {len(result)} box chat")
        return result
    except Exception as e:
        logger.error(f"❌ Lỗi fetch_groups: {e}\n{traceback.format_exc()}")
        return []

def send_message_to_group(imei: str, cookies_dict: dict, group_id: str, message: str) -> bool:
    try:
        bot = make_bot(imei, cookies_dict)
        msg = Message(text=message)
        bot.send(msg, thread_id=group_id, thread_type=ThreadType.GROUP)
        logger.debug(f"✅ Đã gửi: {message[:30]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Lỗi gửi tin: {e}\n{traceback.format_exc()}")
        return False

def send_long_message(imei: str, cookies_dict: dict, group_id: str, content: str, delay_between_lines: float = 1.0, stop_flag=None) -> int:
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    if not lines:
        logger.warning("⚠️ Không có nội dung để gửi")
        return 0
    logger.info(f"📤 Bắt đầu gửi {len(lines)} dòng, delay {delay_between_line}s")
    bot = make_bot(imei, cookies_dict)
    sent = 0
    total = len(lines)
    for idx, line in enumerate(lines, 1):
        if stop_flag and stop_flag.is_set():
            logger.info(f"⏹️ Dừng task do stop_flag")
            break
        try:
            msg = Message(text=line)
            bot.send(msg, thread_id=group_id, thread_type=ThreadType.GROUP)
            sent += 1
            logger.info(f"📤 [{idx}/{total}] Đã gửi: {line[:30]}...")
            time.sleep(delay_between_lines)
        except Exception as e:
            logger.error(f"❌ Lỗi gửi dòng {idx}: {e}")
            continue
    logger.info(f"✅ Đã gửi {sent}/{total} dòng")
    return sent

# ===== Hàm async =====
import asyncio

async def login_with_cookies_imei_async(cookies_string: str, imei: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, login_with_cookies_imei, cookies_string, imei)

async def get_box_chats_async(imei: str, cookies_dict: dict) -> List[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_box_chats, imei, cookies_dict)

async def send_long_message_async(imei: str, cookies_dict: dict, group_id: str, content: str, delay_between_lines: float = 1.0, stop_flag=None) -> int:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_long_message, imei, cookies_dict, group_id, content, delay_between_lines, stop_flag)