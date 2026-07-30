from pyrogram import Client, filters
from database import *
import asyncio, random, time
from datetime import datetime, timedelta
from pyrogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Message
from plugins.FORMAT import *
from helper import *
from config import *
import contextlib
from bot import START_TIME
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.types import CallbackQuery
import psutil
from bson import ObjectId
from datetime import datetime, timedelta
import pytz

IST=pytz.timezone("Asia/Kolkata")
HELP_IMG = "https://graph.org//file/10f310dd6a7cb56ad7c0b.jpg"

from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("set"))
async def set_profile_pic(client: Client, message: Message):
    # check if replied
    if not message.reply_to_message:
        return await message.reply("Reply to a photo with /set")

    replied = message.reply_to_message

    # check if it's a photo
    if not replied.photo:
        return await message.reply("Please reply to a photo.")

    try:
        # download the photo
        file_path = await replied.download()

        # set as profile photo
        await client.set_profile_photo(photo=file_path)

        await message.reply("✅ Profile photo updated!")

    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@Client.on_message(filters.command("start") & subscribed)
async def start(c, m):
    u = m.from_user.id
    await add_user(u)

    if len(m.command) > 1:
        p = m.command[1]
        if p.startswith("bhookibhabhi_"): return await send_bhooki(c, m, p, DB_ID)
        if p.startswith("premium"):return await handle_premium(c, m, p)
        if p.startswith("verify_"):       return await handle_token_verification(c, m)
        if p.startswith("file_"):return await handle_file_verification(c, m, p)
        if p.startswith("refer"): return await referrals(c, m)
        if p.startswith("ref_"):
            msg = await handle_referral(u, p)
            if msg: return await m.reply_text(msg)
        if p.startswith("claim_"):
            cld = p.split("_", 1)[1]
            return await handle_premium_claim(c, m, cld)
        return await copy_msg(c, m, p)

    await c.send_web_page(
        m.chat.id, random.choice(PICS),
        START_MSG.format(mention=m.from_user.mention),
        large_media=True, invert_media=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("• ᴀʙᴏᴜᴛ", callback_data="about_bot"),
            InlineKeyboardButton("sᴇᴛᴛɪɴɢs •", callback_data="settings")
        ]]),
        message_effect_id=5104841245755180586
    )
    try: await m.delete()
    except: pass

@Client.on_message(filters.command("start") & is_ban & filters.private)
async def banned_start(_, m):
    await m.reply_text(
        "<b>❌ ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ғʀᴏᴍ ᴜsɪɴɢ ᴛʜɪs ʙᴏᴛ.</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛠️ ᴄᴏɴᴛᴀᴄᴛ ᴅᴇᴠ", url="https://t.me/DumpAdminBot")
        ]]),
        message_effect_id=5046589136895476101, #💩
        parse_mode=ParseMode.HTML
    )

async def handle_premium_claim(_,m,c):
    u=m.from_user.id; d=await claim_links.find_one({"_id":ObjectId(c)})
    if not d: return await m.reply("<b>❌ ɪɴᴠᴀʟɪᴅ / ᴇxᴘɪʀᴇᴅ</b>")
    cu=d.get("claimed_users",[])
    if u in cu: return await m.reply("<b>🚫 ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ</b>")
    if len(cu)>=d.get("max_claims",10): return await m.reply("<b>⏳ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>")

    dur=d.get("duration",604800); now=datetime.now(IST)
    ud=await user_data.find_one({"_id":u})
    base=datetime.fromtimestamp(ud["premium_expiry"],IST) if ud and ud.get("premium_expiry",0)>now.timestamp() else now
    exp=base+timedelta(seconds=dur)

    await user_data.update_one({"_id":u},{"$set":{"premium":1,"premium_expiry":int(exp.timestamp())}},upsert=True)
    await claim_links.update_one({"_id":ObjectId(c)},{"$addToSet":{"claimed_users":u}})

    await m.reply(f"<b>✅ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴛɪᴠᴀᴛᴇᴅ</b>\n⏳ {dur//86400} ᴅᴀʏs\n📅 <b>{exp:%d-%m-%Y %I:%M %p}</b>",parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("start") & is_ban & filters.private)
async def banned_start(_, m):
    await m.reply_text(
        "<b>❌ ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ғʀᴏᴍ ᴜsɪɴɢ ᴛʜɪs ʙᴏᴛ.</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛠️ ᴄᴏɴᴛᴀᴄᴛ ᴅᴇᴠ", url="https://t.me/DumpAdminBot")
        ]]),
        message_effect_id=5046589136895476101, #💩
        parse_mode=ParseMode.HTML
    )

async def handle_premium(c, m, p):
    user_id = m.from_user.id
    pm_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("• ɢᴇᴛ ᴘʀᴇᴍɪᴜᴍ •", callback_data="buy_premium")
    ]])

    text = (
        f"𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗣𝗟𝗔𝗡𝗦\n\n"
        f"<b>Wᴇʟᴄᴏᴍᴇ Tᴏ Pʀᴇᴍɪᴜᴍ Sᴇᴄᴛɪᴏɴ Exᴘᴇʀɪɴᴇᴄ ᴛʜᴇ ғᴀsᴛᴇʀsᴛ ғɪᴇʟ ᴅᴇʟɪᴠᴇʀʏ</b>\n\n"
    )
    await m.reply_text(text, reply_markup=pm_btn, parse_mode=ParseMode.HTML)
    # except Exception as e:

# ---------------- Stats Command ----------------
@Client.on_message(filters.command("stats") & is_admin)
async def stats(_, m):
    await send_stats(_, m)

# ---------------- Refresh Callback ----------------
@Client.on_callback_query(filters.regex("refresh_stats"))
async def refresh_stats(_, cq: CallbackQuery):
    await cq.answer()  # remove “loading” popup
    await cq.message.edit_text("⏳ <b>ʀᴇғʀᴇsʜɪɴɢ...</b>")
    await send_stats(_, cq.message, edit=True)

# ---------------- Helper to Send Stats ----------------
async def send_stats(client, message, edit=False):
    now = datetime.utcnow()
    total_users, total_admins = await count_users(), await count_admins()
    ten_hours_ago = now - timedelta(hours=10)
    new_users = await user_data.count_documents({
        "joined": {"$gte": ten_hours_ago}
    })

    start = time.time()
    await client.get_me()
    ping = round((time.time() - start) * 1000)

    uptime_sec = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime = f"{days}d {hours}h {minutes}m {seconds}s" if days else f"{hours}h {minutes}m {seconds}s"

    # CPU & Memory usage
    cpu_usage = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()

    # Disk usage
    disk = psutil.disk_usage("/")  
    total_gb = disk.total / (1024**3)
    used_gb = disk.used / (1024**3)
    free_gb = disk.free / (1024**3)
    percent_used = disk.percent

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 ʀᴇꜰʀᴇꜱʜ", callback_data="refresh_stats")]
    ])

    text = (
        f"<blockquote>📊 <b>ʙᴏᴛ ꜱᴛᴀᴛꜱ</b></blockquote>\n\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:</b> <code>{total_users}</code>\n"
        f"🆕 <b>ɴᴇᴡ 10ʜ ᴜꜱᴇʀꜱ:</b> <code>{new_users}</code>\n"
        f"👮 <b>ᴀᴅᴍɪɴꜱ:</b> <code>{total_admins}</code>\n"
        f"🏓 <b>ᴘɪɴɢ:</b> <code>{ping} ms</code>\n"
        f"💾 <b>ᴄᴘᴜ ᴜꜱᴀɢᴇ:</b> <code>{cpu_usage}%</code>\n"
        f"🧠 <b>ᴍᴇᴍ ᴜꜱᴀɢᴇ:</b> <code>{mem.percent}%</code>\n"
        f"📂 <b>ꜱᴛᴏʀᴀɢᴇ:</b> <code>{used_gb:.2f}GB / {total_gb:.2f}GB</code> "
        f"(<code>{percent_used}%</code>)\n"
        f"⬇ <b>ғʀᴇᴇ:</b> <code>{free_gb:.2f}GB</code>\n"
        f"⏱ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{uptime}</code>"
    )

    if edit:await message.edit_text(text, reply_markup=kb)
    else:await message.reply_text(text, reply_markup=kb)


@Client.on_message(filters.command("help"))
async def help_command(client, message):
    caption = (
        "<b>📚 ʜᴇʟᴘ ᴍᴇɴᴜ</b>\n\n"
        "⚡ ᴛʜɪs ʙᴏᴛ ɪs ᴀ sɪᴍᴘʟᴇ ғɪʟᴇsᴛᴏʀᴇ ʙᴏᴛ.\n"
        "• ɪᴛ ᴄᴀɴ sᴇɴᴅ ᴍᴇᴅɪᴀ ᴀᴛᴛᴀᴄʜᴇᴅ ᴛᴏ ᴀ sᴘᴇᴄɪᴀʟ ʟɪɴᴋ.\n"
        "• ᴊᴜsᴛ ᴘᴀsᴛᴇ ᴛʜᴇ sᴘᴇᴄɪᴀʟ ʟɪɴᴋ ʏᴏᴜ ɢᴏᴛ, ᴀɴᴅ ʙᴏᴛ ᴡɪʟʟ sᴇɴᴅ ʏᴏᴜ ᴛʜᴇ ᴍᴇᴅɪᴀ.\n\n"
        "🔗 <b>ᴛɪᴘ:</b> ᴏɴʟʏ ᴜsᴇ ᴠᴀʟɪᴅ sᴘᴇᴄɪᴀʟ ʟɪɴᴋs ᴛᴏ ɢᴇᴛ ғɪʟᴇs."
    )

    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("• 📖 ᴛᴜᴛᴏʀɪᴀʟ •", url="https://t.me/TomXRobot?start=Z2V0LTc2MDkwNjU2MTIzMTA4NzY")],
        [InlineKeyboardButton("• ℹ️ ʜᴏᴡ ɪᴛ ᴡᴏʀᴋs •", url="https://t.me/TomXRobot/123")]  # update with your actual info link
    ])

    await message.reply_photo(
        HELP_IMG,
        caption=caption,
        reply_markup=inline_kb,
        parse_mode=ParseMode.HTML
    )
    # Send persistent reply keyboard after help
    # await message.reply_text("<b>👇 𝙌𝙪𝙞𝙘𝙠 𝘼𝙘𝙩𝙞𝙤𝙣𝙨 :</b>\n𝘾𝙝𝙤𝙤𝙨𝙚 𝙑𝙄𝘿𝙀𝙊 𝙤𝙧 𝙋𝙃𝙊𝙏𝙊 𝙗𝙚𝙡𝙤𝙬 ⬇️",reply_markup=REPLY_KEYBOARD)

@Client.on_message(filters.command("refer") | filters.regex("⚡ REFER"))
async def referrals(client, message):
    user_id = message.from_user.id
    user = await user_data.find_one({"_id": user_id}) or {}

    referrals_count = user.get("referrals", 0)
    premium_expiry = user.get("premium_expiry", 0)

    # Check if referrals are enabled
    refer_enabled = await is_refer_enabled()
    ref_link = f"https://t.me/{client.username}?start=ref_{user_id}" if refer_enabled else None

    # Format premium expiry status
    if premium_expiry > int(time.time()):
        expiry_text = "ᴀᴄᴛɪᴠᴇ ᴜɴᴛɪʟ " + time.strftime('%d %b %Y %H:%M', time.localtime(premium_expiry))
    else:
        expiry_text = "ɴᴏᴛ ᴀᴄᴛɪᴠᴇ"

    # Main referral text
    text = (
        f"<b>🎯 ʀᴇғᴇʀ sᴛᴀᴛs:</b>\n\n"
        f"• ʀᴇғᴇʀʀᴀʟs: <code>{referrals_count}</code>\n"
        f"• ʀᴇғᴇʀ ʀᴇᴡᴀʀᴅ: <code>{REFERRAL_REWARD_DAYS}</code> ᴅᴀʏ ᴘʀᴇᴍɪᴜᴍ\n"
        f"• ᴘʀᴇᴍɪᴜᴍ ᴇxᴘɪʀʏ: <code>{expiry_text}</code>\n"
    )

    reply_markup = None
    if refer_enabled:
        share_url = f"https://telegram.me/share/url?url={ref_link}"
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("• sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ •", url=share_url)]
        ])
        text += (
            f"\n<b>• ʏᴏᴜʀ ʀᴇғᴇʀ ʟɪɴᴋ:\n<code>{ref_link}</code>\n\n"
            f"<blockquote>sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ ᴛᴏ ɢᴇᴛ {REFERRAL_REWARD_DAYS} ᴅᴀʏ ᴘʀᴇᴍɪᴜᴍ ᴀɴᴅ ʏᴏᴜ ᴄᴀɴ ᴇᴀʀɴ ᴜɴʟɪᴍɪᴛᴇᴅ ᴘʀᴇᴍɪᴜᴍ ʙʏ sʜᴀʀɪɴɢ ᴛᴏ ғʀɪᴇɴᴅs</blockquote></b>"
        )

    await message.reply_photo(
        photo="https://t3.ftcdn.net/jpg/16/98/93/96/360_F_1698939625_i7Am20JWPYe0Ltrywpx6vF2bkqD7MtcS.jpg",
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

@Client.on_message(filters.command("id"))
async def id_cmd(client: Client, m: Message):
    try:
        # Short lambda helpers
        ml = lambda cid, mid: f"https://t.me/c/{str(cid)[4:]}/{mid}" if str(cid).startswith("-100") else f"https://t.me/{cid}/{mid}"
        ul = lambda uid: f"tg://user?id={uid}"
        cl = lambda c: f"https://t.me/{c.username}" if c.username else ml(c.id, m.id)

        # Determine target user (replied user or self or @username)
        target = m.reply_to_message.from_user if m.reply_to_message and m.reply_to_message.from_user else m.from_user

        if len(m.command) > 1:  # /id @username
            try:target = await client.get_users(m.command[1])
            except:return await m.reply("<b>❌ Iɴᴠᴀʟɪᴅ ᴜsᴇʀɴᴀᴍᴇ ᴏʀ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.</b>", parse_mode=ParseMode.HTML)

        # Main message data
        text = (
            f'<a href="{ml(m.chat.id, m.id)}"><b>ᴍᴇssᴀɢᴇ ɪᴅ:</b></a> <code>{m.id}</code>\n'
            f'<a href="{ul(target.id)}"><b>ᴛᴀʀɢᴇᴛ ᴜsᴇʀ ɪᴅ:</b></a> <code>{target.id}</code>\n'
            f'<a href="{cl(m.chat)}"><b>ᴄʜᴀᴛ ɪᴅ:</b></a> <code>{m.chat.id}</code>'
        )

        # If replying to a message, include replied message/user info
        if m.reply_to_message:
            r = m.reply_to_message
            replied_msg_link = f'<a href="{ml(m.chat.id, r.id)}"><b>ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ɪᴅ:</b></a> <code>{r.id}</code>'
            if r.from_user:replied_user_info = f'<a href="{ul(r.from_user.id)}"><b>ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ ɪᴅ:</b></a> <code>{r.from_user.id}</code>'
            else:replied_user_info = '<b>ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ ɪᴅ:</b> <code>Unknown</code>'

            text += f"\n\n{replied_msg_link}\n{replied_user_info}"

        await m.reply(text, parse_mode=ParseMode.HTML)

    except Exception as e:await m.reply(f"<b>❌ Eʀʀᴏʀ:</b> <code>{e}</code>", parse_mode=ParseMode.HTML)

chat_data_cache = {}

@Client.on_message(filters.command("start") & filters.private)
async def not_joined(client: Client, message: Message):
    temp = await message.reply("<i><b>» ᴡᴀɪᴛ ᴀ sᴇᴄᴏɴᴅ</b></i>")
    user_id, mention = message.from_user.id, message.from_user.mention
    req_fsub = await get_request_forcesub()
    buttons, count = [], 0

    try:
        for total, chat_id in enumerate(await get_all_channels() or [], 1):
            if await is_userJoin(client, user_id, chat_id): continue

            try:
                data = chat_data_cache.get(chat_id) or await client.get_chat(chat_id)
                chat_data_cache[chat_id] = data
                cname = data.title or "Channel"

                if req_fsub and not data.username:
                    link = await get_stored_reqLink(chat_id)
                    await add_reqChannel(chat_id)
                    if not link:
                        invite = await client.create_chat_invite_link(chat_id, creates_join_request=True)
                        link = invite.invite_link
                        await store_reqLink(chat_id, link)
                else:
                    link = data.invite_link

                buttons.append([InlineKeyboardButton(cname, url=link)])
                count += 1
                with contextlib.suppress(Exception):
                    await temp.edit(f"<b>{'💀 ' * count}</b>")

            except: continue

        buttons.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ", url=f"https://t.me/{client.username}?start={message.command[1] if len(message.command) > 1 else 'start'}")])

        await temp.edit_text(
            FORCE_MSG.format(mention=mention),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        with contextlib.suppress(Exception): await message.delete()

    except Exception as e:
        error_msg = f"<b>Eʀʀᴏʀ Cᴏɴᴛᴀᴄᴛ Dᴇᴠᴇʟᴏᴘᴇʀ @ProError</b>\n<blockquote>{e}</blockquote>"
        with contextlib.suppress(Exception): await temp.edit_text(error_msg)

@Client.on_message(filters.command("reqfsub") & is_admin)
async def reqfsub_toggle(client: Client, message: Message):
    status = await get_request_forcesub()
    state = "✅ ᴇɴᴀʙʟᴇᴅ" if status else "❌ ᴅɪsᴀʙʟᴇᴅ"
    btn_text = "❌ ᴅɪsᴀʙʟᴇ" if status else "✅ ᴇɴᴀʙʟᴇ"

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(btn_text, callback_data="toggle_fsub")
    ]])

    await message.reply(
        f"<b>📡 ʀᴇǫᴜᴇsᴛ ғᴏʀᴄᴇ sᴜʙsᴄʀɪʙᴇ ᴍᴏᴅᴇ</b>\n\nCurrent status: <b>{state}</b>",
        reply_markup=buttons
    )

# from pyrogram.types import BotCommand

# @Client.on_message(filters.command("set"))
# async def set_commands(client, message):
#     commands = [
#         # User commands first (small caps style descriptions)
#         BotCommand("start", "sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ⚡"),
#         BotCommand("help", "🆘 sʜᴏᴡ ʜᴇʟᴘ ᴀɴᴅ ᴜsᴀɢᴇ ɢᴜɪᴅᴇ"),
#         BotCommand("myplan", "ᴄʜᴇᴄᴋ ᴘʀᴇᴍɪᴜᴍ sᴛᴀᴛᴜs ⚡"),
#         BotCommand("refer", "ʀᴇꜰᴇʀ ᴀ ғʀɪᴇɴᴅ ⚡"),
#         BotCommand("id","ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴜsᴇʀ ɪᴅ ⚡"),

#         # Admin commands (small caps + admin only note)
#         BotCommand("genlink","ɢᴇɴᴇʀᴀᴛᴇ ᴀ ʟɪɴᴋ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("batch","ɢᴇɴᴇʀᴀᴛᴇ ᴀ ʙᴀᴛᴄʜ ʟɪɴᴋ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("scrapper","sᴄʀᴀᴘ ᴍᴇᴅɪᴀ ғʀᴏᴍ ᴀ ʟɪɴᴋ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("layout", "sᴇᴛ sᴄʀᴀᴘ ᴍᴇᴅɪᴀ ʟᴀʏᴏᴜᴛ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("waiting_timer","ᴛᴏᴏɢʟᴇ ᴛɪᴍᴇʀ ғᴏʀ ғʀᴇᴇ ᴜsᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("set_free_limit", "sᴇᴛ ᴍᴀx ʀᴀɴᴅᴏᴍ ᴍᴇᴅɪᴀ ʟɪᴍɪᴛ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("reset_free_count", "ʀᴇsᴇᴛ ᴜsᴇʀs' ғʀᴇᴇ ᴍᴇᴅɪᴀ ᴄᴏᴜɴᴛ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("update", "ɢɪᴛ ᴘᴜʟʟ ʟᴀᴛᴇsᴛ ᴜᴘᴅᴀᴛᴇ ( ᴅᴇᴠ ᴏɴʟʏ 🛠️ )"),
#         BotCommand("verification", "ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ sᴛᴀᴛs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("admin", "ᴏᴘᴇɴ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("free", "ᴛᴏɢɢʟᴇ ꜰʀᴇᴇ ᴍᴏᴅᴇ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("toggle_refer", "ᴇɴᴀʙʟᴇ ᴏʀ ᴅɪsᴀʙʟᴇ ʀᴇꜰᴇʀʀᴀʟ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("check_refers", "ᴄʜᴇᴄᴋ ᴜsᴇʀ ʀᴇꜰᴇʀʀᴀʟ sᴛᴀᴛs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("addadmin", "ᴀᴅᴅ ᴀ ɴᴇᴡ ᴀᴅᴍɪɴ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("deladmin", "ʀᴇᴍᴏᴠᴇ ᴀɴ ᴀᴅᴍɪɴ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("listadmin", "ʟɪsᴛ ᴀʟʟ ᴀᴅᴍɪɴs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("stats", "ᴠɪᴇᴡ ʙᴏᴛ sᴛᴀᴛs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("ban", "ʙᴀɴ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("unban", "ᴜɴʙᴀɴ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("dbroadcast", "sᴇɴᴅ ᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("broadcast", "sᴇɴᴅ ᴀ ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ 3 ᴍᴏᴅᴇ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("reqfsub", "ᴛᴏɢɢʟᴇ ʀᴇǫᴜᴇsᴛ ғᴏʀᴄᴇ sᴜʙsᴄʀɪʙᴇ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("listfsub", "ʟɪsᴛ ғsᴜʙ ᴄʜᴀɴɴᴇʟ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("delfsub", "ᴅᴇʟᴇᴛᴇ ᴀ ғsᴜʙ ᴄʜᴀɴɴᴇʟ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("token", "ᴍᴀɴᴀɢᴇ ᴛᴏᴋᴇɴ sᴇᴛᴛɪɴɢ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("addfsub", "ᴀᴅᴅ ᴀ ғsᴜʙ ᴄʜᴀɴɴᴇʟ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("del_shortner", "ᴅᴇʟᴇᴛᴇ ᴀ sʜᴏʀᴛɴᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("list_shortner", "ʟɪsᴛ ᴀʟʟ sʜᴏʀᴛɴᴇʀs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("add_shortner", "ᴀᴅᴅ ᴀ sʜᴏʀᴛɴᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("verification", "ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ sᴛᴀᴛs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("status", "ᴄʜᴇᴄᴋ ᴀᴄᴄᴇssᴇᴅ ᴍᴇᴅɪᴀ sᴛᴀᴛᴜs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("addpaid", "ᴀᴅᴅ ᴘʀᴇᴍɪᴜᴍ ᴛᴏ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("removepaid", "ʀᴇᴍᴏᴠᴇ ᴘʀᴇᴍɪᴜᴍ ꜰʀᴏᴍ ᴀ ᴜsᴇʀ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("listpaid", "ʟɪsᴛ ᴀʟʟ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#         BotCommand("restart", "ʀᴇsᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ (ᴀᴅᴍɪɴ ᴏɴʟʏ 💀)"),
#     ]

#     await client.set_bot_commands(commands)
#     await message.reply_text("✅ ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅs ʜᴀᴠᴇ ʙᴇᴇɴ sᴇᴛ.")
