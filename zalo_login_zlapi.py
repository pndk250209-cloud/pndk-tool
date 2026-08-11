# zalo_login_zlapi.py - Bản sửa lỗi
import json
import logging
import time
import traceback
import random
import asyncio
from typing import List, Dict
from zlapi import ZaloAPI, ThreadType
from zlapi.models import Message, Mention, MultiMention, MultiMsgStyle, MessageStyle

logger = logging.getLogger("zalo")
logger.setLevel(logging.INFO)

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
        logger.info("="*60)
        logger.info("🍪 Đang kiểm tra cookies...")
        logger.info(f"📱 IMEI: {imei}")
        cookies_dict = parse_cookies(cookies_string)
        bot = make_bot(imei, cookies_dict)
        info = bot.fetchAccountInfo()
        if info and hasattr(info, "profile") and info.profile:
            phone = info.profile.get("phoneNumber") or info.profile.get("phone") or "Không rõ"
            name = info.profile.get("displayName") or info.profile.get("zaloName") or "Không rõ"
            return {"success": True, "cookies": cookies_dict, "user_info": {"phone": phone, "displayName": name}, "imei": imei}
        else:
            return {"success": False, "message": "Cookies đã hết hạn!"}
    except Exception as e:
        logger.error(f"Lỗi login: {e}\n{traceback.format_exc()}")
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
            except:
                pass
        return result
    except Exception as e:
        logger.error(f"Lỗi fetch_groups: {e}\n{traceback.format_exc()}")
        return []

def send_full_message_with_style(imei: str, cookies_dict: dict, group_id: str, content: str, 
                                 delay_between_sends: float = 1.0, total=1, stop_flag=None, 
                                 tag_all=True, tag_text="@All", tag_color="#db342e",
                                 colored=True, bold=True, color="#db342e", font_size="15",
                                 multi_color=False) -> int:
    """Gửi toàn bộ nội dung với style: tag all, màu sắc, size chữ."""
    if not content.strip():
        return 0
    
    bot = make_bot(imei, cookies_dict)
    sent = 0
    
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    if not lines:
        return 0
    
    # Xử lý tag
    if tag_all and tag_text:
        message_text = tag_text + "\n" + "\n".join(lines)
        mention = Mention(uid="-1", length=len(tag_text), offset=0, auto_format=False)
        tag_offset = 0
        tag_length = len(tag_text)
    else:
        message_text = "\n".join(lines)
        mention = None
        tag_offset = 0
        tag_length = 0
    
    # Tạo style
    styles = []
    content_start = tag_length + 1 if tag_all and tag_text else 0
    
    # Style cho tag
    if tag_all and tag_text:
        styles.append(MessageStyle(offset=tag_offset, length=tag_length, style="bold", auto_format=False))
        styles.append(MessageStyle(offset=tag_offset, length=tag_length, style="color", color=tag_color, auto_format=False))
    
    # Nếu multi_color = True, mỗi dòng 1 màu
    if multi_color and len(lines) > 1:
        colors = ["#db342e", "#f27806", "#f7b503", "#15a85f", "#1a73e8", "#9c27b0", "#00bcd4", "#ff5722"]
        current_offset = content_start
        for i, line in enumerate(lines):
            if not line:
                current_offset += 1
                continue
            line_color = colors[i % len(colors)]
            styles.append(MessageStyle(offset=current_offset, length=len(line), style="color", color=line_color, auto_format=False))
            if bold:
                styles.append(MessageStyle(offset=current_offset, length=len(line), style="bold", auto_format=False))
            current_offset += len(line) + 1
    else:
        # Style đồng nhất
        if bold:
            styles.append(MessageStyle(offset=content_start, length=len(message_text) - content_start, style="bold", auto_format=False))
        if colored:
            styles.append(MessageStyle(offset=content_start, length=len(message_text) - content_start, style="color", color=color, auto_format=False))
        if font_size and font_size.isdigit():
            styles.append(MessageStyle(offset=content_start, length=len(message_text) - content_start, style="font", size=font_size, auto_format=False))
    
    multi_style = MultiMsgStyle(styles)
    
    # Gửi tin
    for i in range(total):
        if stop_flag and stop_flag.is_set():
            break
        try:
            if tag_all and tag_text:
                msg = Message(text=message_text, mention=mention, style=multi_style)
            else:
                msg = Message(text=message_text, style=multi_style)
            bot.send(msg, thread_id=group_id, thread_type=ThreadType.GROUP)
            sent += 1
            if i < total - 1:
                time.sleep(delay_between_sends)
        except Exception as e:
            logger.error(f"Lỗi gửi lần {i+1}: {e}")
            continue
    
    return sent

# ===== ASYNC =====
async def login_with_cookies_imei_async(cookies_string: str, imei: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, login_with_cookies_imei, cookies_string, imei)

async def get_box_chats_async(imei: str, cookies_dict: dict) -> List[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_box_chats, imei, cookies_dict)

async def send_full_message_with_style_async(imei: str, cookies_dict: dict, group_id: str, content: str, 
                                              delay_between_sends: float = 1.0, total=1, stop_flag=None, 
                                              tag_all=True, tag_text="@All", tag_color="#db342e",
                                              colored=True, bold=True, color="#db342e", font_size="15",
                                              multi_color=False) -> int:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_full_message_with_style, 
                                      imei, cookies_dict, group_id, content, 
                                      delay_between_sends, total, stop_flag, 
                                      tag_all, tag_text, tag_color,
                                      colored, bold, color, font_size, multi_color)