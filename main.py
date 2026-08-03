import os
import asyncio
import random
import time
import logging
import sqlite3
import base64
import hashlib
from cryptography.fernet import Fernet
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import SessionPasswordNeeded, UserNotParticipant, FloodWait, AuthKeyUnregistered, UserBannedInChannel
from pyrogram.enums import ChatMemberStatus, ChatType

# --- إعداد التسجيل والأخطاء ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- ثوابت البوت ---
BOT_TOKEN = "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A"
API_ID = 33057479
API_HASH = "0adc25ac386d50e8ee9f3b987863c4c0"
MAIN_ADMIN_USERNAME = "scofr"
REQUIRED_CHANNEL = "@m_55wa"
DB_FILE = "bot_database.db"

# --- مفتاح تشفير الجلسات ---
def get_fernet():
    secret = BOT_TOKEN
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)

def encrypt_session(val):
    if not val or not isinstance(val, str): return val
    try: return get_fernet().encrypt(val.encode()).decode()
    except Exception: return val

def decrypt_session(val):
    if not val or not isinstance(val, str): return val
    try: return get_fernet().decrypt(val.encode()).decode()
    except Exception: return val

# --- إدارة قاعدة البيانات (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        is_pro INTEGER DEFAULT 0,
        pro_expires_at REAL DEFAULT 0,
        banned INTEGER DEFAULT 0,
        delay INTEGER DEFAULT 120,
        active INTEGER DEFAULT 0,
        state TEXT DEFAULT NULL,
        last_error TEXT DEFAULT 'لا يوجد',
        created_at REAL DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        session_string TEXT,
        telegram_id INTEGER,
        first_name TEXT,
        username TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        chat_id TEXT,
        title TEXT,
        is_paused INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        type TEXT,
        file_id TEXT,
        content TEXT,
        caption TEXT,
        btn_text TEXT,
        btn_url TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
        user_id TEXT PRIMARY KEY,
        success INTEGER DEFAULT 0,
        failed INTEGER DEFAULT 0,
        last_publish REAL DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS publish_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        chat_id TEXT,
        status TEXT,
        timestamp REAL,
        details TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS codes (
        code TEXT PRIMARY KEY,
        days INTEGER,
        max_uses INTEGER,
        uses INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS code_used (
        code TEXT,
        user_id TEXT,
        PRIMARY KEY (code, user_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS developers (
        user_id TEXT PRIMARY KEY
    )''')

    conn.commit()
    conn.close()

async def db_exec(query, params=(), fetchone=False, fetchall=False, commit=True):
    def _run():
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(query, params)
        res = None
        if fetchone:
            res = c.fetchone()
        elif fetchall:
            res = c.fetchall()
        if commit:
            conn.commit()
        conn.close()
        return res
    return await asyncio.to_thread(_run)

# --- إدارة الجلسات في الذاكرة ---
client_pool = {}
login_attempts = {}
user_publisher_tasks = {}
rate_limits = {}

def check_rate_limit(user_id, limit_seconds=1.5):
    now = time.time()
    last = rate_limits.get(user_id, 0)
    if now - last < limit_seconds:
        return False
    rate_limits[user_id] = now
    return True

async def cleanup_login_attempts():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        to_del = []
        for uid, attempt in login_attempts.items():
            if now - attempt.get("time", now) > 300:
                if attempt.get("client") and attempt["client"].is_connected:
                    try: await attempt["client"].disconnect()
                    except Exception: pass
                to_del.append(uid)
        for uid in to_del:
            del login_attempts[uid]

async def close_and_remove_client(pool_key):
    if pool_key in client_pool:
        client = client_pool[pool_key]
        if client.is_connected:
            try: await client.disconnect()
            except Exception: pass
        del client_pool[pool_key]

# --- البوت الرئيسي ---
app = Client("publisher_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

async def is_admin(user):
    if not user: return False
    if user.username and user.username.lower() == MAIN_ADMIN_USERNAME.lower():
        return True
    dev = await db_exec("SELECT user_id FROM developers WHERE user_id = ?", (str(user.id),), fetchone=True)
    return dev is not None

async def is_subscribed(client, user_id):
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return True

def normalize_group_id(g):
    if not g: return ""
    g_str = str(g).strip()
    if "t.me/" in g_str:
        g_str = g_str.split("t.me/")[-1].strip("/")
    if g_str.startswith("+") or g_str.startswith("@") or (g_str.startswith("-") and g_str[1:].isdigit()) or g_str.isdigit():
        return g_str
    return "@" + g_str

# --- الواجهات ولوحات التحكم ---
def main_menu(is_admin_user=False, is_pro=False):
    pro_badge = " ⭐ [Pro]" if is_pro else " 👤 [مجاني]"
    keyboard = [
        [InlineKeyboardButton(f"👤 حساباتي{pro_badge}", callback_data="show_accounts"), InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
        [InlineKeyboardButton("👥 المجموعات", callback_data="show_groups"), InlineKeyboardButton("🌐 جلب مجموعاتي", callback_data="fetch_account_groups")],
        [InlineKeyboardButton("⏸️ الجروبات الموقوفة", callback_data="show_paused_groups"), InlineKeyboardButton("📊 الداشبورد والرسائل", callback_data="show_dashboard")],
        [InlineKeyboardButton("⏱️ ضبط الوقت", callback_data="set_time"), InlineKeyboardButton("✉️ إدارة الرسائل", callback_data="show_texts")],
        [InlineKeyboardButton("🎟️ تفعيل كود Pro", callback_data="redeem_code_prompt"), InlineKeyboardButton("📖 الشرح والتعليمات", callback_data="bot_guide")],
        [InlineKeyboardButton("🔴 إيقاف النشر", callback_data="stop_pub"), InlineKeyboardButton("🟢 بدء النشر", callback_data="start_pub")],
        [InlineKeyboardButton("👑 ترقية لـ Pro / الدعم", url=f"https://t.me/{MAIN_ADMIN_USERNAME}")]
    ]
    if is_admin_user:
        keyboard.insert(0, [InlineKeyboardButton("🛠️ لوحة الأدمن الخاصة", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

# --- محرك النشر الخلفي المستقل لكل مستخدم ---
async def get_or_create_client(user_id, acc):
    acc_id = acc["id"]
    pool_key = f"{user_id}_{acc_id}"
    
    if pool_key in client_pool:
        client = client_pool[pool_key]
        if client.is_connected:
            return client
        else:
            try:
                await client.connect()
                return client
            except Exception:
                await close_and_remove_client(pool_key)

    session_str = decrypt_session(acc["session_string"])
    try:
        client = Client(f"worker_{pool_key}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
        await client.connect()
        client_pool[pool_key] = client
        return client
    except Exception as e:
        logging.error(f"فشل الاتصال بالحساب {acc_id} للمستخدم {user_id}: {e}")
        return None

async def user_publisher_worker(user_id):
    logging.info(f"شروع مهمة النشر للمستخدم: {user_id}")
    while True:
        try:
            user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
            if not user or not user["active"] or user["banned"]:
                break

            is_pro = user["is_pro"]
            if is_pro and user["pro_expires_at"] > 0 and time.time() > user["pro_expires_at"]:
                await db_exec("UPDATE users SET is_pro = 0, pro_expires_at = 0 WHERE user_id = ?", (user_id,))
                is_pro = False

            accounts = await db_exec("SELECT * FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
            groups = await db_exec("SELECT * FROM groups WHERE user_id = ? AND is_paused = 0", (user_id,), fetchall=True)
            messages = await db_exec("SELECT * FROM messages WHERE user_id = ?", (user_id,), fetchall=True)

            if not accounts or not groups or not messages:
                await db_exec("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))
                break

            active_accs = accounts if is_pro else accounts[:1]
            
            for group in groups:
                target_chat = group["chat_id"]
                try: target_chat = int(target_chat)
                except Exception: pass

                msg_item = random.choice(messages) if is_pro else messages[0]

                for acc in active_accs:
                    client = await get_or_create_client(user_id, acc)
                    if not client: continue

                    try:
                        markup = None
                        if msg_item["btn_text"] and msg_item["btn_url"]:
                            markup = InlineKeyboardMarkup([[InlineKeyboardButton(msg_item["btn_text"], url=msg_item["btn_url"])]])

                        m_type = msg_item["type"]
                        file_id = msg_item["file_id"]
                        caption = msg_item["caption"] or msg_item["content"]

                        if m_type == "text":
                            await client.send_message(target_chat, msg_item["content"], reply_markup=markup)
                        elif m_type == "photo":
                            try: await client.send_photo(target_chat, file_id, caption=caption, reply_markup=markup)
                            except Exception: await client.send_message(target_chat, caption, reply_markup=markup)
                        elif m_type == "video":
                            try: await client.send_video(target_chat, file_id, caption=caption, reply_markup=markup)
                            except Exception: await client.send_message(target_chat, caption, reply_markup=markup)
                        elif m_type == "voice":
                            await client.send_voice(target_chat, file_id, caption=caption, reply_markup=markup)
                        elif m_type == "audio":
                            await client.send_audio(target_chat, file_id, caption=caption, reply_markup=markup)
                        elif m_type == "document":
                            await client.send_document(target_chat, file_id, caption=caption, reply_markup=markup)
                        elif m_type == "animation":
                            await client.send_animation(target_chat, file_id, caption=caption, reply_markup=markup)
                        elif m_type == "sticker":
                            await client.send_sticker(target_chat, file_id)

                        await db_exec("UPDATE stats SET success = success + 1, last_publish = ? WHERE user_id = ?", (time.time(), user_id))
                        await db_exec("INSERT INTO publish_logs (user_id, chat_id, status, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                                      (user_id, str(target_chat), "نجاح", time.time(), f"تم الإرسال عبر {acc['first_name']}"))
                        break

                    except FloodWait as fw:
                        logging.warning(f"FloodWait {fw.value}s للمستخدم {user_id}")
                        await asyncio.sleep(fw.value)
                        continue
                    except Exception as e:
                        err_msg = str(e)[:100]
                        await db_exec("UPDATE users SET last_error = ? WHERE user_id = ?", (err_msg, user_id))
                        await db_exec("UPDATE stats SET failed = failed + 1 WHERE user_id = ?", (user_id,))
                        await db_exec("INSERT INTO publish_logs (user_id, chat_id, status, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                                      (user_id, str(target_chat), "فشل", time.time(), err_msg))

                await asyncio.sleep(3)

            delay = user["delay"] if user["delay"] >= 10 else 10
            actual_delay = delay + random.randint(0, 15) if is_pro else delay
            await asyncio.sleep(actual_delay)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.exception(f"خطأ في مهمة المستخدم {user_id}: {e}")
            await asyncio.sleep(10)

async def manage_publisher_tasks():
    while True:
        try:
            active_users = await db_exec("SELECT user_id FROM users WHERE active = 1 AND banned = 0", fetchall=True)
            active_ids = {u["user_id"] for u in active_users}

            for uid in active_ids:
                if uid not in user_publisher_tasks or user_publisher_tasks[uid].done():
                    user_publisher_tasks[uid] = asyncio.create_task(user_publisher_worker(uid))

            for uid in list(user_publisher_tasks.keys()):
                if uid not in active_ids:
                    user_publisher_tasks[uid].cancel()
                    del user_publisher_tasks[uid]

        except Exception as e:
            logging.error(f"خطأ مدير مهام النشر: {e}")
        await asyncio.sleep(5)

# --- معالجات الرسائل والأوامر ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    if not message.from_user: return
    user_id = str(message.from_user.id)

    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            f"❌ **يجب عليك الاشتراك في قناة البوت أولاً لاستخدامه:**\n{REQUIRED_CHANNEL}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك الآن", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@','')}")], [InlineKeyboardButton("✅ تحقق", callback_data="check_sub")]])
        )
        return

    user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        await db_exec("INSERT INTO users (user_id, created_at) VALUES (?, ?)", (user_id, time.time()))
        await db_exec("INSERT INTO stats (user_id) VALUES (?)", (user_id,))
        user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)

    if user["banned"] and not await is_admin(message.from_user):
        await message.reply_text("❌ أنت محظور من استخدام هذا البوت.")
        return

    await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
    admin_flag = await is_admin(message.from_user)
    is_pro = bool(user["is_pro"])

    txt = f"أهلاً بك **{message.from_user.first_name}** في بوت النشر التلقائي المطور!\n\n"
    txt += "⭐ **نوع الاشتراك:** `Pro`" if is_pro else "👤 **نوع الاشتراك:** `مجاني`"
    await message.reply_text(txt, reply_markup=main_menu(admin_flag, is_pro))

@app.on_callback_query()
async def cb_handler(client, call: CallbackQuery):
    if not call.from_user: return
    user_id = str(call.from_user.id)
    if not check_rate_limit(user_id):
        await call.answer("⏱️ يرجى الانتظار قليلاً...", show_alert=False)
        return

    admin_flag = await is_admin(call.from_user)

    if call.data == "check_sub":
        if await is_subscribed(client, call.from_user.id):
            await call.answer("✅ تم التحقق!", show_alert=True)
            user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
            await call.message.edit_text("إليك لوحة التحكم الرئيسيّة:", reply_markup=main_menu(admin_flag, bool(user["is_pro"] if user else False)))
        else:
            await call.answer("❌ لم تشترك في القناة بعد!", show_alert=True)
        return

    user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user or (user["banned"] and not admin_flag):
        await call.answer("❌ لا يمكنك استخدام البوت.", show_alert=True)
        return

    is_pro = bool(user["is_pro"])

    if call.data == "back_main":
        await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        await call.message.edit_text("إليك لوحة التحكم الرئيسيّة:", reply_markup=main_menu(admin_flag, is_pro))

    elif call.data == "bot_guide":
        guide = (
            "📖 **دليل استخدام البوت المطور:**\n\n"
            "1️⃣ اضغط على **إضافة حساب** لربط حسابك عبر الرقم والرمز.\n"
            "2️⃣ قم بإضافة **المجموعات** أو استخدام زر **جلب مجموعاتي**.\n"
            "3️⃣ قم بإضافة **الرسائل** (يدعم النصوص، الصور، المستندات، الأصوات، البصمات، الملصقات).\n"
            "4️⃣ اضغط **بدء النشر** للبدء التلقائي.\n\n"
            "⭐ **مميزات Pro:** نشر بعدة حسابات متوازية، وقت عشوائي، ميديا بدون حدود، وإرسال عشوائي."
        )
        await call.message.edit_text(guide, reply_markup=back_menu())

    elif call.data == "show_dashboard":
        st = await db_exec("SELECT * FROM stats WHERE user_id = ?", (user_id,), fetchone=True)
        acc_count = (await db_exec("SELECT COUNT(*) as c FROM accounts WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        grp_count = (await db_exec("SELECT COUNT(*) as c FROM groups WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        msg_count = (await db_exec("SELECT COUNT(*) as c FROM messages WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        
        logs = await db_exec("SELECT * FROM publish_logs WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,), fetchall=True)
        log_str = ""
        for l in logs:
            log_str += f"• `{l['chat_id']}` -> {l['status']} ({l['details']})\n"
        if not log_str: log_str = "لا توجد عمليات مسبقة."

        dash = (
            f"📊 **لوحة التحكم والإحصائيات:**\n\n"
            f"👤 الحسابات المضافة: `{acc_count}`\n"
            f"👥 الجروبات المضافة: `{grp_count}`\n"
            f"✉️ الرسائل المخزنة: `{msg_count}`\n\n"
            f"✅ العمليات الناجحة: `{st['success'] if st else 0}`\n"
            f"❌ العمليات الفاشلة: `{st['failed'] if st else 0}`\n"
            f"⚠️ آخر خطأ: `{user['last_error']}`\n\n"
            f"📋 **آخر 5 عمليات نشر:**\n{log_str}"
        )
        await call.message.edit_text(dash, reply_markup=back_menu())

    elif call.data == "show_accounts":
        accs = await db_exec("SELECT * FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
        txt = f"👤 **حساباتك المرتبطة (`{len(accs)}`):**\n\n"
        kb = []
        for a in accs:
            txt += f"• {a['first_name']} (@{a['username']})\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف {a['first_name']}", callback_data=f"del_acc_{a['id']}")])
        kb.append([InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")])
        kb.append([InlineKeyboardButton("🗑️ حذف جميع الحسابات", callback_data="clear_accounts")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    elif call.data.startswith("del_acc_"):
        acc_id = int(call.data.split("_")[2])
        await close_and_remove_client(f"{user_id}_{acc_id}")
        await db_exec("DELETE FROM accounts WHERE id = ? AND user_id = ?", (acc_id, user_id))
        await call.answer("🗑️ تم حذف الحساب بنجاح", show_alert=True)
        await call.message.edit_text("تم تحديث القائمة.", reply_markup=back_menu())

    elif call.data == "clear_accounts":
        accs = await db_exec("SELECT id FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
        for a in accs:
            await close_and_remove_client(f"{user_id}_{a['id']}")
        await db_exec("DELETE FROM accounts WHERE user_id = ?", (user_id,))
        await call.answer("🗑️ تم حذف جميع الحسابات وإغلاق جلساتها.", show_alert=True)
        await call.message.edit_text("تم مسح الحسابات.", reply_markup=back_menu())

    elif call.data == "add_account":
        acc_count = (await db_exec("SELECT COUNT(*) as c FROM accounts WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        if not is_pro and acc_count >= 1:
            await call.answer("❌ الباقة المجانية تسمح بحساب واحد فقط! اشترك في Pro للزيادة.", show_alert=True)
            return
        await db_exec("UPDATE users SET state = 'waiting_for_phone' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("📱 **أرسل رقم هاتفك الآن مع رمز الدولة**\nمثال: `+966500000000`", reply_markup=back_menu())

    elif call.data == "show_groups":
        grps = await db_exec("SELECT * FROM groups WHERE user_id = ?", (user_id,), fetchall=True)
        txt = f"👥 **المجموعات المحفوظة (`{len(grps)}`):**\n\n"
        kb = []
        for g in grps:
            st = "⏸️" if g["is_paused"] else "🟢"
            kb.append([
                InlineKeyboardButton(f"{st} {g['title'] or g['chat_id']}", callback_data="none"),
                InlineKeyboardButton("🔄 إيقاف/تشغيل", callback_data=f"toggle_grp_{g['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"del_grp_{g['id']}")
            ])
        kb.append([InlineKeyboardButton("➕ إضافة مجموعة يدوياً", callback_data="add_group")])
        kb.append([InlineKeyboardButton("🌐 جلب تلقائي من الحساب", callback_data="fetch_account_groups")])
        kb.append([InlineKeyboardButton("🗑️ تفريغ كل المجموعات", callback_data="clear_groups")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    elif call.data == "show_paused_groups":
        grps = await db_exec("SELECT * FROM groups WHERE user_id = ? AND is_paused = 1", (user_id,), fetchall=True)
        txt = f"⏸️ **المجموعات الموقوفة مؤقتاً (`{len(grps)}`):**\n\n"
        kb = []
        for g in grps:
            kb.append([
                InlineKeyboardButton(f"⏸️ {g['title'] or g['chat_id']}", callback_data="none"),
                InlineKeyboardButton("▶️ تشغيل", callback_data=f"toggle_grp_{g['id']}")
            ])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    elif call.data.startswith("del_grp_"):
        gid = int(call.data.split("_")[2])
        await db_exec("DELETE FROM groups WHERE id = ? AND user_id = ?", (gid, user_id))
        await call.answer("🗑️ تم حذف المجموعة", show_alert=True)
        await call.message.edit_text("تم التحديث.", reply_markup=back_menu())

    elif call.data.startswith("toggle_grp_"):
        gid = int(call.data.split("_")[2])
        await db_exec("UPDATE groups SET is_paused = CASE WHEN is_paused = 1 THEN 0 ELSE 1 END WHERE id = ? AND user_id = ?", (gid, user_id))
        await call.answer("🔄 تم تغيير حالة المجموعة", show_alert=True)
        await call.message.edit_text("تم التحديث.", reply_markup=back_menu())

    elif call.data == "clear_groups":
        await db_exec("DELETE FROM groups WHERE user_id = ?", (user_id,))
        await call.answer("🗑️ تم مسح المجموعات", show_alert=True)
        await call.message.edit_text("تم التفريغ.", reply_markup=back_menu())

    elif call.data == "add_group":
        g_count = (await db_exec("SELECT COUNT(*) as c FROM groups WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        if not is_pro and g_count >= 5:
            await call.answer("❌ وصلت للحد الأقصى في المجاني (5 مجموعات).", show_alert=True)
            return
        await db_exec("UPDATE users SET state = 'waiting_for_group' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):", reply_markup=back_menu())

    elif call.data == "fetch_account_groups":
        accs = await db_exec("SELECT * FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
        if not accs:
            await call.answer("❌ أضف حساباً أولاً للجلب منه!", show_alert=True)
            return
        await call.answer("⏳ جاري فحص وجلب المجموعات من حسابك...", show_alert=True)
        client = await get_or_create_client(user_id, accs[0])
        if not client:
            await call.message.edit_text("❌ فشل الاتصال بالحساب لجلب المجموعات.", reply_markup=back_menu())
            return
        added = 0
        async for dialog in client.get_dialogs(limit=100):
            if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                chat_identifier = f"@{dialog.chat.username}" if dialog.chat.username else str(dialog.chat.id)
                exists = await db_exec("SELECT id FROM groups WHERE user_id = ? AND chat_id = ?", (user_id, chat_identifier), fetchone=True)
                if not exists:
                    await db_exec("INSERT INTO groups (user_id, chat_id, title) VALUES (?, ?, ?)", (user_id, chat_identifier, dialog.chat.title[:30]))
                    added += 1
        await call.message.edit_text(f"✅ تم جلب وإضافة `{added}` مجموعة جديدة بنجاح!", reply_markup=back_menu())

    elif call.data == "show_texts":
        msgs = await db_exec("SELECT * FROM messages WHERE user_id = ?", (user_id,), fetchall=True)
        txt = f"✉️ **رسائلك المحفوظة (`{len(msgs)}`):**\n\n"
        kb = []
        for m in msgs:
            prev = (m["content"] or m["caption"] or f"[{m['type']}]")[:30]
            kb.append([
                InlineKeyboardButton(f"[{m['type']}] {prev}", callback_data="none"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"del_msg_{m['id']}")
            ])
        kb.append([InlineKeyboardButton("➕ إضافة رسالة جديدة", callback_data="add_text")])
        kb.append([InlineKeyboardButton("🗑️ مسح كل الرسائل", callback_data="clear_texts")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    elif call.data.startswith("del_msg_"):
        mid = int(call.data.split("_")[2])
        await db_exec("DELETE FROM messages WHERE id = ? AND user_id = ?", (mid, user_id))
        await call.answer("🗑️ تم حذف الرسالة", show_alert=True)
        await call.message.edit_text("تم التحديث.", reply_markup=back_menu())

    elif call.data == "clear_texts":
        await db_exec("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await call.answer("🗑️ تم مسح كافة الرسائل", show_alert=True)
        await call.message.edit_text("تم المسح.", reply_markup=back_menu())

    elif call.data == "add_text":
        m_count = (await db_exec("SELECT COUNT(*) as c FROM messages WHERE user_id = ?", (user_id,), fetchone=True))["c"]
        if not is_pro and m_count >= 3:
            await call.answer("❌ الحد الأقصى للمجاني 3 رسائل فقط.", show_alert=True)
            return
        await db_exec("UPDATE users SET state = 'waiting_for_text' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("✍️ **أرسل رسالتك الآن** (نص، صورة، فيديو، بصمة، مستند...)\nمع إمكانية إضافة زر شفاف بكتابة:\n`النص | اسم الزر - https://t.me/...`", reply_markup=back_menu())

    elif call.data == "set_time":
        await db_exec("UPDATE users SET state = 'waiting_for_time' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("⏱️ **أرسل الفاصل الزمني بالثواني بين كل دورة نشر** (مثال: `120`):", reply_markup=back_menu())

    elif call.data == "start_pub":
        accs = await db_exec("SELECT id FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
        grps = await db_exec("SELECT id FROM groups WHERE user_id = ?", (user_id,), fetchall=True)
        msgs = await db_exec("SELECT id FROM messages WHERE user_id = ?", (user_id,), fetchall=True)
        if not accs or not grps or not msgs:
            await call.answer("❌ يجب إضافة حساب، ومجموعة، ورسالة واحدة على الأقل للبدء!", show_alert=True)
            return
        await db_exec("UPDATE users SET active = 1 WHERE user_id = ?", (user_id,))
        await call.answer("🟢 تم تفعيل النشر التلقائي بنجاح!", show_alert=True)
        await call.message.edit_text("🟢 **النشر التلقائي يعمل الآن في الخلفية.**", reply_markup=back_menu())

    elif call.data == "stop_pub":
        await db_exec("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))
        await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)
        await call.message.edit_text("🔴 **تم إيقاف النشر التلقائي.**", reply_markup=back_menu())

    elif call.data == "redeem_code_prompt":
        await db_exec("UPDATE users SET state = 'waiting_for_code' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("🎟️ **أرسل كود Pro الذي حصلت عليه الآن:**", reply_markup=back_menu())

    # --- لوحة الأدمن ---
    elif call.data == "admin_panel":
        if not admin_flag: return
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 إحصائيات عامة", callback_data="admin_stats"), InlineKeyboardButton("📢 إذاعة موجهة", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🎟️ إنشاء كود Pro", callback_data="admin_gen_code"), InlineKeyboardButton("📁 تصدير DB", callback_data="admin_export_db")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ])
        await call.message.edit_text("👑 **لوحة تحكم الأدمن الشاملة:**", reply_markup=admin_kb)

    elif call.data == "admin_stats":
        if not admin_flag: return
        tot_u = (await db_exec("SELECT COUNT(*) as c FROM users", fetchone=True))["c"]
        pro_u = (await db_exec("SELECT COUNT(*) as c FROM users WHERE is_pro = 1", fetchone=True))["c"]
        act_u = (await db_exec("SELECT COUNT(*) as c FROM users WHERE active = 1", fetchone=True))["c"]
        await call.answer(f"📊 الأعضاء: {tot_u} | Pro: {pro_u} | النشطين: {act_u}", show_alert=True)

    elif call.data == "admin_export_db":
        if not admin_flag: return
        await call.message.reply_document(DB_FILE, caption="📁 **نسخة احتياطية لقاعدة البيانات**")

    elif call.data == "admin_gen_code":
        if not admin_flag: return
        await db_exec("UPDATE users SET state = 'admin_creating_code' WHERE user_id = ?", (user_id,))
        await call.message.edit_text("🎟️ أرسل بيانات الكود بالصيغة التالية:\n`VIPCODE 30 5`\n(الكود الأيام الاستخدامات)", reply_markup=back_menu())

    elif call.data == "admin_broadcast":
        if not admin_flag: return
        b_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 للجميع", callback_data="bc_all"), InlineKeyboardButton("⭐ للـ Pro فقط", callback_data="bc_pro")],
            [InlineKeyboardButton("👤 للمجاني فقط", callback_data="bc_free"), InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])
        await call.message.edit_text("📢 **اختر الفئة الموجه لها الإذاعة:**", reply_markup=b_kb)

    elif call.data.startswith("bc_"):
        target_type = call.data.split("_")[1]
        await db_exec("UPDATE users SET state = ? WHERE user_id = ?", (f"admin_bc_{target_type}", user_id))
        await call.message.edit_text(f"📢 أرسل الرسالة الآن للإذاعة لفئة (`{target_type}`):", reply_markup=back_menu())

@app.on_message(~filters.command("start"))
async def msg_handler(client, message: Message):
    if not message.from_user: return
    user_id = str(message.from_user.id)

    user = await db_exec("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user or not user["state"]: return
    state = user["state"]

    admin_flag = await is_admin(message.from_user)

    if state == "waiting_for_code":
        code_input = message.text.strip()
        cd = await db_exec("SELECT * FROM codes WHERE code = ?", (code_input,), fetchone=True)
        if cd:
            if cd["uses"] >= cd["max_uses"]:
                await message.reply_text("❌ هذا الكود استنفد عدد مرات الاستخدام!")
            else:
                used = await db_exec("SELECT * FROM code_used WHERE code = ? AND user_id = ?", (code_input, user_id), fetchone=True)
                if used:
                    await message.reply_text("⚠️ لقد استخدمت هذا الكود مسبقاً!")
                else:
                    exp = time.time() + (cd["days"] * 86400)
                    await db_exec("UPDATE users SET is_pro = 1, pro_expires_at = ? WHERE user_id = ?", (exp, user_id))
                    await db_exec("UPDATE codes SET uses = uses + 1 WHERE code = ?", (code_input,))
                    await db_exec("INSERT INTO code_used (code, user_id) VALUES (?, ?)", (code_input, user_id))
                    await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
                    await message.reply_text(f"🎉 **مبروك! تم تفعيل اشتراك Pro لمدة {cd['days']} يوم.**", reply_markup=main_menu(admin_flag, True))
        else:
            await message.reply_text("❌ الكود خاطئ أو غير موجود.")

    elif state == "admin_creating_code":
        if not admin_flag: return
        try:
            p = message.text.split()
            code, days, max_u = p[0], int(p[1]), int(p[2])
            await db_exec("INSERT INTO codes (code, days, max_uses) VALUES (?, ?, ?)", (code, days, max_u))
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text(f"✅ تم إنشاء الكود `{code}` بنجاح!", reply_markup=back_menu())
        except Exception:
            await message.reply_text("❌ صيغة خاطئة. أرسل مثل: `PRO2026 30 10`")

    elif state.startswith("admin_bc_"):
        if not admin_flag: return
        b_type = state.split("_")[2]
        await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        
        query = "SELECT user_id FROM users WHERE banned = 0"
        if b_type == "pro": query += " AND is_pro = 1"
        elif b_type == "free": query += " AND is_pro = 0"
        
        target_users = await db_exec(query, fetchall=True)
        succ, fail = 0, 0
        st_msg = await message.reply_text("⏳ جاري الإذاعة...")
        for u in target_users:
            try:
                await message.copy(chat_id=int(u["user_id"]))
                succ += 1
                await asyncio.sleep(0.05)
            except Exception:
                fail += 1
        await st_msg.edit_text(f"✅ اكتملت الإذاعة!\n• نجح: {succ}\n• فشل: {fail}")

    elif state == "waiting_for_phone":
        phone = message.text.strip()
        temp_client = None
        try:
            temp_client = Client(f"login_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await temp_client.connect()
            code_info = await temp_client.send_code(phone)
            login_attempts[user_id] = {"client": temp_client, "phone": phone, "hash": code_info.phone_code_hash, "time": time.time()}
            await db_exec("UPDATE users SET state = 'waiting_for_otp' WHERE user_id = ?", (user_id,))
            await message.reply_text("📥 **أرسل كود التحقق الواصل لحسابك الآن:**")
        except Exception as e:
            if temp_client and temp_client.is_connected:
                try: await temp_client.disconnect()
                except Exception: pass
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text(f"❌ حدث خطأ أثناء إرسال الكود: {e}")

    elif state == "waiting_for_otp":
        attempt = login_attempts.get(user_id)
        if not attempt:
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text("❌ انتهت مهلة جلسة الدخول. حاول مجدداً.")
            return
        try:
            await attempt["client"].sign_in(attempt["phone"], attempt["hash"], message.text.strip())
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            enc_session = encrypt_session(session_str)

            await db_exec("INSERT INTO accounts (user_id, session_string, telegram_id, first_name, username) VALUES (?, ?, ?, ?, ?)",
                          (user_id, enc_session, me.id, me.first_name, me.username or "بدون معرف"))
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text("✅ **تم ربط الحساب بنجاح!**", reply_markup=main_menu(admin_flag, bool(user["is_pro"])))
        except SessionPasswordNeeded:
            await db_exec("UPDATE users SET state = 'waiting_for_password' WHERE user_id = ?", (user_id,))
            await message.reply_text("🔐 **الحساب محمي بالتحقق بخطوتين. أرسل كلمة المرور الآن:**")
            return
        except Exception as e:
            await message.reply_text(f"❌ فشل الدخول: {e}")
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        finally:
            if user_id in login_attempts and user["state"] != "waiting_for_password":
                try: await attempt["client"].disconnect()
                except Exception: pass
                del login_attempts[user_id]

    elif state == "waiting_for_password":
        attempt = login_attempts.get(user_id)
        if not attempt:
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text("❌ انتهت المهلة.")
            return
        try:
            await attempt["client"].check_password(message.text.strip())
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            enc_session = encrypt_session(session_str)

            await db_exec("INSERT INTO accounts (user_id, session_string, telegram_id, first_name, username) VALUES (?, ?, ?, ?, ?)",
                          (user_id, enc_session, me.id, me.first_name, me.username or "بدون معرف"))
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
            await message.reply_text("✅ **تم ربط الحساب بنجاح!**", reply_markup=main_menu(admin_flag, bool(user["is_pro"])))
        except Exception as e:
            await message.reply_text(f"❌ كلمة المرور خاطئة: {e}")
            await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        finally:
            if user_id in login_attempts:
                try: await attempt["client"].disconnect()
                except Exception: pass
                del login_attempts[user_id]

    elif state == "waiting_for_group":
        g_input = normalize_group_id(message.text.strip())
        await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        
        accs = await db_exec("SELECT * FROM accounts WHERE user_id = ?", (user_id,), fetchall=True)
        g_title = g_input
        if accs:
            client = await get_or_create_client(user_id, accs[0])
            if client:
                try:
                    chat = await client.get_chat(g_input)
                    g_title = chat.title
                    g_input = f"@{chat.username}" if chat.username else str(chat.id)
                except Exception:
                    pass

        await db_exec("INSERT INTO groups (user_id, chat_id, title) VALUES (?, ?, ?)", (user_id, g_input, g_title))
        await message.reply_text(f"✅ تم حفظ المجموعة: `{g_title}`", reply_markup=back_menu())

    elif state == "waiting_for_text":
        btn_text, btn_url = None, None
        content = message.text or message.caption or ""

        if "|" in content and "-" in content:
            try:
                parts = content.split("|")
                content = parts[0].strip()
                b_part = parts[1].strip()
                b_name, b_link = b_part.split("-", 1)
                btn_text = b_name.strip()
                btn_url = b_link.strip()
            except Exception: pass

        m_type = "text"
        file_id = None

        if message.photo:
            m_type = "photo"
            file_id = message.photo.file_id
        elif message.video:
            m_type = "video"
            file_id = message.video.file_id
        elif message.voice:
            m_type = "voice"
            file_id = message.voice.file_id
        elif message.audio:
            m_type = "audio"
            file_id = message.audio.file_id
        elif message.document:
            m_type = "document"
            file_id = message.document.file_id
        elif message.animation:
            m_type = "animation"
            file_id = message.animation.file_id
        elif message.sticker:
            m_type = "sticker"
            file_id = message.sticker.file_id

        await db_exec("INSERT INTO messages (user_id, type, file_id, content, caption, btn_text, btn_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (user_id, m_type, file_id, content, content, btn_text, btn_url))
        await db_exec("UPDATE users SET state = NULL WHERE user_id = ?", (user_id,))
        await message.reply_text("✅ **تم حفظ الرسالة بنجاح!**", reply_markup=back_menu())

    elif state == "waiting_for_time":
        try:
            t = int(message.text.strip())
            if t < 10: t = 10
            await db_exec("UPDATE users SET delay = ?, state = NULL WHERE user_id = ?", (t, user_id))
            await message.reply_text(f"⏱️ تم ضبط الوقت إلى `{t}` ثانية.", reply_markup=back_menu())
        except Exception:
            await message.reply_text("❌ يرجى إرسال رقم صحيح بالثواني.")

# --- التشغيل والتنظيف عند الإغلاق ---
async def main():
    init_db()
    asyncio.create_task(cleanup_login_attempts())
    asyncio.create_task(manage_publisher_tasks())
    await app.start()
    logging.info("🚀 تم تشغيل البوت المحدث بنجاح!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())

