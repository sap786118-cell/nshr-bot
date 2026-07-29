import os
import json
import asyncio
import random
import time
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import SessionPasswordNeeded, UserNotParticipant
from pyrogram.enums import ChatMemberStatus, ChatType

# --- إعداد التسجيل والأخطاء ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- إعداد التوكن والمعلومات الأساسية ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A")
API_ID = os.getenv("API_ID", "33057479")
API_HASH = os.getenv("API_HASH", "0adc25ac386d50e8ee9f3b987863c4c0")

# قراءة معرف قناة النسخ الاحتياطي (يوصى بشدة أن يكون يوزرنيم مثل @m_55wa لتجنب مشاكل in_memory)
BACKUP_CHAT_ID = os.getenv("BACKUP_CHAT_ID", "@m_55wa")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise ValueError("❌ خطأ: يجب تعيين متغيرات البيئة BOT_TOKEN و API_ID و API_HASH بشكل صحيح!")

API_ID = int(API_ID)

# معالجة BACKUP_CHAT_ID ليكون رقماً إن كان رقماً، أو يوزرنيم إن كان نصاً
if BACKUP_CHAT_ID:
    if str(BACKUP_CHAT_ID).lstrip('-').isdigit():
        BACKUP_CHAT_ID = int(BACKUP_CHAT_ID)
    else:
        if not str(BACKUP_CHAT_ID).startswith("@"):
            BACKUP_CHAT_ID = "@" + str(BACKUP_CHAT_ID).strip()

MAIN_ADMIN_USERNAME = "scofr"
REQUIRED_CHANNEL = "@m_55wa"

app = Client("publisher_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
DATA_FILE = "users_config.json"
BACKUP_CAPTION = "🔄 نسخة احتياطية تلقائية لملف الإعدادات"
data_changed = False
login_attempts = {}
account_groups_cache = {}
client_pool = {}
_memory_cache = None

data_lock = asyncio.Lock()

async def save_data(data):
    global data_changed, _memory_cache
    async with data_lock:
        _memory_cache = data
        temp_file = DATA_FILE + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, DATA_FILE)
            data_changed = True
        except Exception:
            logging.exception("خطأ أثناء حفظ البيانات بشكل آمن")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

def load_data():
    global _memory_cache
    if not os.path.exists(DATA_FILE):
        default_data = {"_settings": {"developers": [], "codes": {}, "buttons": {}}}
        _memory_cache = default_data
        return default_data
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "_settings" not in data:
                data["_settings"] = {"developers": [], "codes": {}, "buttons": {}}
            
            current_time = time.time()
            for uid, udata in data.items():
                if uid == "_settings": continue
                if isinstance(udata, dict):
                    udata.setdefault("accounts", [])
                    udata.setdefault("texts", [])
                    udata.setdefault("groups", [])
                    udata.setdefault("paused_groups", [])
                    udata.setdefault("stats", {"success": 0, "failed": 0})
                    udata.setdefault("banned", False)
                    udata.setdefault("is_pro", False)
                    udata.setdefault("pro_expires_at", 0)
                    
                    if udata.get("is_pro", False) and udata.get("pro_expires_at", 0) > 0:
                        if current_time > udata["pro_expires_at"]:
                            udata["is_pro"] = False
                            udata["pro_expires_at"] = 0
            _memory_cache = data
            return data
    except json.JSONDecodeError:
        logging.exception("❌ تحذير: ملف الإعدادات تالف. يتم الاعتماد على الذاكرة المؤقتة.")
        if _memory_cache is not None:
            return _memory_cache
        temp_file = DATA_FILE + ".tmp"
        if os.path.exists(temp_file):
            try:
                with open(temp_file, 'r', encoding='utf-8') as tf:
                    data = json.load(tf)
                    _memory_cache = data
                    return data
            except Exception:
                pass
        return {"_settings": {"developers": [], "codes": {}, "buttons": {}}}
    except Exception:
        logging.exception("خطأ أثناء قراءة ملف الإعدادات")
        if _memory_cache is not None:
            return _memory_cache
        return {"_settings": {"developers": [], "codes": {}, "buttons": {}}}

def normalize_group_id(g):
    if not g:
        return ""
    g_str = str(g).strip()
    if "t.me/" in g_str:
        g_str = "@" + g_str.split("t.me/")[-1].strip("/")
    if g_str.startswith("https://t.me/"):
        g_str = "@" + g_str.split("https://t.me/")[-1].strip("/")
    if not g_str.startswith("@") and not g_str.startswith("-") and not g_str.isdigit():
        g_str = "@" + g_str
    return g_str

async def restore_config(client):
    if not BACKUP_CHAT_ID:
        logging.info("[i] لم يتم تعيين BACKUP_CHAT_ID، الاعتماد على التخزين المحلي فقط.")
        return
    logging.info("[*] جاري فحص ملف الإعدادات محلياً واستعادة النسخة...")
    try:
        await client.get_chat(BACKUP_CHAT_ID)
        
        if not os.path.exists(DATA_FILE):
            backups = []
            async for message in client.get_chat_history(BACKUP_CHAT_ID, limit=50):
                if message.document and message.document.file_name == DATA_FILE:
                    backups.append(message)
            
            if backups:
                backups.sort(key=lambda m: m.id, reverse=True)
                latest_backup = backups[0]
                await latest_backup.download(file_name=DATA_FILE)
                logging.info(f"[+] تم استعادة أحدث نسخة احتياطية بنجاح من الرسالة رقم {latest_backup.id}!")
    except Exception:
        logging.exception("خطأ أثناء استعادة النسخة الاحتياطية (تخطي واستمرار التشغيل)")

async def backup_config(client):
    global data_changed
    if not BACKUP_CHAT_ID:
        data_changed = False
        return
    try:
        if os.path.exists(DATA_FILE):
            await client.get_chat(BACKUP_CHAT_ID)
            
            sent_msg = await client.send_document(
                chat_id=BACKUP_CHAT_ID,
                document=DATA_FILE,
                caption=BACKUP_CAPTION
            )
            logging.info("[+] تم رفع النسخة الاحتياطية الجديدة بنجاح إلى قناة النسخ.")
            
            try:
                async for message in client.get_chat_history(BACKUP_CHAT_ID, limit=20):
                    if message.id != sent_msg.id and message.document and message.document.file_name == DATA_FILE and message.caption == BACKUP_CAPTION:
                        await client.delete_messages(BACKUP_CHAT_ID, message.id)
            except Exception:
                logging.exception("خطأ أثناء حذف النسخة الاحتياطية القديمة")
        else:
            data_changed = False
    except Exception:
        logging.exception("فشل رفع النسخة الاحتياطية الجديدة")
        data_changed = True

async def periodic_backup_worker(client):
    global data_changed
    while True:
        await asyncio.sleep(60)
        try:
            data = load_data()
            changed_pro = False
            current_time = time.time()
            for uid, udata in data.items():
                if uid == "_settings": continue
                if isinstance(udata, dict) and udata.get("is_pro", False):
                    expires_at = udata.get("pro_expires_at", 0)
                    if expires_at > 0 and current_time > expires_at:
                        udata["is_pro"] = False
                        udata["pro_expires_at"] = 0
                        changed_pro = True
            if changed_pro:
                await save_data(data)
        except Exception:
            pass

        if data_changed:
            data_changed = False
            await backup_config(client)

def is_admin(user):
    if user.username and user.username.lower() == MAIN_ADMIN_USERNAME.lower():
        return True
    data = load_data()
    developers = data.get("_settings", {}).get("developers", [])
    if user.id in developers or str(user.id) in [str(d) for d in developers]:
        return True
    return False

async def is_subscribed(client, user_id):
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.RESTRICTED]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception:
        return True

def main_menu(is_admin_user=False, is_pro=False):
    pro_badge = " ⭐ [Pro]" if is_pro else " 👤 [مجاني]"
    keyboard = [
        [InlineKeyboardButton(f"👤 حساباتي{pro_badge}", callback_data="show_accounts"), InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
        [InlineKeyboardButton("👥 السوبرات", callback_data="show_groups"), InlineKeyboardButton("🌐 مجموعات الحساب", callback_data="fetch_account_groups")],
        [InlineKeyboardButton("⏸️ المجموعات المؤقتة", callback_data="show_paused_groups"), InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
        [InlineKeyboardButton("⏱️ ضبط الوقت", callback_data="set_time"), InlineKeyboardButton("✉️ رسائل النشر", callback_data="show_texts")],
        [InlineKeyboardButton("🎟️ استبدال كود Pro", callback_data="redeem_code_prompt"), InlineKeyboardButton("📖 شرح البوت", callback_data="bot_guide")],
        [InlineKeyboardButton("🔴 إيقاف النشر", callback_data="stop_pub"), InlineKeyboardButton("🟢 بدء النشر", callback_data="start_pub")],
        [InlineKeyboardButton("👑 ترقية لـ Pro / الدعم", url=f"https://t.me/{MAIN_ADMIN_USERNAME}")]
    ]
    if is_admin_user:
        keyboard.insert(0, [InlineKeyboardButton("🛠️ لوحة الأدمن الخاصة", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

def subscription_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("✅ لقد اشتركت، تحقق الآن", callback_data="check_subscription")]
    ])

async def render_groups_page(message, user_id, data, is_pro):
    groups_list = account_groups_cache.get(user_id, [])
    user_groups = data[user_id].get("groups", [])
    keyboard = []
    for g in groups_list[:25]:
        g_identifier = normalize_group_id(g["username"] if not g["id"].startswith("-100") else g["id"])
        is_added = g_identifier in user_groups or g["id"] in user_groups
        btn_text = "🗑️ حذف" if is_added else "➕ إضافة"
        callback_val = f"tg_rem_{g_identifier}" if is_added else f"tg_add_{g_identifier}"
        keyboard.append([
            InlineKeyboardButton(g["title"], callback_data="none_click"),
            InlineKeyboardButton(btn_text, callback_data=callback_val)
        ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع للسوبرات", callback_data="show_groups")])
    text = f"🌐 **مجموعات حسابك (تم العثور على {len(groups_list)}):**\nاضغط على زر (إضافة) لتخزينها أو (حذف) لإزالتها:"
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass

async def get_or_create_client(user_id, acc):
    session_str = acc.get("session_string")
    acc_id = acc.get("id")
    pool_key = f"{user_id}_{acc_id}"
    
    if pool_key in client_pool:
        client = client_pool[pool_key]
        if not client.is_connected:
            try:
                await client.connect()
            except Exception:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                del client_pool[pool_key]
        else:
            return client

    try:
        client = Client(
            f"worker_{pool_key}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_str,
            in_memory=True
        )
        await client.connect()
        client_pool[pool_key] = client
        return client
    except Exception:
        return None

async def background_publisher():
    while True:
        await asyncio.sleep(10)
        try:
            data = load_data()
            updated = False
            for user_id, u_data in data.items():
                if user_id == "_settings": continue
                try:
                    if u_data.get("active") and u_data.get("accounts") and u_data.get("groups") and u_data.get("texts"):
                        delay = u_data.get("delay", 120)
                        accounts = u_data.get("accounts")
                        texts = u_data.get("texts")
                        groups = u_data.get("groups")
                        paused_groups = u_data.get("paused_groups", [])
                        
                        active_accounts = accounts if u_data.get("is_pro") else accounts[:1]
                        
                        for acc in active_accounts:
                            user_client = await get_or_create_client(user_id, acc)
                            if not user_client:
                                continue
                            
                            try:
                                for group in groups:
                                    norm_group = normalize_group_id(group)
                                    if norm_group in paused_groups or group in paused_groups:
                                        continue
                                    
                                    try:
                                        target_chat = int(group) if (group.isdigit() or (group.startswith("-") and group[1:].isdigit())) else group
                                    except Exception:
                                        target_chat = group

                                    for t_item in texts:
                                        try:
                                            markup = None
                                            if isinstance(t_item, dict) and t_item.get("btn_text") and t_item.get("btn_url"):
                                                markup = InlineKeyboardMarkup([[InlineKeyboardButton(t_item.get("btn_text"), url=t_item.get("btn_url"))]])

                                            if isinstance(t_item, str):
                                                await user_client.send_message(target_chat, t_item)
                                            else:
                                                m_type = t_item.get("type")
                                                if m_type == "text":
                                                    await user_client.send_message(target_chat, t_item.get("content"), reply_markup=markup)
                                                elif m_type == "photo":
                                                    await user_client.send_photo(target_chat, t_item.get("file_id"), caption=t_item.get("caption"), reply_markup=markup)
                                                elif m_type == "video":
                                                    await user_client.send_video(target_chat, t_item.get("file_id"), caption=t_item.get("caption"), reply_markup=markup)
                                            
                                            if user_id in data:
                                                data[user_id]["stats"]["success"] = data[user_id]["stats"].get("success", 0) + 1
                                                updated = True
                                            await asyncio.sleep(3)
                                        except Exception:
                                            if user_id in data:
                                                data[user_id]["stats"]["failed"] = data[user_id]["stats"].get("failed", 0) + 1
                                                updated = True
                            except Exception:
                                pass
                        
                        if updated:
                            await save_data(data)
                        
                        actual_delay = random.randint(int(delay), int(delay) + 30)
                        await asyncio.sleep(actual_delay)
                except Exception:
                    pass
        except Exception:
            pass

@app.on_message(filters.command("start"))
async def start_command(client, message):
    if not message.from_user:
        return
    user_id = str(message.from_user.id)
    
    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            f"❌ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!**\n\nرابط القناة: https://t.me/{REQUIRED_CHANNEL.replace('@', '')}\n\nبعد الاشتراك، اضغط على زر التحقق بالأسفل 👇",
            reply_markup=subscription_markup()
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        await message.reply_text("❌ عذراً، لقد تم حظرك من استخدام هذا البوت.")
        return

    if user_id not in data:
        data[user_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False, "pro_expires_at": 0}
    else:
        for key in ["accounts", "texts", "groups", "paused_groups"]:
            if key not in data[user_id]: data[user_id][key] = []
        if "stats" not in data[user_id]: data[user_id]["stats"] = {"success": 0, "failed": 0}
        if "banned" not in data[user_id]: data[user_id]["banned"] = False
        if "is_pro" not in data[user_id]: data[user_id]["is_pro"] = False
        if "pro_expires_at" not in data[user_id]: data[user_id]["pro_expires_at"] = 0
    
    data[user_id]["state"] = None
    await save_data(data)
    
    is_pro = data[user_id].get("is_pro", False)
    welcome_text = f"أهلاً بك يا {message.from_user.first_name}، هذا بوت النشر التلقائي الذكي."
    
    if is_pro:
        welcome_text += "\n\n⭐ حسابك مفعل على **باقة Pro المدفوعة** (مميزات غير محدودة)."
    else:
        welcome_text += "\n\n👤 حسابك على **الباقة المجانية** (محدد بحساب واحد و 5 مجموعات كحد أقصى)."

    if admin_status:
        welcome_text += "\n\n👑 أهلاً بك يا أدمن/مطور، تم التعرف على صلاحياتك الكاملة."

    await message.reply_text(welcome_text, reply_markup=main_menu(admin_status, is_pro))

@app.on_callback_query()
async def callback_handler(client, call):
    if not call.from_user:
        return
    user_id = str(call.from_user.id)
    admin_status = is_admin(call.from_user)
    answered = False

    try:
        if call.data == "check_subscription":
            if await is_subscribed(client, call.from_user.id):
                data = load_data()
                is_pro = data.get(user_id, {}).get("is_pro", False)
                await call.answer("✅ تم التحقق من اشتراكك بنجاح!", show_alert=True)
                answered = True
                await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status, is_pro))
            else:
                await call.answer("❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)
                answered = True
            return

        if call.data == "none_click":
            await call.answer("اسم المجموعة فقط", show_alert=False)
            answered = True
            return

        if call.data.startswith("tg_add_") or call.data.startswith("tg_rem_"):
            data = load_data()
            is_pro = data.get(user_id, {}).get("is_pro", False)
            if call.data.startswith("tg_add_"):
                g_target = normalize_group_id(call.data[7:])
                if not is_pro and len(data[user_id].get("groups", [])) >= 5:
                    await call.answer("❌ وصلت للحد الأقصى في الباقة المجانية (5 مجموعات). اشترك في Pro!", show_alert=True)
                    answered = True
                    return
                if g_target not in data[user_id]["groups"]:
                    data[user_id]["groups"].append(g_target)
                    await save_data(data)
                await call.answer("✅ تمت إضافة المجموعة", show_alert=True)
                answered = True
            elif call.data.startswith("tg_rem_"):
                g_target = normalize_group_id(call.data[7:])
                if g_target in data[user_id]["groups"]:
                    data[user_id]["groups"].remove(g_target)
                    await save_data(data)
                await call.answer("🗑️ تمت إزالة المجموعة", show_alert=True)
                answered = True
            
            if user_id in account_groups_cache:
                await render_groups_page(call.message, user_id, data, is_pro)
            return

        if not await is_subscribed(client, call.from_user.id):
            await call.answer("❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
            answered = True
            return

        data = load_data()
        if user_id not in data: 
            data[user_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False, "pro_expires_at": 0}

        is_pro = data[user_id].get("is_pro", False)

        if data.get(user_id, {}).get("banned", False) and not admin_status:
            await call.answer("❌ عذراً، تم حظرك من البوت.", show_alert=True)
            answered = True
            return

        if call.data == "back_main":
            data[user_id]["state"] = None
            await save_data(data)
            await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status, is_pro))
            
        elif call.data == "bot_guide":
            guide_text = (
                "📖 **دليل استخدام البوت:**\n\n"
                "👤 **الباقة المجانية:** ربط حساب واحد، وإضافة حتى 5 مجموعات.\n"
                "⭐ **باقة Pro:** حسابات ومجموعات غير محدودة + أزرار شفافة.\n\n"
                "💳 للترقية، تواصل مع المطور."
            )
            await call.message.edit_text(guide_text, reply_markup=back_menu())

        elif call.data == "redeem_code_prompt":
            data[user_id]["state"] = "waiting_for_code"
            await save_data(data)
            await call.message.edit_text("🎟️ أرسل كود التفعيل الخاص بـ Pro الآن في رسالة جديدة:", reply_markup=back_menu())

        elif call.data == "fetch_account_groups":
            accounts = data[user_id].get("accounts", [])
            if not accounts:
                await call.answer("❌ يجب إضافة حساب أولاً لجلب المجموعات!", show_alert=True)
                answered = True
                return
            await call.answer("⏳ جاري جلب مجموعات حسابك من تيليجرام...", show_alert=True)
            answered = True
            acc = accounts[0]
            session_str = acc.get("session_string")
            try:
                groups_list = []
                async with Client(f"fetcher_{user_id}_{acc.get('id')}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True) as temp_client:
                    async for dialog in temp_client.get_dialogs():
                        if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                            groups_list.append({
                                "id": str(dialog.chat.id),
                                "title": dialog.chat.title[:25],
                                "username": f"@{dialog.chat.username}" if dialog.chat.username else str(dialog.chat.id)
                            })
                
                if not groups_list:
                    await call.message.edit_text("❌ لم يتم العثور على أي مجموعات في هذا الحساب.", reply_markup=back_menu())
                    return
                
                account_groups_cache[user_id] = groups_list
                await render_groups_page(call.message, user_id, data, is_pro)
            except Exception:
                await call.message.edit_text("❌ حدث خطأ أثناء جلب المجموعات.", reply_markup=back_menu())

        elif call.data == "admin_panel":
            if not admin_status: return
            admin_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 الأعضاء", callback_data="admin_member_count"), InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast")],
                [InlineKeyboardButton("⭐ إدارة Pro المباشرة", callback_data="admin_pro_management"), InlineKeyboardButton("🎟️ إنشاء كود Pro", callback_data="admin_create_code")],
                [InlineKeyboardButton("🚫 حظر/إلغاء", callback_data="admin_ban_user"), InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
            await call.message.edit_text("👑 **لوحة تحكم الأدمن:**", reply_markup=admin_kb)

        elif call.data == "admin_create_code":
            if not admin_status: return
            data[user_id]["state"] = "creating_code"
            await save_data(data)
            await call.message.edit_text("🎟️ أرسل تفاصيل الكود الجديد بالشكل التالي:\n`VIPCODE 30 5`\n(اسم الكود ثم عدد الأيام ثم عدد المستخدمين)", reply_markup=back_menu())

        elif call.data == "admin_pro_management":
            if not admin_status: return
            pro_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ تفعيل Pro", callback_data="add_pro_user"), InlineKeyboardButton("❌ إزالة Pro", callback_data="remove_pro_user")],
                [InlineKeyboardButton("📋 المشتركين", callback_data="list_pro_users")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
            ])
            await call.message.edit_text("⭐ **إدارة اشتراكات Pro:**", reply_markup=pro_kb)

        elif call.data == "add_pro_user":
            if not admin_status: return
            data[user_id]["state"] = "waiting_for_pro_add_id"
            await save_data(data)
            await call.message.edit_text("➕ أرسل آيدي المستخدم لمنحه Pro:", reply_markup=back_menu())

        elif call.data == "remove_pro_user":
            if not admin_status: return
            data[user_id]["state"] = "waiting_for_pro_remove_id"
            await save_data(data)
            await call.message.edit_text("❌ أرسل آيدي المستخدم لإرجاعه للمجاني:", reply_markup=back_menu())

        elif call.data == "list_pro_users":
            if not admin_status: return
            all_u = load_data()
            pro_list = [uid for uid, uval in all_u.items() if uid != "_settings" and isinstance(uval, dict) and uval.get("is_pro")]
            text = f"⭐ **مشتركو Pro:** (`{len(pro_list)}`)\n\n"
            for i, pid in enumerate(pro_list, 1):
                text += f"{i}. `{pid}`\n"
            await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_pro_management")]]))

        elif call.data == "admin_member_count":
            if not admin_status: return
            count = len([uid for uid in load_data() if uid != "_settings"])
            await call.answer(f"📊 إجمالي الأعضاء: {count}", show_alert=True)
            answered = True

        elif call.data == "admin_broadcast":
            if not admin_status: return
            data[user_id]["state"] = "waiting_for_admin_broadcast"
            await save_data(data)
            await call.message.edit_text("📢 أرسل رسالة الإذاعة:", reply_markup=back_menu())

        elif call.data == "admin_ban_user":
            if not admin_status: return
            data[user_id]["state"] = "waiting_for_ban_user_id"
            await save_data(data)
            await call.message.edit_text("🚫 أرسل آيدي المستخدم للحظر/إلغاء الحظر:", reply_markup=back_menu())

        elif call.data == "show_accounts":
            accs = data[user_id].get("accounts", [])
            text = f"👤 **الحسابات المضافة:** (`{len(accs)}`)\n\n"
            for i, acc in enumerate(accs, 1):
                text += f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"
            keyboard = [
                [InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
                [InlineKeyboardButton("🗑️ حذف الحسابات", callback_data="clear_accounts")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]
            await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                
        elif call.data == "add_account":
            if not is_pro and len(data[user_id].get("accounts", [])) >= 1:
                await call.answer("❌ الباقة المجانية تسمح بحساب واحد فقط!", show_alert=True)
                answered = True
                return
            data[user_id]["state"] = "waiting_for_phone"
            await save_data(data)
            await call.message.edit_text("📱 أرسل رقم هاتفك مع رمز الدولة (+9665xxxxxxxx):", reply_markup=back_menu())
            
        elif call.data == "clear_accounts":
            data[user_id]["accounts"] = []
            await save_data(data)
            await call.message.edit_text("🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu())

        elif call.data == "show_groups":
            groups = data[user_id].get("groups", [])
            paused = data[user_id].get("paused_groups", [])
            text = f"👥 **السوبرات المضافة حالياً:** (`{len(groups)}`)\n\n"
            for i, g in enumerate(groups, 1):
                status = "⏸️ (موقوفة)" if g in paused else "🟢 (نشطة)"
                text += f"{i}. `{g}` - {status}\n"
            keyboard = [
                [InlineKeyboardButton("🌐 جلب واختيار من مجموعات الحساب", callback_data="fetch_account_groups")],
                [InlineKeyboardButton("➕ إضافة يدوياً", callback_data="add_group"), InlineKeyboardButton("🔄 إيقاف/تفعيل", callback_data="toggle_group_pause")],
                [InlineKeyboardButton("🗑️ تفريغ السوبرات", callback_data="clear_groups")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]
            await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif call.data == "add_group":
            if not is_pro and len(data[user_id].get("groups", [])) >= 5:
                await call.answer("❌ وصلت للحد الأقصى (5 مجموعات). اشترك في Pro!", show_alert=True)
                answered = True
                return
            data[user_id]["state"] = "waiting_for_group"
            await save_data(data)
            await call.message.edit_text("📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):", reply_markup=back_menu())
            
        elif call.data == "toggle_group_pause":
            data[user_id]["state"] = "waiting_for_toggle_group"
            await save_data(data)
            await call.message.edit_text("🔄 أرسل معرف السوبر لإيقافه مؤقتاً أو إعادة تفعيله:", reply_markup=back_menu())

        elif call.data == "show_paused_groups":
            paused = data[user_id].get("paused_groups", [])
            text = f"⏸️ **المجموعات الموقوفة:** (`{len(paused)}`)\n\n"
            for i, g in enumerate(paused, 1):
                text += f"{i}. `{g}`\n"
            await call.message.edit_text(text, reply_markup=back_menu())

        elif call.data == "show_stats":
            stats = data[user_id].get("stats", {"success": 0, "failed": 0})
            text = f"📊 **الإحصائيات:**\n\n✅ ناجحة: `{stats.get('success', 0)}`\n❌ فاشلة: `{stats.get('failed', 0)}`"
            await call.message.edit_text(text, reply_markup=back_menu())

        elif call.data == "clear_groups":
            data[user_id]["groups"] = []
            data[user_id]["paused_groups"] = []
            await save_data(data)
            await call.message.edit_text("🗑️ تم تفريغ السوبرات.", reply_markup=back_menu())

        elif call.data == "show_texts":
            texts = data[user_id].get("texts", [])
            text = f"✉️ **الرسائل المحفوظة:** (`{len(texts)}`)\n\n"
            for i, t in enumerate(texts, 1):
                preview = t[:40] if isinstance(t, str) else f"[{t.get('type')}]"
                text += f"{i}. {preview}\n"
            keyboard = [
                [InlineKeyboardButton("➕ إضافة رسالة جديدة", callback_data="add_text")],
                [InlineKeyboardButton("🗑️ حذف جميع الرسائل", callback_data="clear_texts")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]
            await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif call.data == "add_text":
            data[user_id]["state"] = "waiting_for_text"
            await save_data(data)
            await call.message.edit_text("✍️ أرسل نص الرسالة أو الوسائط (مع إمكانية إضافة زر شفاف):\nمثال:\n`النص هنا | زر - https://t.me/...`", reply_markup=back_menu())
            
        elif call.data == "clear_texts":
            data[user_id]["texts"] = []
            await save_data(data)
            await call.message.edit_text("🗑️ تم حذف الرسائل.", reply_markup=back_menu())

        elif call.data == "set_time":
            data[user_id]["state"] = "waiting_for_time"
            await save_data(data)
            await call.message.edit_text("⏱️ أرسل الفاصل الزمني بالثواني (مثلاً 120):", reply_markup=back_menu())
            
        elif call.data == "start_pub":
            if not data[user_id].get("accounts") or not data[user_id].get("texts") or not data[user_id].get("groups"):
                await call.answer("❌ يجب إضافة حساب، ورسالة، ومجموعة واحدة أولاً!", show_alert=True)
                answered = True
            else:
                data[user_id]["active"] = True
                await save_data(data)
                await call.answer("🟢 تم تفعيل النشر التلقائي بنجاح!", show_alert=True)
                answered = True
                
        elif call.data == "stop_pub":
            data[user_id]["active"] = False
            await save_data(data)
            await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)
            answered = True
    finally:
        if not answered:
            try:
                await call.answer()
            except Exception:
                pass

@app.on_message(~filters.command("start"))
async def message_handler(client, message):
    if not message.from_user:
        return
    user_id = str(message.from_user.id)
    
    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            f"❌ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً!**\n\nرابط القناة: https://t.me/{REQUIRED_CHANNEL.replace('@', '')}",
            reply_markup=subscription_markup()
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)
    is_pro = data.get(user_id, {}).get("is_pro", False)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        return

    if user_id not in data or not data[user_id].get("state"): return
    state = data[user_id]["state"]

    if state == "waiting_for_code":
        code_text = message.text.strip()
        settings = data.setdefault("_settings", {})
        codes = settings.setdefault("codes", {})
        
        if code_text in codes:
            code_data = codes[code_text]
            if code_data["uses"] >= code_data["max_uses"]:
                await message.reply_text("❌ هذا الكود استُخدم بالكامل ووصل للحد الأقصى.")
            elif user_id in code_data.get("used_by", []):
                await message.reply_text("⚠️ لقد قمت باستخدام هذا الكود مسبقاً!")
            else:
                days = code_data.get("days", 30)
                expires_at = time.time() + (days * 86400)
                
                data[user_id]["is_pro"] = True
                data[user_id]["pro_expires_at"] = expires_at
                code_data["uses"] += 1
                code_data.setdefault("used_by", []).append(user_id)
                await save_data(data)
                
                data[user_id]["state"] = None
                await save_data(data)
                await message.reply_text(f"✅ مبروك! تم تفعيل اشتراك Pro بنجاح لمدة {days} يوماً.", reply_markup=main_menu(admin_status, True))
        else:
            await message.reply_text("❌ الكود غير صحيح أو منتهي الصلاحية.")
        return

    elif state == "creating_code":
        if not admin_status: return
        try:
            parts = message.text.split()
            code_str = parts[0]
            days = int(parts[1])
            max_uses = int(parts[2])
            
            settings = data.setdefault("_settings", {})
            codes = settings.setdefault("codes", {})
            codes[code_str] = {
                "days": days,
                "max_uses": max_uses,
                "uses": 0,
                "used_by": []
            }
            await save_data(data)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(f"✅ تم إنشاء الكود `{code_str}` بنجاح لمدة {days} أيام ولـ {max_uses} مستخدمين.", reply_markup=main_menu(admin_status, is_pro))
        except Exception:
            await message.reply_text("❌ الصيغة غير صحيحة. أرسل بالشكل التالي:\n`VIP2026 30 5`")
        return

    elif state == "waiting_for_pro_add_id":
        if not admin_status: return
        target_id = message.text.strip()
        expires_at = time.time() + (30 * 86400)
        if target_id not in data:
            data[target_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": True, "pro_expires_at": expires_at}
        else:
            data[target_id]["is_pro"] = True
            data[target_id]["pro_expires_at"] = expires_at
        await save_data(data)
        await message.reply_text(f"⭐ تمت ترقية المستخدم (`{target_id}`) إلى Pro لمدة 30 يوماً بنجاح!", reply_markup=main_menu(admin_status, is_pro))
        data[user_id]["state"] = None
        await save_data(data)
        return

    elif state == "waiting_for_pro_remove_id":
        if not admin_status: return
        target_id = message.text.strip()
        if target_id in data:
            data[target_id]["is_pro"] = False
            data[target_id]["pro_expires_at"] = 0
            await save_data(data)
            await message.reply_text(f"👤 تم إرجاع المستخدم (`{target_id}`) للباقة المجانية.", reply_markup=main_menu(admin_status, is_pro))
        else:
            await message.reply_text("❌ المستخدم غير مسجل.")
        data[user_id]["state"] = None
        await save_data(data)
        return

    elif state == "waiting_for_admin_broadcast":
        if not admin_status: return
        data[user_id]["state"] = None
        await save_data(data)
        success, failed = 0, 0
        status_msg = await message.reply_text("⏳ جاري الإذاعة...")
        all_users = load_data()
        for target_id in all_users:
            if target_id == "_settings": continue
            try:
                await message.copy(chat_id=int(target_id))
                success += 1
                await asyncio.sleep(0.1)
            except Exception:
                failed += 1
        await status_msg.edit_text(f"✅ تمت الإذاعة!\n- نجح: {success}\n- فشل: {failed}", reply_markup=main_menu(admin_status, is_pro))
        return

    elif state == "waiting_for_ban_user_id":
        if not admin_status: return
        target_id = message.text.strip()
        data[user_id]["state"] = None
        if target_id not in data:
            data[target_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False, "pro_expires_at": 0}
        new_status = not data[target_id].get("banned", False)
        data[target_id]["banned"] = new_status
        await save_data(data)
        msg_res = f"🚫 تم حظر (`{target_id}`)." if new_status else f"🟢 تم إلغاء حظر (`{target_id}`)."
        await message.reply_text(msg_res, reply_markup=main_menu(admin_status, is_pro))
        return

    elif state == "waiting_for_phone":
        temp_client = None
        try:
            temp_client = Client(f"session_{user_id}_{message.text}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await temp_client.connect()
            code_info = await temp_client.send_code(message.text)
            login_attempts[user_id] = {"client": temp_client, "phone": message.text, "hash": code_info.phone_code_hash}
            data[user_id]["state"] = "waiting_for_otp"
            await save_data(data)
            await message.reply_text("📥 أرسل كود التحقق من تيليجرام الآن:")
        except Exception as e:
            if temp_client and temp_client.is_connected:
                try:
                    await temp_client.disconnect()
                except Exception:
                    pass
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        return

    elif state == "waiting_for_otp":
        attempt = login_attempts.get(user_id)
        if not attempt:
            data[user_id]["state"] = None
            await save_data(data)
            return
        try:
            await attempt["client"].sign_in(attempt["phone"], attempt["hash"], message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username or "لا يوجد", "first_name": me.first_name}
            data[user_id]["accounts"].append(account_info)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status, is_pro))
        except SessionPasswordNeeded:
            data[user_id]["state"] = "waiting_for_password"
            await save_data(data)
            await message.reply_text("🔐 أرسل كلمة مرور التحقق بخطوتين:")
            return
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        finally:
            try:
                if attempt.get("client") and attempt["client"].is_connected:
                    await attempt["client"].disconnect()
                if user_id in login_attempts:
                    del login_attempts[user_id]
            except Exception:
                pass
        return

    elif state == "waiting_for_password":
        attempt = login_attempts.get(user_id)
        if not attempt:
            data[user_id]["state"] = None
            await save_data(data)
            return
        try:
            await attempt["client"].check_password(message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username or "لا يوجد", "first_name": me.first_name}
            data[user_id]["accounts"].append(account_info)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        finally:
            try:
                if attempt.get("client") and attempt["client"].is_connected:
                    await attempt["client"].disconnect()
                if user_id in login_attempts:
                    del login_attempts[user_id]
            except Exception:
                pass
        return

    elif state == "waiting_for_group":
        try:
            group_input = normalize_group_id(message.text.strip())
            data[user_id]["groups"].append(group_input)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(f"✅ تم إضافة السوبر: {group_input}", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        return

    elif state == "waiting_for_toggle_group":
        try:
            g_input = normalize_group_id(message.text.strip())
            paused = data[user_id].setdefault("paused_groups", [])
            if g_input in paused:
                paused.remove(g_input)
                msg = f"🟢 أعيد تفعيل: {g_input}"
            else:
                paused.append(g_input)
                msg = f"⏸️ تم إيقاف: {g_input}"
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(msg, reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        return

    elif state == "waiting_for_text":
        try:
            text_content = message.text or message.caption or ""
            btn_text, btn_url = None, None
            
            if "|" in text_content and "-" in text_content:
                parts = text_content.split("|")
                main_text = parts[0].strip()
                btn_part = parts[1].strip()
                if "-" in btn_part:
                    b_name, b_link = btn_part.split("-", 1)
                    btn_text = b_name.strip()
                    btn_url = b_link.strip()
                    text_content = main_text

            if message.text:
                msg_data = {"type": "text", "content": text_content, "btn_text": btn_text, "btn_url": btn_url}
            elif message.photo:
                msg_data = {"type": "photo", "file_id": message.photo.file_id, "caption": text_content, "btn_text": btn_text, "btn_url": btn_url}
            elif message.video:
                msg_data = {"type": "video", "file_id": message.video.file_id, "caption": text_content, "btn_text": btn_text, "btn_url": btn_url}
            else:
                await message.reply_text("❌ أرسل نص، صورة، أو فيديو فقط!")
                return
            
            data[user_id]["texts"].append(msg_data)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text("✅ تم حفظ الرسالة بنجاح.", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        return

    elif state == "waiting_for_time":
        try:
            data[user_id]["delay"] = int(message.text)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text("✅ تم ضبط الوقت.", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ أدخل رقماً صحيحاً: {e}")
            data[user_id]["state"] = None
            await save_data(data)
        return

async def handle_ping(reader, writer):
    try:
        await reader.read(100)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 15\r\n\r\nBot is running!")
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def main():
    port = int(os.environ.get("PORT", 8080))
    server = await asyncio.start_server(handle_ping, '0.0.0.0', port)
    
    await app.start()
    
    if BACKUP_CHAT_ID:
        await restore_config(app)
    
    asyncio.create_task(background_publisher())
    asyncio.create_task(periodic_backup_worker(app))
    
    logging.info("البوت يعمل الآن بنجاح ومحمي بنظام نسخ احتياطي آمن وتلقائي...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
