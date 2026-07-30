import logging, os, asyncio, base64, json, re, cv2
import motor.motor_asyncio
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode
from config import *
from helper import *

logging.basicConfig(level=logging.INFO)


# ─────────────────────────── DB ───────────────────────────
class dbhandler:
    def __init__(self, uri, name):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self.client[name]
        self.users = self.db["users"]
        self.misc = self.db["misc"]
        self.header = self.db["header"]
        self.footer = self.db["footer"]
        self.watermark = self.db["watermark"]
        self.channels = self.db["channels"]
        self.scrapper_channels = self.db["scrapper_channels"]

    async def _upsert(self, col, fid, data): await col.update_one({"_id": fid}, {"$set": data}, upsert=True)
    async def _get(self, col, fid, key, default=""): d = await col.find_one({"_id": fid}); return d.get(key, default) if d else default

    async def set_global_session(self, s): await self._upsert(self.misc, "global_session", {"session": s})
    async def get_global_session(self): return await self._get(self.misc, "global_session", "session", None)
    async def set_session(self, uid, s): await self._upsert(self.users, uid, {"session": s})
    async def get_session(self, uid): return await self._get(self.users, uid, "session", None)
    async def get_header(self, uid): return await self._get(self.header, uid, "text", "")
    async def get_footer(self, uid): return await self._get(self.footer, uid, "text", "")
    async def set_header(self, uid, t): await self._upsert(self.header, uid, {"text": t})
    async def set_footer(self, uid, t): await self._upsert(self.footer, uid, {"text": t})
    async def set_scrapper(self, v): await self._upsert(self.misc, "scrapper", {"enabled": v})
    async def get_scrapper(self): return await self._get(self.misc, "scrapper", "enabled", False)
    async def set_watermark(self, uid, t): await self._upsert(self.watermark, uid, {"text": t})
    async def set_global_watermark(self, t): await self._upsert(self.watermark, "global", {"text": t})
    async def get_global_watermark(self): return await self._get(self.watermark, "global", "text", "")
    async def get_watermark(self, uid):
        d = await self.watermark.find_one({"_id": uid})
        if d: return d.get("text", "")
        g = await self.watermark.find_one({"_id": "global"})
        return g.get("text", "") if g else ""
    async def add_channel(self, cid): await self.channels.update_one({"_id": "list"}, {"$addToSet": {"data": cid}}, upsert=True)
    async def remove_channel(self, cid): await self.channels.update_one({"_id": "list"}, {"$pull": {"data": cid}})
    async def get_channels(self): return await self._get(self.channels, "list", "data", [])
    async def add_scrapper_channel(self, cid): await self.scrapper_channels.update_one({"_id": "list"}, {"$addToSet": {"data": cid}}, upsert=True)
    async def remove_scrapper_channel(self, cid): await self.scrapper_channels.update_one({"_id": "list"}, {"$pull": {"data": cid}})
    async def get_scrapper_channels(self): return await self._get(self.scrapper_channels, "list", "data", [])


db = dbhandler(DB_URI, DB_NAME)

MAX_RETRIES    = 3
RETRY_DELAY    = 3
CHANNEL_ID     = -1003849339538
CUSTOM_CAPTION = "<b>• <a href='https://t.me/tharkibhabhii'>Tʜᴀʀᴋɪ Bʜᴀʙʜɪ ⛩</a></b>"
TARGET_CHANNEL = -1003811146288

# ─────────────────────────── UTILS ───────────────────────────
def encode(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode()).decode().strip("=")

async def send_retry(func, *args, **kwargs):
    for _ in range(MAX_RETRIES):
        try: return await func(*args, **kwargs)
        except FloodWait as e: await asyncio.sleep(e.value + 1)
        except: await asyncio.sleep(RETRY_DELAY)
    return None

def msg_type(msg: Message):
    for t in ["photo", "video", "audio", "document", "animation", "text"]:
        if getattr(msg, t): return t
    return None

async def get_channel_name(client, cid):
    try:
        chat = await client.get_chat(cid)
        return f"{chat.title or 'Unknown'} (@{chat.username})" if chat.username else chat.title or "Unknown"
    except: return "❌ Invalid Channel"

# ─────────────────────────── WATERMARK DETECTION ───────────────────────────
def detect_watermark_position(image_path: str) -> dict:
    try:
        img = cv2.imread(image_path)
        if img is None: return None
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = [(x, y, cw, ch, cw*ch) for cnt in contours
                      for x, y, cw, ch in [cv2.boundingRect(cnt)]
                      if 500 < cw*ch < w*h*0.15 and cw > ch]
        if not candidates: return None
        x, y, cw, ch, _ = max(candidates, key=lambda c: c[4])
        return {"x_ratio": round((x + cw/2) / w, 3), "y_ratio": round((y + ch/2) / h, 3)}
    except: return None

async def detect_from_first_frame(video_path: str) -> dict:
    frame = "tmp_frame_detect.jpg"
    try:
        p = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", video_path, "-vframes", "1", "-q:v", "2", frame,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        await p.communicate()
        return detect_watermark_position(frame)
    except: return None
    finally:
        if os.path.exists(frame): os.remove(frame)


# ─────────────────────────── VIDEO METADATA ───────────────────────────
async def get_video_metadata(path: str):
    try:
        p = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format=duration", "-show_entries", "stream=width,height",
            "-of", "json", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await p.communicate()
        data = json.loads(stdout.decode().strip())
        duration = float(data.get("format", {}).get("duration", 0))
        s = data.get("streams", [{}])[0]
        return duration, int(s.get("width", 0)), int(s.get("height", 0))
    except: return 0, 0, 0

async def get_video_info(path: str) -> dict:
    dur, w, h = await get_video_metadata(path)
    return {"duration": int(dur), "width": w or 1280, "height": h or 720}


# ─────────────────────────── WATERMARK IMAGE ───────────────────────────
async def add_watermark_to_image(input_path: str, output_path: str, user_id=None) -> str:
    try:
        detected = detect_watermark_position(input_path)
        x_ratio  = detected["x_ratio"] if detected else 0.599
        y_ratio  = detected["y_ratio"] if detected else 0.760

        img = Image.open(input_path).convert("RGBA")
        w, h = img.size
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        text = await db.get_watermark(user_id) or "@TharkiBhabhii"
        size = max(22, int(min(w, h) * 0.055))

        try: font = ImageFont.truetype("GROBOLD.ttf", size)
        except: font = ImageFont.load_default()

        x, y   = int(w * x_ratio), int(h * y_ratio)
        border = max(1, int(size * 0.08))
        shadow = max(1, int(size * 0.06))

        draw.text((x + shadow, y + shadow), text, font=font, fill=(0, 0, 0, 120))
        for dx in [-border, 0, border]:
            for dy in [-border, 0, border]:
                if dx or dy: draw.text((x+dx, y+dy), text, font=font, fill=(0, 0, 0, 140))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 200))

        Image.alpha_composite(img, overlay).convert("RGB").save(output_path, "JPEG", quality=95)
        return output_path
    except Exception as e:
        logging.warning(f"Image watermark error: {e}")
        return None

# ─────────────────────────── WATERMARK VIDEO (FIXED) ───────────────────────────
async def add_watermark_to_video(input_path: str, output_path: str, user_id: int) -> str:
    try:
        watermark_text = await db.get_watermark(user_id) or "@TharkiBhabhii"

        safe_text = (
            watermark_text
            .replace("\\", r"\\\\")
            .replace("'",  r"\'")
            .replace(":",  r"\:")
            .replace(",",  r"\,")
        )

        font_path = "GROBOLD.ttf"
        duration, width, height = await get_video_metadata(input_path)

        if not duration or duration <= 0: duration = 20
        if not width or not height:       width, height = 1280, 720

        base_dim = min(width, height)
        size     = max(18, int(base_dim * 0.035))
        x_off    = max(8,  int(width   * 0.015))
        y_off    = max(8,  int(height  * 0.015))
        border   = max(1,  int(size    * 0.08))
        shadow   = max(1,  int(size    * 0.06))
        cycle    = max(20, duration)

        vf_filter = (
            # ✅ FIX 1: normalize color space/format AND scale to even dimensions
            # before drawtext — handles yuv422p, yuvj420p, nv12, etc.
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            f"format=yuv420p,"
            f"drawtext="
            f"fontfile={font_path}:"
            f"text='{safe_text}':"
            f"fontsize={size}:"
            f"fontcolor=white@0.78:"
            f"borderw={border}:"
            f"bordercolor=black@0.55:"
            f"shadowcolor=black@0.45:"
            f"shadowx={shadow}:"
            f"shadowy={shadow}:"
            f"x='if(lt(mod(t,{cycle}),{cycle/4}),{x_off},"
            f"if(lt(mod(t,{cycle}),{cycle/2}),w-tw-{x_off},"
            f"if(lt(mod(t,{cycle}),{(cycle*3)/4}),w-tw-{x_off},{x_off})))':"
            f"y='if(lt(mod(t,{cycle}),{cycle/4}),h-th-{y_off},"
            f"if(lt(mod(t,{cycle}),{cycle/2}),{y_off},"
            f"if(lt(mod(t,{cycle}),{(cycle*3)/4}),h-th-{y_off},{y_off})))'"
        )

        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", input_path,
            # ✅ FIX 2: explicit stream mapping — avoids missing/extra stream errors
            "-map", "0:v:0",        # first video stream only
            "-map", "0:a?",         # audio if present (? = optional, no error if missing)
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "28",
            "-pix_fmt", "yuv420p",  # output-level safety net
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "96k",
            # ✅ FIX 3: avoid muxer complaints on streams with no audio
            "-shortest",
            output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            process.kill()
            return None

        if process.returncode != 0:
            logging.warning(f"FFmpeg error: {stderr.decode().strip()}")
            return None

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return output_path

        return None

    except Exception as e:
        logging.warning(f"Watermarking failed: {e}")
        return None


# ─────────────────────────── THUMBNAIL (FIXED) ───────────────────────────
async def generate_thumbnail(video_path: str, output_path: str, user_id: int, time_position: int = 10) -> str:
    try:
        t = (await db.get_watermark(user_id) or "@TharkiBhabhii") \
            .replace("\\", r"\\\\").replace("'", r"\'").replace(":", r"\:").replace(",", r"\,")
        _, w, h = await get_video_metadata(video_path)
        w, h = w or 1280, h or 720
        s  = max(28, int(min(w, h) * 0.06))
        # ✅ FIX: same scale+format normalization before drawtext
        vf = (
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            f"format=yuv420p,"
            f"scale={min(w, 720)}:-2,"   # -2 keeps even height (avoid odd-dimension crash)
            f"drawtext=fontfile=GROBOLD.ttf:text='{t}':"
            f"fontsize={s}:fontcolor=white@0.92:borderw={max(2, s//12)}:bordercolor=black@0.9:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:x=(w-tw)/2:y=(h-th)/2"
        )
        p = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "panic",
            "-ss", str(time_position), "-i", video_path,
            "-vframes", "1", "-vf", vf, "-q:v", "1", "-pix_fmt", "yuv420p", output_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        try:    await asyncio.wait_for(p.communicate(), timeout=15)
        except: p.kill(); return None
        return output_path if p.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1024 else None
    except Exception as e:
        logging.warning(f"Thumbnail failed: {e}")
        return None

@Client.on_callback_query(filters.regex("^noop$"))
async def noop_cb(client, query):
    await query.answer("𝖯𝖱𝖮𝖤𝖱𝖱𝖮𝖱...", show_alert=False)

async def process_upload(client, acc, typ, msg, user_id=None, status_msg=None, current=1, total=1):
    temp = thumb = None

    def fmt_size(b):
        if b >= 1024 ** 3: return f"{b / 1024 ** 3:.1f} GB"
        if b >= 1024 ** 2: return f"{b / 1024 ** 2:.1f} MB"
        if b >= 1024:      return f"{b / 1024:.1f} KB"
        return f"{b} B"

    async def tg_edit(text, btn=None):
        if not status_msg: return
        try:
            await status_msg.edit_text(text, reply_markup=btn, parse_mode=enums.ParseMode.HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except:
            pass

    # ── Download progress ─────────────────────────────────────
    dl_last = [0.0]
    async def dl_progress(current_bytes, total_bytes):
        if not total_bytes: return
        now = asyncio.get_event_loop().time()
        if now - dl_last[0] < 5: return
        dl_last[0] = now
        pct  = int((current_bytes / total_bytes) * 100)
        done = fmt_size(current_bytes)
        size = fmt_size(total_bytes)
        text = (
            f"<b>🔽 𝖣𝖮𝖶𝖭𝖫𝖮𝖠𝖣𝖨𝖭𝖦... {pct}%\n📦 {current}/{total}</b>"
            if total > 1 else
            f"<b>🔽 𝖣𝖮𝖶𝖭𝖫𝖮𝖠𝖣𝖨𝖭𝖦... {pct}%</b>"
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton(f"💾 {done} / {size}", callback_data="noop")]])
        await tg_edit(text, btn)

    # ── Upload progress ───────────────────────────────────────
    ul_last = [0.0]
    async def ul_progress(current_bytes, total_bytes):
        if not total_bytes: return
        now = asyncio.get_event_loop().time()
        if now - ul_last[0] < 5: return
        ul_last[0] = now
        pct  = int((current_bytes / total_bytes) * 100)
        done = fmt_size(current_bytes)
        size = fmt_size(total_bytes)
        text = (
            f"<b>📤 𝖴𝖯𝖫𝖮𝖠𝖣𝖨𝖭𝖦... {pct}%\n📦 {current}/{total}</b>"
            if total > 1 else
            f"<b>📤 𝖴𝖯𝖫𝖮𝖠𝖣𝖨𝖭𝖦... {pct}%</b>"
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton(f"💾 {done} / {size}", callback_data="noop")]])
        await tg_edit(text, btn)

    try:
        if typ in ["photo", "video", "audio", "document", "animation"]:
            temp = await acc.download_media(
                getattr(msg, typ),
                progress=dl_progress if status_msg else None
            )

        if typ == "photo":
            # wm_path = f"{temp}_wm.jpg"
            # result  = await add_watermark_to_image(temp, wm_path, user_id)
            # watermarked = result if result and os.path.exists(result) and os.path.getsize(result) > 1024 else temp
            db_msg = await send_retry(
                client.send_photo, CHANNEL_ID, temp,
                caption=CUSTOM_CAPTION, parse_mode=enums.ParseMode.HTML,
                progress=ul_progress
            )

        elif typ == "video":
            thumb  = await generate_thumbnail(temp, f"{temp}_thumb.jpg", user_id)
            info   = await get_video_info(temp)

            await tg_edit(
                f"<b>📤 𝖴𝖯𝖫𝖮𝖠𝖣𝖨𝖭𝖦... </b>",
                InlineKeyboardMarkup([[InlineKeyboardButton(f"📦 {current}/{total}", callback_data="noop")]])
            )
            db_msg = await send_retry(
                client.send_video, CHANNEL_ID, temp,
                caption=CUSTOM_CAPTION,
                duration=info["duration"], width=info["width"], height=info["height"],
                thumb=thumb if thumb and os.path.exists(thumb) else None,
                parse_mode=enums.ParseMode.HTML,
                progress=ul_progress
            )

        elif typ == "audio":
            db_msg = await send_retry(
                client.send_audio, CHANNEL_ID, temp,
                caption=CUSTOM_CAPTION,
                duration=msg.audio.duration, performer=msg.audio.performer, title=msg.audio.title,
                progress=ul_progress
            )

        elif typ == "document":
            db_msg = await send_retry(
                client.send_document, CHANNEL_ID, temp,
                caption=CUSTOM_CAPTION,
                progress=ul_progress
            )

        elif typ == "animation":
            db_msg = await send_retry(
                client.send_animation, CHANNEL_ID, temp,
                caption=CUSTOM_CAPTION,
                progress=ul_progress
            )

        elif typ == "text":
            db_msg = await send_retry(
                client.send_message, CHANNEL_ID, msg.text,
                parse_mode=enums.ParseMode.HTML
            )

        else:
            return None

    except Exception as e:
        logging.exception(f"process_upload failed: {e}")
        return None
    finally:
        for f in {temp, thumb}:
            if f and f != temp and os.path.exists(f):
                try: os.remove(f)
                except: pass
        if temp and os.path.exists(temp):
            try: os.remove(temp)
            except: pass

    return db_msg


# ─────────────────────────── COMMANDS ───────────────────────────
@Client.on_message(filters.private & is_admin & filters.command("setglobalsession"))
async def set_global_session_cmd(client, message):
    msg = await client.ask(message.from_user.id, "<b>📝 Send USER session string for 24x7 listener:</b>", timeout=300)
    if msg.text.lower() in ["cancel", "/cancel"]: return await msg.reply("<b>Cancelled</b>")
    try:
        tmp = Client(":memory:", session_string=msg.text, api_id=API_ID, api_hash=API_HASH)
        await tmp.connect(); me = await tmp.get_me(); await tmp.disconnect()
        await db.set_global_session(msg.text)
        await msg.reply(f"<b>✅ Global session set!\n👤 {me.first_name} | 🆔 {me.id}</b>")
    except Exception as e: await msg.reply(f"<b>❌ Invalid session: {e}</b>")

@Client.on_message(filters.private & is_admin & filters.command('logout'))
async def logout(client, message):
    await db.set_session(message.from_user.id, None)
    await message.reply("<b>✅ ʟᴏɢᴏᴜᴛ sᴜᴄᴄᴇssғᴜʟʟʏ</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.private & is_admin & filters.command('setsession'))
async def set_session(client, message):
    if await db.get_session(message.from_user.id): return await message.reply("<b>ᴀʟʀᴇᴀᴅʏ ʟᴏɢɢᴇᴅ ɪɴ. /ʟᴏɢᴏᴜᴛ ғɪʀsᴛ</b>", parse_mode=ParseMode.HTML)
    msg = await client.ask(message.from_user.id, "<b>📝 sᴇɴᴅ sᴇssɪᴏɴ sᴛʀɪɴɢ</b>", timeout=300)
    if msg.text.lower() == "ᴄᴀɴᴄᴇʟʟᴇᴅ": return await msg.reply("<b>ᴄᴀɴᴄᴇʟʟᴇᴅ</b>", parse_mode=ParseMode.HTML)
    try:
        tmp = Client(":memory:", session_string=msg.text, api_id=API_ID, api_hash=API_HASH)
        await tmp.connect(); me = await tmp.get_me(); await tmp.disconnect()
        await db.set_session(message.from_user.id, msg.text)
        await msg.reply(f"<b>✅ sᴇssɪᴏɴ sᴇᴛ!\n👤 {me.first_name}\n🆔 {me.id}</b>", parse_mode=ParseMode.HTML)
    except Exception as e: await msg.reply(f"<b>❌ ɪɴᴠᴀʟɪᴅ: {e}</b>", parse_mode=ParseMode.HTML)


# ─────────────────────────── PANEL ───────────────────────────
async def panel_text_and_btn(client, status, channels):
    ch_lines = ""
    for cid in channels:
        try:
            chat = await client.get_chat(cid)
            uname = f" @{chat.username}" if chat.username else ""
            ch_lines += f"  • <b>{chat.title or 'Unknown'}</b>{uname}\n    <code>{cid}</code>\n"
        except: ch_lines += f"  • ❌ Unknown | <code>{cid}</code>\n"
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 ON" if status else "🔴 OFF", callback_data="scr_toggle")],
        [InlineKeyboardButton("➕ Add", callback_data="add_ch"), InlineKeyboardButton("➖ Remove", callback_data="rm_ch")],
        [InlineKeyboardButton("📊 Channels", callback_data="show_ch")]
    ])
    txt = (f"<b>⚙️ LISTENER PANEL</b>\n\n<b>Status:</b> {'🟢 ON' if status else '🔴 OFF'}\n"
           f"<b>Channels ({len(channels)}):</b>\n{ch_lines or '  <i>No channels added</i>'}")
    return txt, btn

@Client.on_message(filters.private & is_admin & filters.command("panel"))
async def panel(client, message):
    txt, btn = await panel_text_and_btn(client, await db.get_scrapper(), await db.get_scrapper_channels())
    await message.reply_text(txt, reply_markup=btn, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex("^(scr_toggle|add_ch|rm_ch|show_ch)$"))
async def cb(client, query):
    data = query.data
    if data == "scr_toggle":
        status = not await db.get_scrapper()
        await db.set_scrapper(status)
        txt, btn = await panel_text_and_btn(client, status, await db.get_scrapper_channels())
        await query.edit_message_text(txt, reply_markup=btn, parse_mode=enums.ParseMode.HTML)
        await query.answer("✅ Toggled!")

    elif data == "show_ch":
        channels = await db.get_scrapper_channels()
        if not channels: return await query.answer("No channels added!", show_alert=True)
        txt = "<b>📊 Active Channels:</b>\n\n"
        for cid in channels:
            try:
                chat = await client.get_chat(cid)
                uname = f" | @{chat.username}" if chat.username else ""
                try: count = f" | 👥 {await client.get_chat_members_count(cid):,}"
                except: count = ""
                txt += f"• <b>{chat.title or 'Channel'}</b>{uname}{count}\n  <code>{cid}</code>\n\n"
            except: txt += f"• ❌ Unknown\n  <code>{cid}</code>\n\n"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="scr_toggle")]]), parse_mode=enums.ParseMode.HTML)

    elif data == "add_ch":
        await query.answer()
        msg = await client.ask(query.from_user.id, "Send channel ID (e.g. <code>-1001234567890</code>) or /cancel:", timeout=300, parse_mode=enums.ParseMode.HTML)
        if msg.text.strip().lower() in ["/cancel", "cancel"]: return await msg.reply("<b>Cancelled</b>")
        try:
            cid = int(msg.text.strip())
            await db.add_scrapper_channel(cid)
            await msg.reply(f"<b>✅ Added: <code>{cid}</code></b>", parse_mode=enums.ParseMode.HTML)
        except ValueError: await msg.reply("<b>❌ Invalid ID</b>", parse_mode=enums.ParseMode.HTML)
        except Exception as e: await msg.reply(f"<b>❌ Failed: {e}</b>", parse_mode=enums.ParseMode.HTML)

    elif data == "rm_ch":
        await query.answer()
        channels = await db.get_scrapper_channels()
        if not channels: return await query.answer("No channels to remove!", show_alert=True)
        buttons = []
        for cid in channels:
            try: name = (await client.get_chat(cid)).title or str(cid)
            except: name = str(cid)
            buttons.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"del_ch:{cid}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="scr_toggle")])
        await query.edit_message_text("<b>Select channel to remove:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^del_ch:(-?\d+)$"))
async def del_ch_cb(client, query):
    cid = int(query.data.split(":")[1])
    await db.remove_scrapper_channel(cid)
    await query.answer("✅ Removed!", show_alert=True)
    channels = await db.get_scrapper_channels()
    if not channels:
        return await query.edit_message_text("<b>No scrapper channels left.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="scr_toggle")]]),
            parse_mode=enums.ParseMode.HTML)
    buttons = []
    for c in channels:
        try: name = (await client.get_chat(c)).title or str(c)
        except: name = str(c)
        buttons.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"del_ch:{c}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="scr_toggle")])
    await query.edit_message_text("<b>Select channel to remove:</b>", reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────── SCRAPPER CMD ───────────────────────────
@Client.on_message(filters.command("scrapper") & is_admin)
@Client.on_callback_query(filters.regex("^toggle_scrapper$|^set_channel$|^set_caption$"))
async def scrapper_cmd(client, update):
    is_cb = hasattr(update, "data")
    data  = getattr(update, "data", "")
    if data == "toggle_scrapper":
        await db.set_scrapper(not await db.get_scrapper())
    elif data == "set_channel":
        msg = await client.ask(update.from_user.id, "<b>sᴇɴᴅ ᴛᴀʀɢᴇᴛ ᴄʜᴀɴɴᴇʟ ɪᴅ:</b>", timeout=120)
        global CHANNEL_ID
        if msg.text.isdigit() or msg.text.startswith("-100"):
            CHANNEL_ID = int(msg.text); await msg.reply(f"<b>✅ ᴄʜᴀɴɴᴇʟ: {CHANNEL_ID}</b>")
        else: await msg.reply("<b>❌ ɪɴᴠᴀʟɪᴅ</b>")
    elif data == "set_caption":
        msg = await client.ask(update.from_user.id, "<b>sᴇɴᴅ ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ:</b>", timeout=300)
        global CUSTOM_CAPTION
        if msg.text.lower() != "ᴄᴀɴᴄᴇʟʟᴇᴅ": CUSTOM_CAPTION = msg.text; await msg.reply("<b>✅ ᴜᴘᴅᴀᴛᴇᴅ</b>")
        else: await msg.reply("<b>ᴄᴀɴᴄᴇʟʟᴇᴅ</b>")
    status = "🟢 <b>ᴇɴᴀʙʟᴇᴅ</b>" if await db.get_scrapper() else "🔴 <b>ᴅɪꜱᴀʙʟᴇᴅ</b>"
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ᴅɪꜱᴀʙʟᴇ" if status.startswith("🟢") else "🚀 ᴇɴᴀʙʟᴇ", callback_data="toggle_scrapper")],
        [InlineKeyboardButton("🛠 sᴇᴛ ᴄʜᴀɴɴᴇʟ", callback_data="set_channel"), InlineKeyboardButton("✏️ sᴇᴛ ᴄᴀᴘᴛɪᴏɴ", callback_data="set_caption")]
    ])
    txt = (f"<b>⚙️ sᴄʀᴀᴘᴘᴇʀ</b>\n\n🌐 sᴛᴀᴛᴜs: {status}\n"
           f"<b>📡 ᴄʜᴀɴɴᴇʟ:</b> {await get_channel_name(client, CHANNEL_ID)} | <code>{CHANNEL_ID}</code>\n"
           f"<b>ᴄᴀᴘᴛɪᴏɴ:</b> {CUSTOM_CAPTION}\n\n<b>» ʙʏ <a href='https://t.me/bhookibhabhi'>ᴍʀ ᴊʜᴀᴘʟᴜ 👑</a></b>")
    if is_cb: await update.message.edit_text(txt, parse_mode=enums.ParseMode.HTML, reply_markup=btn); await update.answer("✅")
    else: await update.reply_text(txt, parse_mode=enums.ParseMode.HTML, reply_markup=btn)

async def safe_edit(msg, text, tries=3):
    for _ in range(tries):
        try:
            return await msg.edit_text(text, parse_mode=enums.ParseMode.HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            if "topics" in str(e):
                await asyncio.sleep(0.5)
                continue
            return None
    return None

# ─────────────────────────── FETCH & UPLOAD ───────────────────────────
TOKEN_PHRASES = ["token is expired","token is invalid","ᴛᴏᴋᴇɴ ɪs ᴇxᴘɪʀᴇᴅ","ᴛᴏᴋᴇɴ ɪs ɪɴᴠᴀʟɪᴅ",
                 "ads token","ᴀᴅs ᴛᴏᴋᴇɴ","verify to access","ᴠᴇʀɪғʏ ᴛᴏ ᴀᴄᴄᴇss",
                 "token timeout","ᴛᴏᴋᴇɴ ᴛɪᴍᴇᴏᴜᴛ","passing 1 ad","ᴘᴀssɪɴɢ 𝟷 ᴀᴅ"]

def is_token_msg(text: str) -> bool:
    if not text: return False
    lower = text.lower()
    return any(p.lower() in lower for p in TOKEN_PHRASES)

@Client.on_message(filters.private & is_admin & ~filters.command(commands))
async def fetch_upload(client, message):
    if not await db.get_scrapper(): return
    text = message.text or message.caption or ""
    link = next((x for x in text.split() if "t.me/" in x or "telegram.me/" in x and "?start=" in x), None)
    if not link: return

    bot   = link.split("?start=")[0].split("/")[-1]
    start = link.split("?start=")[1]

    media, is_album = [], bool(message.media_group_id)
    if is_album:
        group = await client.get_media_group(message.chat.id, message.id)
        media = [InputMediaPhoto(m.photo.file_id) for m in group if m.photo]
    elif message.photo:
        media = [message.photo.file_id]

    ses = await db.get_session(message.from_user.id)
    if not ses:
        return await message.reply_text("<b>ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ /sᴇᴛsᴇssɪᴏɴ ғɪʀsᴛ</b>", parse_mode=enums.ParseMode.HTML)

    status = await message.reply_text("<b>⏳ 𝖢𝖮𝖬𝖬𝖠𝖭𝖣 𝖲𝖤𝖭𝖣𝖤𝖣...</b>", parse_mode=enums.ParseMode.HTML)

    acc = Client(f"restricted_{message.from_user.id}", session_string=ses, api_id=API_ID, api_hash=API_HASH)
    await acc.start()
    sent = await acc.send_message(bot, f"/start {start}")
    await asyncio.sleep(2.5)

    async def check_token(msgs):
        for m in msgs:
            t = m.text or m.caption or ""
            if not is_token_msg(t): continue
            await acc.stop()
            await status.edit_text(
                f"⚠️ <b>Token Verification Required!</b>\n\n<blockquote>{t}</blockquote>\n\n🔐 Verify manually then resend.",
                parse_mode=enums.ParseMode.HTML)
            return True
        return False

    if await check_token([m async for m in acc.get_chat_history(bot, 5) if m.date > sent.date]):
        return

    msgs, last_count, stable = [], 0, 0
    for _ in range(30):
        all_msgs = [m async for m in acc.get_chat_history(bot, 100) if m.date > sent.date]
        if await check_token(all_msgs): return
        media_msgs = [m for m in all_msgs if m.media]
        stable = stable + 1 if len(media_msgs) == last_count and len(media_msgs) > 0 else 0
        last_count, msgs = len(media_msgs), media_msgs
        if stable >= 3: break
        await asyncio.sleep(2)

    if not msgs:
        await acc.stop()
        return await status.edit_text("<b>❌ No media received from bot.</b>", parse_mode=enums.ParseMode.HTML)

    # ── Build final list ──────────────────────────────────────
    final, done = [], set()
    for m in msgs:
        if m.media_group_id:
            if m.media_group_id in done: continue
            grp = sorted([x for x in msgs if x.media_group_id == m.media_group_id], key=lambda x: x.id)
            cap_grp = next((x.caption for x in grp if x.caption), None)
            if cap_grp: grp[0].caption = cap_grp
            final += grp; done.add(m.media_group_id)
        else:
            final.append(m)

    # ── Upload with progress ──────────────────────────────────
    total = len(final)
    ids = []
    for i, m in enumerate(final, 1):
        typ = msg_type(m)
        if not typ:
            continue
        r = await process_upload(client, acc, typ, m, message.from_user.id,
                                 status_msg=status, current=i, total=total)
        if r:
            ids.append(r.id)

    if not ids:
        await acc.stop()
        return await status.edit_text("<b>❌ 𝖴𝖯𝖫𝖮𝖠𝖣 𝖥𝖠𝖨𝖫𝖤𝖣..</b>", parse_mode=enums.ParseMode.HTML)

    key      = f"get-{ids[0]}" if len(ids) == 1 else f"get-{ids[0]}-{ids[-1]}"
    new_link = f"https://t.me/{client.username}?start={encode(key)}"
    cap      = (f"<b>( डार्क 𝖣𝖾𝗌𝖎𝗋𝖾 ) : 𝐏ʀᴇᴍɪᴜᴍ 𝐒ᴛᴜꜰꜰ\n\n<blockquote>𝖧𝖾𝗋𝖾 𝗂𝗌 𝗒𝗈𝗎𝗋 𝖲𝗍𝗎𝖿𝖿 : ⬇️\n\n{new_link}</blockquote>\n\n"
              f"❐ NOTΕ : FORWARD & DOWNLOAD ΕNABLΕD ✅</b>")
    btn      = InlineKeyboardMarkup([[InlineKeyboardButton("𝗢𝗣𝗘𝗡 𝗟𝗜𝗡𝗞 🌺", url=new_link)]])
    fm       = msgs[0]

    SEND = {
        "video":     lambda: client.send_video(TARGET_CHANNEL, fm.video.file_id, caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn),
        "animation": lambda: client.send_animation(TARGET_CHANNEL, fm.animation.file_id, caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn),
        "document":  lambda: client.send_document(TARGET_CHANNEL, fm.document.file_id, caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn),
        "audio":     lambda: client.send_audio(TARGET_CHANNEL, fm.audio.file_id, caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn),
        "photo":     lambda: client.send_photo(TARGET_CHANNEL, fm.photo.file_id, caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn),
    }

    if media:
        if is_album:
            media[0].caption, media[0].parse_mode = cap, enums.ParseMode.HTML
            await status.edit_text("<b>✅ 𝖣𝖮𝖭𝖤 𝖬𝖤𝖣𝖨𝖠 𝖲𝖤𝖭𝖣𝖤𝖣..!</b>", parse_mode=enums.ParseMode.HTML)
            sm = await client.send_media_group(TARGET_CHANNEL, media)
            await client.send_message(TARGET_CHANNEL, cap, reply_to_message_id=sm[0].id, reply_markup=btn, parse_mode=enums.ParseMode.HTML)
        else:
            await client.send_photo(TARGET_CHANNEL, media[0], caption=cap, parse_mode=enums.ParseMode.HTML, reply_markup=btn)
    else:
        media_type = next((k for k in SEND if getattr(fm, k, None)), None)
        await (SEND[media_type]() if media_type else client.send_message(TARGET_CHANNEL, cap, reply_markup=btn, parse_mode=enums.ParseMode.HTML))

    await acc.stop()
    await status.edit_text("<b>✅ 𝖣𝖮𝖭𝖤 !</b>", parse_mode=enums.ParseMode.HTML)

# ─────────────────────────── LAYOUT ───────────────────────────
@Client.on_message(is_admin & filters.command('layout'))
async def layout_menu(client, message):
    header    = await db.get_header(message.from_user.id) or "❌ <i>ɴᴏᴛ sᴇᴛ</i>"
    footer    = await db.get_footer(message.from_user.id) or "❌ <i>ɴᴏᴛ sᴇᴛ</i>"
    watermark = await db.get_watermark(message.from_user.id) or "❌ <i>ɴᴏᴛ sᴇᴛ</i>"
    keyboard  = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ sᴇᴛ ʜᴇᴀᴅᴇʀ", callback_data="set_header"), InlineKeyboardButton("🛠 ᴇᴅɪᴛ ʜᴇᴀᴅᴇʀ", callback_data="edit_header"), InlineKeyboardButton("👀 ᴠɪᴇᴡ ʜᴇᴀᴅᴇʀ", callback_data="view_header")],
        [InlineKeyboardButton("✏️ sᴇᴛ ғᴏᴏᴛᴇʀ", callback_data="set_footer"), InlineKeyboardButton("🛠 ᴇᴅɪᴛ ғᴏᴏᴛᴇʀ", callback_data="edit_footer"), InlineKeyboardButton("👀 ᴠɪᴇᴡ ғᴏᴏᴛᴇʀ", callback_data="view_footer")],
        [InlineKeyboardButton("💧 sᴇᴛ ᴡᴀᴛᴇʀᴍᴀʀᴋ", callback_data="set_watermark"), InlineKeyboardButton("🛠 ᴇᴅɪᴛ ᴡᴀᴛᴇʀᴍᴀʀᴋ", callback_data="edit_watermark"), InlineKeyboardButton("👀 ᴠɪᴇᴡ ᴡᴀᴛᴇʀᴍᴀʀᴋ", callback_data="view_watermark")],
        [InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʜᴇᴀᴅᴇʀ", callback_data="remove_header"), InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ғᴏᴏᴛᴇʀ", callback_data="remove_footer"), InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ᴡᴀᴛᴇʀᴍᴀʀᴋ", callback_data="remove_watermark")]
    ])
    await message.reply_text(
        f"🔝 <b>ʜᴇᴀᴅᴇʀ:</b>\n{header}\n\n🔚 <b>ғᴏᴏᴛᴇʀ:</b>\n{footer}\n\n💧 <b>ᴡᴀᴛᴇʀᴍᴀʀᴋ:</b>\n{watermark}",
        reply_markup=keyboard, parse_mode=ParseMode.HTML)

async def handle_set_edit(client, cq, field, edit=False):
    current = await getattr(db, f"get_{field}")(cq.from_user.id) if edit else None
    prompt  = f"🛠 ᴄᴜʀʀᴇɴᴛ {field}:\n\n{current}\n\nsᴇɴᴅ ᴜᴘᴅᴀᴛᴇᴅ ᴛᴇxᴛ." if edit else f"📝 sᴇɴᴅ ɴᴇᴡ {field}:"
    await cq.message.edit_text(prompt, parse_mode=ParseMode.HTML)
    try:
        msg = await client.listen(cq.from_user.id, timeout=300)
        if msg.text.lower() == "/cancel": return await msg.reply_text("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ")
        await getattr(db, f"set_{field}")(cq.from_user.id, msg.text)
        await msg.reply_text(f"✅ {field} ᴜᴘᴅᴀᴛᴇᴅ\n\n{msg.text}", parse_mode=ParseMode.HTML)
    except Exception as e: await client.send_message(cq.from_user.id, f"❌ ᴇʀʀᴏʀ: {e}")

async def handle_view(client, cq, field):
    text = await getattr(db, f"get_{field}")(cq.from_user.id)
    if not text: return await cq.message.edit_text(f"❌ ɴᴏ {field} sᴇᴛ")
    await cq.message.edit_text(f"🔹 {field}:\n\n{text}\n\n<b>ʟᴇɴɢᴛʜ:</b> {len(text)} ᴄʜᴀʀs",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ ʙᴀᴄᴋ", callback_data="layout_menu")]]))

async def handle_remove(client, cq, field):
    await cq.message.edit_text(f"⚠️ ʀᴇᴍᴏᴠᴇ {field}?", parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ʏᴇs", callback_data=f"confirm_remove_{field}")],
            [InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="layout_menu")]]))

async def handle_confirm_remove(client, cq, field):
    success = await getattr(db, f"deactivate_{field}")(cq.from_user.id)
    await cq.message.edit_text(f"✅ {field} ʀᴇᴍᴏᴠᴇᴅ" if success else "❌ ғᴀɪʟᴇᴅ",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ ʙᴀᴄᴋ", callback_data="layout_menu")]]))

@Client.on_callback_query(filters.regex("^(set|edit|view|remove|confirm_remove)_(header|footer|watermark)$|layout_menu"))
async def callback_handler(client, cq):
    if cq.data == "layout_menu": return await layout_menu(client, cq.message)
    parts = cq.data.split("_", 1)
    if len(parts) == 2:
        action, field = parts
        if action in ["set", "edit"]: await handle_set_edit(client, cq, field, edit=(action == "edit"))
        elif action == "view": await handle_view(client, cq, field)
        elif action == "remove": await handle_remove(client, cq, field)
        elif action == "confirm_remove": await handle_confirm_remove(client, cq, field) 
