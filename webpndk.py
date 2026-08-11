# zalo_send_message.py
import asyncio
import time
import random
import threading
from zlapi import ZaloAPI, ThreadType, Message, Mention, MultiMention, MultiMsgStyle, MessageStyle

async def send_full_message_with_style(imei, cookies, thread_id, content, delay, total, stop_flag, 
                                       tag_all=True, tag_text="@All", tag_color="#db342e",
                                       colored=True, bold=True, color="#db342e", font_size="15", multi_color=False):
    """Gửi tin nhắn với style và hỗ trợ dừng"""
    
    bot = ZaloAPI("api_key", "secret_key", imei, cookies)
    
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    if not lines:
        lines = ["Nội dung mặc định"]
    
    sent = 0
    i = 0
    line_index = 0
    
    # Tạo danh sách màu cho multi color
    colors = ["#db342e", "#f27806", "#f7b503", "#15a85f", "#1a73e8", "#9c27b0", "#00bcd4", "#ff5722"]
    
    while (total == 0 or sent < total) and not (stop_flag and stop_flag.is_set()):
        try:
            # Kiểm tra stop flag trước khi gửi
            if stop_flag and stop_flag.is_set():
                print(f"🛑 Dừng task do stop flag được set")
                break
            
            # Tạo tin nhắn với tag
            if tag_all:
                msg = tag_text + " " + lines[line_index]
            else:
                msg = lines[line_index]
            
            # Tạo mention cho tag
            mentions = []
            if tag_all:
                mention = Mention(uid="-1", length=len(tag_text), offset=0, auto_format=False)
                mentions.append(mention)
            
            # Tạo style
            styles = []
            offset = 0
            
            if tag_all:
                # Style cho tag
                styles.append(MessageStyle(
                    offset=0, 
                    length=len(tag_text), 
                    style="color", 
                    color=tag_color,
                    auto_format=False
                ))
                styles.append(MessageStyle(
                    offset=0, 
                    length=len(tag_text), 
                    style="bold", 
                    auto_format=False
                ))
                offset = len(tag_text) + 1
            
            # Style cho nội dung
            content_start = offset
            content_len = len(lines[line_index])
            
            if multi_color:
                # Mỗi dòng một màu riêng
                parts = lines[line_index].split()
                if parts:
                    color_index = line_index % len(colors)
                    for j, part in enumerate(parts):
                        part_offset = content_start + msg[content_start:].find(part)
                        if part_offset != -1:
                            styles.append(MessageStyle(
                                offset=part_offset,
                                length=len(part),
                                style="color",
                                color=colors[(color_index + j) % len(colors)],
                                auto_format=False
                            ))
                            if bold:
                                styles.append(MessageStyle(
                                    offset=part_offset,
                                    length=len(part),
                                    style="bold",
                                    auto_format=False
                                ))
            else:
                if colored:
                    styles.append(MessageStyle(
                        offset=content_start,
                        length=content_len,
                        style="color",
                        color=color,
                        auto_format=False
                    ))
                if bold:
                    styles.append(MessageStyle(
                        offset=content_start,
                        length=content_len,
                        style="bold",
                        auto_format=False
                    ))
            
            # Gửi tin nhắn
            bot.setTyping(thread_id, ThreadType.GROUP)
            await asyncio.sleep(1.5)
            
            if mentions:
                mention_obj = MultiMention(mentions)
                if styles:
                    style_obj = MultiMsgStyle(styles)
                    message = Message(text=msg, mention=mention_obj, style=style_obj)
                else:
                    message = Message(text=msg, mention=mention_obj)
            else:
                if styles:
                    style_obj = MultiMsgStyle(styles)
                    message = Message(text=msg, style=style_obj)
                else:
                    message = Message(text=msg)
            
            bot.send(message, thread_id=thread_id, thread_type=ThreadType.GROUP)
            
            sent += 1
            line_index += 1
            if line_index >= len(lines):
                line_index = 0
            
            # Kiểm tra stop flag trước khi sleep
            if stop_flag and stop_flag.is_set():
                print(f"🛑 Dừng task do stop flag được set sau khi gửi")
                break
            
            # Delay
            if delay > 0:
                for _ in range(int(delay)):
                    if stop_flag and stop_flag.is_set():
                        break
                    await asyncio.sleep(1)
                if delay % 1 > 0:
                    if not (stop_flag and stop_flag.is_set()):
                        await asyncio.sleep(delay % 1)
                    
        except Exception as e:
            print(f"Lỗi gửi tin nhắn: {e}")
            if "zpw_sek" in str(e) or "600" in str(e) or "cookie" in str(e).lower():
                break
            await asyncio.sleep(2)
    
    return sent
