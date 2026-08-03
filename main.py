import asyncio
import base64
import copy
import hashlib
import json
import logging
import os
import random
import re
import time
from cryptography.fernet import Fernet
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, SessionPasswordNeeded, UserNotParticipant
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# --- إعداد التسجيل والأخطاء ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- معلومات الاتصال والتوكن ---
BOT_TOKEN = "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A"
API_ID = 33057479
API_HASH = "0adc25ac386d50e8ee9f3b987863c4c0"


# تشفير الجلسات
def get_fernet():
    secret = BOT_TOKEN
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_session(val):
    if not val or not isinstance(val, str):
        return val
    try:
        return get_fernet().encrypt(val.encode()).decode()
    except Exception:
        return val


def decrypt_session(val):
    if not val or not isinstance(val, str):
        return val
    try:
        return get_fernet().decrypt(val.encode()).decode()
    except Exception:
        return val


# معالجة النصوص العشوائية لمنع الحظر (Spintax)
def parse_spintax(text):
    if not text:
        return text

    def replace(match):
        options = match.group(1).split("|")
        return random.choice(options)

    pattern = re.compile(r"\{([^{}]+)\}")
    while pattern.search(text):
        text = pattern.sub(replace, text)
    return text


BACKUP_CHAT_ID = "@m_55wa"
if BACKUP_CHAT_ID:
    if str(BACKUP_CHAT_ID).lstrip("-").isdigit():
        BACKUP_CHAT_ID = int(BACKUP_CHAT_ID)
    else:
        if not str(BACKUP_CHAT_ID).startswith("@"):
            BACKUP_CHAT_ID = "@" + str(BACKUP_CHAT_ID).strip()

MAIN_ADMIN_USERNAME = "scofr"
REQUIRED_CHANNEL = "@m_55wa"

app = Client(
    "publisher_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)
DATA_FILE = "users_config.json"
BACKUP_CAPTION = "🔄 نسخة احتياطية تلقائية لملف الإعدادات (مشفرة وآمنة)"
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
        data_to_save = copy.deepcopy(data)

        for uid, udata in data_to_save.items():
            if uid == "_settings":
                continue
            if isinstance(udata, dict) and "accounts" in udata:
                for acc in udata["accounts"]:
                    if "session_string" in acc and acc["session_string"]:
                        acc["session_string"] = encrypt_session(
                            acc["session_string"]
                        )

        temp_file = DATA_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
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
        default_data = {
            "_settings": {"developers": [], "codes": {}, "buttons": {}}
        }
        _memory_cache = default_data
        return default_data

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "_settings" not in data:
                data["_settings"] = {
                    "developers": [],
                    "codes": {},
                    "buttons": {},
                }

            current_time = time.time()
            for uid, udata in data.items():
                if uid == "_settings":
                    continue
                if isinstance(udata, dict):
                    udata.setdefault("accounts", [])
                    udata.setdefault("texts", [])
                    udata.setdefault("groups", [])
                    udata.setdefault("paused_groups", [])
                    udata.setdefault(
                        "stats",
                        {"success": 0, "failed": 0, "last_error": "لا يوجد"},
                    )
                    udata.setdefault("banned", False)
                    udata.setdefault("is_pro", False)
                    udata.setdefault("pro_expires_at", 0)

                    for acc in udata["accounts"]:
                        if "session_string" in acc and acc["session_string"]:
                            acc["session_string"] = decrypt_session(
                                acc["session_string"]
                            )

                    if udata.get("is_pro", False) and udata.get(
                        "pro_expires_at", 0
                    ) > 0:
                        if current_time > udata["pro_expires_at"]:
                            udata["is_pro"] = False
                            udata["pro_expires_at"] = 0
            _memory_cache = data
            return data
    except Exception:
        if _memory_cache is not None:
            return _memory_cache
        return {"_settings": {"developers": [], "codes": {}, "buttons": {}}}


def normalize_group_id(g):
    if not g:
        return ""
    g_str = str(g).strip()
    if "https://t.me/" in g_str:
        g_str = g_str.split("https://t.me/")[-1].strip("/")
    elif "t.me/" in g_str:
        g_str = g_str.split("t.me/")[-1].strip("/")

    if (
        g_str.startswith("+")
        or g_str.startswith("@")
        or (g_str.startswith("-") and g_str[1:].isdigit())
        or g_str.isdigit()
    ):
        return g_str
    return "@" + g_str


async def restore_config(client):
    if not BACKUP_CHAT_ID:
        return
    try:
        await client.get_chat(BACKUP_CHAT_ID)
        if not os.path.exists(DATA_FILE):
            backups = []
            async for message in client.get_chat_history(
                BACKUP_CHAT_ID, limit=50
            ):
                if (
                    message.document
                    and message.document.file_name == DATA_FILE
                ):
                    backups.append(message)
            if backups:
                backups.sort(key=lambda m: m.id, reverse=True)
                latest_backup = backups[0]
                await latest_backup.download(file_name=DATA_FILE)
    except Exception:
        pass


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
                caption=BACKUP_CAPTION,
            )
            try:
                async for message in client.get_chat_history(
                    BACKUP_CHAT_ID, limit=20
                ):
                    if (
                        message.id != sent_msg.id
                        and message.document
                        and message.document.file_name == DATA_FILE
                        and message.caption == BACKUP_CAPTION
                    ):
                        await client.delete_messages(
                            BACKUP_CHAT_ID, message.id
                        )
            except Exception:
                pass
        else:
            data_changed = False
    except Exception:
        data_changed = True


async def periodic_backup_worker(client):
    global data_changed
    while True:
        await asyncio.sleep(60)
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
        if member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.RESTRICTED,
        ]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception:
        return True


# --- الأزرار المنظمة والمبسطة (من الأهم للأقل أهمية) ---
def main_menu(is_admin_user=False, is_pro=False):
    pro_badge = " ⭐ [Pro]" if is_pro else " 👤 [مجاني]"
    keyboard = [
        # 1. التحكم الأهم في القمة (تشغيل / إيقاف)
        [
            InlineKeyboardButton("🟢 بدء النشر", callback_data="start_pub"),
            InlineKeyboardButton("🔴 إيقاف النشر", callback_data="stop_pub"),
        ],
        # 2. أصول إدارة النشر الرئيسية
        [
            InlineKeyboardButton(
                f"👤 حساباتي{pro_badge}", callback_data="show_accounts"
            ),
            InlineKeyboardButton("👥 السوبرات", callback_data="show_groups"),
        ],
        [
            InlineKeyboardButton("✉️ الرسائل", callback_data="show_texts"),
            InlineKeyboardButton("⏱️ الفاصل الزمني", callback_data="set_time"),
        ],
        # 3. التقارير والمميزات الذكية
        [
            InlineKeyboardButton(
                "📊 الإحصائيات والسجلات", callback_data="show_stats"
            ),
            InlineKeyboardButton(
                "🛡️ منع الحظر (Spintax)", callback_data="spintax_info"
            ),
        ],
        # 4. الترقية والتعليمات
        [
            InlineKeyboardButton(
                "🎟️ كود Pro", callback_data="redeem_code_prompt"
            ),
            InlineKeyboardButton(
                "📖 الشرح والتعليمات", callback_data="bot_guide"
            ),
        ],
        # 5. الدعم والأدمن في الأسفل تماماً
        [
            InlineKeyboardButton(
                "👑 ترقية لـ Pro / الدعم",
                url=f"https://t.me/{MAIN_ADMIN_USERNAME}",
            )
        ],
    ]

    if is_admin_user:
        keyboard.insert(
            0,
            [
                InlineKeyboardButton(
                    "🛠️ لوحة الأدمن الخاصة", callback_data="admin_panel"
                )
            ],
        )

    return InlineKeyboardMarkup(keyboard)


def back_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_main")]]
    )


def subscription_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 اشترك في القناة",
                url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}",
            )
        ],
        [
            InlineKeyboardButton(
                "✅ لقد اشتركت، تحقق الآن", callback_data="check_subscription"
            )
        ],
    ])


async def render_groups_page(message, user_id, data, is_pro):
    groups_list = account_groups_cache.get(user_id, [])
    user_groups = data[user_id].get("groups", [])
    keyboard = []
    for idx, g in enumerate(groups_list[:20]):
        g_identifier = normalize_group_id(
            g["username"] if not g["id"].startswith("-100") else g["id"]
        )
        is_added = g_identifier in user_groups or g["id"] in user_groups
        btn_text = "🗑️ حذف" if is_added else "➕ إضافة"
        callback_val = f"tg_rem_{idx}" if is_added else f"tg_add_{idx}"
        keyboard.append([
            InlineKeyboardButton(g["title"], callback_data="none_click"),
            InlineKeyboardButton(btn_text, callback_data=callback_val),
        ])
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع لقائمة السوبرات", callback_data="show_groups")
    ])
    text = f"🌐 **مجموعات حسابك (تم العثور على {len(groups_list)}):**\nاختر المجموعات التي تريد إضافتها للنشر:"
    try:
        await message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
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
            in_memory=True,
        )
        await client.connect()
        client_pool[pool_key] = client
        return client
    except Exception:
        return None


# --- معالجة النشر المتوازي الفعال لكل مستخدم ---
async def process_user_publishing(user_id, u_data):
    delay = u_data.get("delay", 120)
    accounts = u_data.get("accounts", [])
    texts = u_data.get("texts", [])
    groups = u_data.get("groups", [])
    paused_groups = u_data.get("paused_groups", [])

    active_accounts = accounts if u_data.get("is_pro") else accounts[:1]
    updated = False

    for acc in active_accounts:
        user_client = await get_or_create_client(user_id, acc)
        if not user_client:
            continue

        for group in groups:
            norm_group = normalize_group_id(group)
            if norm_group in paused_groups or group in paused_groups:
                continue

            try:
                target_chat = (
                    int(group)
                    if (group.isdigit() or (group.startswith("-") and group[1:].isdigit()))
                    else group
                )
            except Exception:
                target_chat = group

            for t_item in texts:
                try:
                    markup = None
                    if (
                        isinstance(t_item, dict)
                        and t_item.get("btn_text")
                        and t_item.get("btn_url")
                    ):
                        markup = InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                t_item.get("btn_text"), url=t_item.get("btn_url")
                            )
                        ]])

                    if isinstance(t_item, str):
                        final_text = parse_spintax(t_item)
                        await user_client.send_message(target_chat, final_text)
                    else:
                        m_type = t_item.get("type")
                        content = parse_spintax(t_item.get("content", ""))
                        caption = parse_spintax(t_item.get("caption", ""))

                        if m_type == "text":
                            await user_client.send_message(
                                target_chat, content, reply_markup=markup
                            )
                        elif m_type == "photo":
                            await user_client.send_photo(
                                target_chat,
                                t_item.get("file_id"),
                                caption=caption,
                                reply_markup=markup,
                            )
                        elif m_type == "video":
                            await user_client.send_video(
                                target_chat,
                                t_item.get("file_id"),
                                caption=caption,
                                reply_markup=markup,
                            )

                    u_data["stats"]["success"] = (
                        u_data["stats"].get("success", 0) + 1
                    )
                    updated = True
                    await asyncio.sleep(3)
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except Exception as err_exp:
                    u_data["stats"]["failed"] = (
                        u_data["stats"].get("failed", 0) + 1
                    )
                    u_data["stats"]["last_error"] = str(err_exp)[:40]
                    updated = True

    if updated:
        all_data = load_data()
        all_data[user_id] = u_data
        await save_data(all_data)


async def background_publisher():
    while True:
        await asyncio.sleep(10)
        try:
            data = load_data()
            tasks = []
            for user_id, u_data in data.items():
                if user_id == "_settings":
                    continue
                if (
                    u_data.get("active")
                    and u_data.get("accounts")
                    and u_data.get("groups")
                    and u_data.get("texts")
                ):
                    tasks.append(process_user_publishing(user_id, u_data))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass


@app.on_message(filters.command("start"))
async def start_command(client, message):
    if not message.from_user:
        return
    user_id = str(message.from_user.id)

    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            f"❌ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً!**\n\nالقناة: https://t.me/{REQUIRED_CHANNEL.replace('@', '')}",
            reply_markup=subscription_markup(),
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        await message.reply_text("❌ عذراً، لقد تم حظرك من استخدام هذا البوت.")
        return

    if user_id not in data:
        data[user_id] = {
            "groups": [],
            "paused_groups": [],
            "delay": 120,
            "active": False,
            "accounts": [],
            "texts": [],
            "stats": {"success": 0, "failed": 0, "last_error": "لا يوجد"},
            "state": None,
            "banned": False,
            "is_pro": False,
            "pro_expires_at": 0,
        }
    else:
        for key in ["accounts", "texts", "groups", "paused_groups"]:
            if key not in data[user_id]:
                data[user_id][key] = []
        if "stats" not in data[user_id]:
            data[user_id]["stats"] = {
                "success": 0,
                "failed": 0,
                "last_error": "لا يوجد",
            }

    data[user_id]["state"] = None
    await save_data(data)

    is_pro = data[user_id].get("is_pro", False)
    welcome_text = f"أهلاً بك يا {message.from_user.first_name} 👋\nفي لوحة تحكم بوت النشر التلقائي."

    if is_pro:
        welcome_text += "\n\n⭐ اشتراكك: **باقة Pro المدفوعة**"
    else:
        welcome_text += "\n\n👤 اشتراكك: **الباقة المجانية** (حساب واحد + 5 مجموعات)"

    await message.reply_text(
        welcome_text, reply_markup=main_menu(admin_status, is_pro)
    )


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
                await call.answer(
                    "✅ تم التحقق من اشتراكك بنجاح!", show_alert=True
                )
                answered = True
                await call.message.edit_text(
                    "إليك لوحة التحكم:",
                    reply_markup=main_menu(admin_status, is_pro),
                )
            else:
                await call.answer(
                    "❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True
                )
                answered = True
            return

        if call.data == "none_click":
            await call.answer()
            answered = True
            return

        if call.data.startswith("tg_add_") or call.data.startswith("tg_rem_"):
            data = load_data()
            is_pro = data.get(user_id, {}).get("is_pro", False)
            try:
                parts = call.data.split("_")
                action = parts[1]
                idx = int(parts[2])
                groups_list = account_groups_cache.get(user_id, [])
                if idx < len(groups_list):
                    g = groups_list[idx]
                    g_target = normalize_group_id(
                        g["username"]
                        if not g["id"].startswith("-100")
                        else g["id"]
                    )

                    if action == "add":
                        if (
                            not is_pro
                            and len(data[user_id].get("groups", [])) >= 5
                        ):
                            await call.answer(
                                "❌ وصلت للحد الأقصى في الباقة المجانية (5 مجموعات).",
                                show_alert=True,
                            )
                            answered = True
                            return
                        if g_target not in data[user_id]["groups"]:
                            data[user_id]["groups"].append(g_target)
                            await save_data(data)
                        await call.answer(
                            "✅ تمت إضافة المجموعة", show_alert=True
                        )
                        answered = True
                    elif action == "rem":
                        if g_target in data[user_id]["groups"]:
                            data[user_id]["groups"].remove(g_target)
                            await save_data(data)
                        await call.answer(
                            "🗑️ تمت إزالة المجموعة", show_alert=True
                        )
                        answered = True

                    if user_id in account_groups_cache:
                        await render_groups_page(
                            call.message, user_id, data, is_pro
                        )
                return
            except Exception:
                await call.answer("❌ حدث خطأ", show_alert=True)
                answered = True
                return

        if not await is_subscribed(client, call.from_user.id):
            await call.answer(
                "❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True
            )
            answered = True
            return

        data = load_data()
        if user_id not in data:
            data[user_id] = {
                "groups": [],
                "paused_groups": [],
                "delay": 120,
                "active": False,
                "accounts": [],
                "texts": [],
                "stats": {"success": 0, "failed": 0, "last_error": "لا يوجد"},
                "state": None,
                "banned": False,
                "is_pro": False,
                "pro_expires_at": 0,
            }

        is_pro = data[user_id].get("is_pro", False)

        if data.get(user_id, {}).get("banned", False) and not admin_status:
            await call.answer("❌ عذراً، تم حظرك من البوت.", show_alert=True)
            answered = True
            return

        if call.data == "back_main":
            data[user_id]["state"] = None
            await save_data(data)
            await call.message.edit_text(
                "إليك لوحة التحكم الرئيسية:",
                reply_markup=main_menu(admin_status, is_pro),
            )

        elif call.data == "spintax_info":
            info_text = (
                "🛡️ **نظام منع الحظر الذكي (Spintax):**\n\n"
                "يمكنك استخدام الأقواس `{}` مع الفواصل `|` لجعل البوت يختار كلمات عشوائية في كل مرة ينشر فيها!\n\n"
                "📌 **مثال للرسالة:**\n"
                "`{أهلاً|مرحباً|السلام عليكم} يسعدنا تقديم {خدماتنا|منتجاتنا}`\n\n"
                "💡 سيقوم البوت بالتنويع الذكي تلقائياً لمنع حظر حساباتك من تيليجرام."
            )
            await call.message.edit_text(info_text, reply_markup=back_menu())

        elif call.data == "bot_guide":
            guide_text = (
                "📖 **دليل الاستخدام السريع:**\n\n"
                "1️⃣ **إضافة حساب:** اضغط على (حساباتي) ثم ربط حسابك برقم الهاتف.\n"
                "2️⃣ **إضافة مجموعات:** اضغط على (السوبرات) وجلب المجموعات أو إضافتها يدويًا.\n"
                "3️⃣ **إضافة الرسالة:** اضغط على (الرسائل) وأرسل النص أو الميديا.\n"
                "4️⃣ **بدء النشر:** اضغط زر (🟢 بدء النشر) في الأعلى."
            )
            await call.message.edit_text(guide_text, reply_markup=back_menu())

        elif call.data == "redeem_code_prompt":
            data[user_id]["state"] = "waiting_for_code"
            await save_data(data)
            await call.message.edit_text(
                "🎟️ أرسل كود التفعيل الخاص بـ Pro الآن:", reply_markup=back_menu()
            )

        elif call.data == "fetch_account_groups":
            accounts = data[user_id].get("accounts", [])
            if not accounts:
                await call.answer(
                    "❌ يجب إضافة حساب أولاً لجلب المجموعات!", show_alert=True
                )
                answered = True
                return
            await call.answer(
                "⏳ جاري جلب مجموعات حسابك من تيليجرام...", show_alert=True
            )
            answered = True
            acc = accounts[0]
            session_str = acc.get("session_string")
            try:
                groups_list = []
                async with Client(
                    f"fetcher_{user_id}_{acc.get('id')}",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    session_string=session_str,
                    in_memory=True,
                ) as temp_client:
                    async for dialog in temp_client.get_dialogs():
                        if dialog.chat.type in [
                            ChatType.GROUP,
                            ChatType.SUPERGROUP,
                        ]:
                            groups_list.append({
                                "id": str(dialog.chat.id),
                                "title": dialog.chat.title[:25],
                                "username": f"@{dialog.chat.username}"
                                if dialog.chat.username
                                else str(dialog.chat.id),
                            })

                if not groups_list:
                    await call.message.edit_text(
                        "❌ لم يتم العثور على أي مجموعات.", reply_markup=back_menu()
                    )
                    return

                account_groups_cache[user_id] = groups_list
                await render_groups_page(call.message, user_id, data, is_pro)
            except Exception:
                await call.message.edit_text(
                    "❌ حدث خطأ أثناء جلب المجموعات.", reply_markup=back_menu()
                )

        elif call.data == "show_accounts":
            accs = data[user_id].get("accounts", [])
            text = f"👤 **حساباتك المربوطة:** (`{len(accs)}`)\n\n"
            for i, acc in enumerate(accs, 1):
                text += f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "➕ إضافة حساب جديد", callback_data="add_account"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ حذف جميع الحسابات", callback_data="clear_accounts"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع للقائمة", callback_data="back_main"
                    )
                ],
            ]
            await call.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif call.data == "add_account":
            if not is_pro and len(data[user_id].get("accounts", [])) >= 1:
                await call.answer(
                    "❌ الباقة المجانية تسمح بحساب واحد فقط! اشترك في Pro للزيادة.",
                    show_alert=True,
                )
                answered = True
                return
            data[user_id]["state"] = "waiting_for_phone"
            await save_data(data)
            await call.message.edit_text(
                "📱 أرسل رقم هاتفك مع رمز الدولة (مثال: `+9665xxxxxxx`):",
                reply_markup=back_menu(),
            )

        elif call.data == "clear_accounts":
            data[user_id]["accounts"] = []
            await save_data(data)
            await call.message.edit_text(
                "🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu()
            )

        elif call.data == "show_groups":
            groups = data[user_id].get("groups", [])
            paused = data[user_id].get("paused_groups", [])
            text = f"👥 **المجموعات المستهدفة:** (`{len(groups)}`)\n\n"
            for i, g in enumerate(groups, 1):
                status = "⏸️ (موقوفة)" if g in paused else "🟢 (نشطة)"
                text += f"{i}. `{g}` - {status}\n"

            # منظم بدون فوضى
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🌐 جلب من حسابك", callback_data="fetch_account_groups"
                    ),
                    InlineKeyboardButton(
                        "➕ إضافة يدوياً", callback_data="add_group"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⏸️ إيقاف/تفعيل مجموعة",
                        callback_data="toggle_group_pause",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ حذف الكل", callback_data="clear_groups"
                    ),
                    InlineKeyboardButton(
                        "🔙 رجوع", callback_data="back_main"
                    ),
                ],
            ]
            await call.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif call.data == "add_group":
            if not is_pro and len(data[user_id].get("groups", [])) >= 5:
                await call.answer(
                    "❌ وصلت للحد الأقصى (5 مجموعات).", show_alert=True
                )
                answered = True
                return
            data[user_id]["state"] = "waiting_for_group"
            await save_data(data)
            await call.message.edit_text(
                "📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):",
                reply_markup=back_menu(),
            )

        elif call.data == "toggle_group_pause":
            data[user_id]["state"] = "waiting_for_toggle_group"
            await save_data(data)
            await call.message.edit_text(
                "🔄 أرسل معرف السوبر لإيقافه مؤقتاً أو إعادة تفعيله:",
                reply_markup=back_menu(),
            )

        elif call.data == "show_stats":
            stats = data[user_id].get(
                "stats", {"success": 0, "failed": 0, "last_error": "لا يوجد"}
            )
            status_str = (
                "🟢 نشط الآن" if data[user_id].get("active") else "🔴 متوقف"
            )
            text = (
                f"📊 **إحصائيات وحالة النشر:**\n\n"
                f"الحالة: {status_str}\n"
                f"✅ منشورات ناجحة: `{stats.get('success', 0)}`\n"
                f"❌ محاولات فاشلة: `{stats.get('failed', 0)}`\n"
                f"⚠️ آخر خطأ: `{stats.get('last_error', 'لا يوجد')}`"
            )
            await call.message.edit_text(text, reply_markup=back_menu())

        elif call.data == "clear_groups":
            data[user_id]["groups"] = []
            data[user_id]["paused_groups"] = []
            await save_data(data)
            await call.message.edit_text(
                "🗑️ تم تفريغ قائمة المجموعات.", reply_markup=back_menu()
            )

        elif call.data == "show_texts":
            texts = data[user_id].get("texts", [])
            text = f"✉️ **الرسائل المحفوظة:** (`{len(texts)}`)\n\n"
            for i, t in enumerate(texts, 1):
                preview = (
                    t[:40] if isinstance(t, str) else f"[{t.get('type')}]"
                )
                text += f"{i}. {preview}\n"
            keyboard = [
                [
                    InlineKeyboardButton(
                        "➕ إضافة رسالة جديدة", callback_data="add_text"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ حذف الرسائل", callback_data="clear_texts"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع", callback_data="back_main"
                    )
                ],
            ]
            await call.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif call.data == "add_text":
            data[user_id]["state"] = "waiting_for_text"
            await save_data(data)
            await call.message.edit_text(
                "✍️ أرسل نص الرسالة (يدعم Spintax `{كلمة1|كلمة2}` والزر الشفاف):\nمثال:\n`مرحباً | رابط - https://t.me/...`",
                reply_markup=back_menu(),
            )

        elif call.data == "clear_texts":
            data[user_id]["texts"] = []
            await save_data(data)
            await call.message.edit_text(
                "🗑️ تم حذف جميع الرسائل.", reply_markup=back_menu()
            )

        elif call.data == "set_time":
            data[user_id]["state"] = "waiting_for_time"
            await save_data(data)
            await call.message.edit_text(
                "⏱️ أرسل الفاصل الزمني بالثواني (مثلاً 120):",
                reply_markup=back_menu(),
            )

        elif call.data == "start_pub":
            if (
                not data[user_id].get("accounts")
                or not data[user_id].get("texts")
                or not data[user_id].get("groups")
            ):
                await call.answer(
                    "❌ يجب إضافة (حساب + رسالة + مجموعة) على الأقل!",
                    show_alert=True,
                )
                answered = True
            else:
                data[user_id]["active"] = True
                await save_data(data)
                await call.answer(
                    "🟢 تم تفعيل النشر التلقائي بنجاح!", show_alert=True
                )
                answered = True

        elif call.data == "stop_pub":
            data[user_id]["active"] = False
            await save_data(data)
            await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)
            answered = True

        elif call.data == "admin_panel":
            if not admin_status:
                return
            admin_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📊 الإحصائيات العامة",
                        callback_data="admin_member_count",
                    ),
                    InlineKeyboardButton(
                        "📢 إذاعة لكل الأعضاء", callback_data="admin_broadcast"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⭐ إدارة Pro", callback_data="admin_pro_management"
                    ),
                    InlineKeyboardButton(
                        "🎟️ إنشاء كود Pro", callback_data="admin_create_code"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🚫 حظر/إلغاء حظر", callback_data="admin_ban_user"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع للقائمة الرئيسية", callback_data="back_main"
                    )
                ],
            ])
            await call.message.edit_text(
                "👑 **لوحة تحكم الأدمن:**", reply_markup=admin_kb
            )

        elif call.data == "admin_create_code":
            if not admin_status:
                return
            data[user_id]["state"] = "creating_code"
            await save_data(data)
            await call.message.edit_text(
                "🎟️ أرسل الكود بهذا الشكل:\n`VIPCODE 30 5`\n(اسم الكود ثم عدد الأيام ثم المستفيدين)",
                reply_markup=back_menu(),
            )

        elif call.data == "admin_pro_management":
            if not admin_status:
                return
            pro_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ تفعيل Pro", callback_data="add_pro_user"
                    ),
                    InlineKeyboardButton(
                        "❌ إزالة Pro", callback_data="remove_pro_user"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "📋 قائمة المشتركين", callback_data="list_pro_users"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 رجوع للأدمن", callback_data="admin_panel"
                    )
                ],
            ])
            await call.message.edit_text(
                "⭐ **إدارة اشتراكات Pro:**", reply_markup=pro_kb
            )

        elif call.data == "add_pro_user":
            if not admin_status:
                return
            data[user_id]["state"] = "waiting_for_pro_add_id"
            await save_data(data)
            await call.message.edit_text(
                "➕ أرسل آيدي المستخدم لمنحه Pro:", reply_markup=back_menu()
            )

        elif call.data == "remove_pro_user":
            if not admin_status:
                return
            data[user_id]["state"] = "waiting_for_pro_remove_id"
            await save_data(data)
            await call.message.edit_text(
                "❌ أرسل آيدي المستخدم لإرجاعه للمجاني:", reply_markup=back_menu()
            )

        elif call.data == "list_pro_users":
            if not admin_status:
                return
            all_u = load_data()
            pro_list = [
                uid
                for uid, uval in all_u.items()
                if uid != "_settings"
                and isinstance(uval, dict)
                and uval.get("is_pro")
            ]
            text = f"⭐ **مشتركو Pro:** (`{len(pro_list)}`)\n\n"
            for i, pid in enumerate(pro_list, 1):
                text += f"{i}. `{pid}`\n"
            await call.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🔙 رجوع", callback_data="admin_pro_management"
                    )
                ]]),
            )

        elif call.data == "admin_member_count":
            if not admin_status:
                return
            count = len([uid for uid in load_data() if uid != "_settings"])
            await call.answer(
                f"📊 إجمالي أعضاء البوت: {count}", show_alert=True
            )
            answered = True

        elif call.data == "admin_broadcast":
            if not admin_status:
                return
            data[user_id]["state"] = "waiting_for_admin_broadcast"
            await save_data(data)
            await call.message.edit_text(
                "📢 أرسل نص أو ميديا الإذاعة الآن:", reply_markup=back_menu()
            )

        elif call.data == "admin_ban_user":
            if not admin_status:
                return
            data[user_id]["state"] = "waiting_for_ban_user_id"
            await save_data(data)
            await call.message.edit_text(
                "🚫 أرسل آيدي المستخدم للحظر/إلغاء الحظر:",
                reply_markup=back_menu(),
            )

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
            f"❌ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً!**",
            reply_markup=subscription_markup(),
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)
    is_pro = data.get(user_id, {}).get("is_pro", False)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        return

    if user_id not in data or not data[user_id].get("state"):
        return
    state = data[user_id]["state"]

    if state == "waiting_for_time":
        if message.text and message.text.isdigit():
            val = int(message.text)
            if val < 10:
                val = 10
            data[user_id]["delay"] = val
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(
                f"⏱️ تم تحديد الفاصل الزمني بـ {val} ثانية.",
                reply_markup=main_menu(admin_status, is_pro),
            )
        else:
            await message.reply_text("❌ أرسل أرقاماً فقط!")
        return

    elif state == "waiting_for_code":
        code_text = message.text.strip()
        settings = data.setdefault("_settings", {})
        codes = settings.setdefault("codes", {})

        if code_text in codes:
            code_data = codes[code_text]
            if code_data["uses"] >= code_data["max_uses"]:
                await message.reply_text(
                    "❌ هذا الكود استُخدم بالكامل ووصل للحد الأقصى."
                )
            elif user_id in code_data.get("used_by", []):
                await message.reply_text(
                    "⚠️ لقد قمت باستخدام هذا الكود مسبقاً!"
                )
            else:
                days = code_data.get("days", 30)
                expires_at = time.time() + (days * 86400)

                data[user_id]["is_pro"] = True
                data[user_id]["pro_expires_at"] = expires_at
                code_data["uses"] += 1
                code_data.setdefault("used_by", []).append(user_id)
                data[user_id]["state"] = None
                await save_data(data)

                await message.reply_text(
                    f"✅ مبروك! تم تفعيل اشتراك Pro بنجاح لمدة {days} يوماً.",
                    reply_markup=main_menu(admin_status, True),
                )
        else:
            await message.reply_text("❌ الكود غير صحيح أو منتهي الصلاحية.")
        return

    elif state == "creating_code":
        if not admin_status:
            return
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
                "used_by": [],
            }
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(
                f"✅ تم إنشاء الكود `{code_str}` بنجاح لمدة {days} أيام ولـ {max_uses} مستخدمين.",
                reply_markup=main_menu(admin_status, is_pro),
            )
        except Exception:
            await message.reply_text(
                "❌ الصيغة غير صحيحة. أرسل بالشكل التالي:\n`VIP2026 30 5`"
            )
        return

    elif state == "waiting_for_pro_add_id":
        if not admin_status:
            return
        target_id = message.text.strip()
        expires_at = time.time() + (30 * 86400)
        if target_id not in data:
            data[target_id] = {
                "groups": [],
                "paused_groups": [],
                "delay": 120,
                "active": False,
                "accounts": [],
                "texts": [],
                "stats": {"success": 0, "failed": 0, "last_error": "لا يوجد"},
                "state": None,
                "banned": False,
                "is_pro": True,
                "pro_expires_at": expires_at,
            }
        else:
            data[target_id]["is_pro"] = True
            data[target_id]["pro_expires_at"] = expires_at
        data[user_id]["state"] = None
        await save_data(data)
        await message.reply_text(
            f"⭐ تمت ترقية المستخدم (`{target_id}`) إلى Pro لمدة 30 يوماً بنجاح!",
            reply_markup=main_menu(admin_status, is_pro),
        )
        return

    elif state == "waiting_for_pro_remove_id":
        if not admin_status:
            return
        target_id = message.text.strip()
        if target_id in data:
            data[target_id]["is_pro"] = False
            data[target_id]["pro_expires_at"] = 0
            await save_data(data)
            await message.reply_text(
                f"👤 تم إرجاع المستخدم (`{target_id}`) للباقة المجانية.",
                reply_markup=main_menu(admin_status, is_pro),
            )
        else:
            await message.reply_text("❌ المستخدم غير مسجل.")
        data[user_id]["state"] = None
        await save_data(data)
        return

    elif state == "waiting_for_admin_broadcast":
        if not admin_status:
            return
        data[user_id]["state"] = None
        await save_data(data)
        success, failed = 0, 0
        status_msg = await message.reply_text("⏳ جاري الإذاعة...")
        all_users = load_data()
        for target_id in all_users:
            if target_id == "_settings":
                continue
            try:
                await message.copy(chat_id=int(target_id))
                success += 1
                await asyncio.sleep(0.1)
            except Exception:
                failed += 1
        await status_msg.edit_text(
            f"✅ تمت الإذاعة!\n- نجح: {success}\n- فشل: {failed}",
            reply_markup=main_menu(admin_status, is_pro),
        )
        return

    elif state == "waiting_for_ban_user_id":
        if not admin_status:
            return
        target_id = message.text.strip()
        data[user_id]["state"] = None
        if target_id not in data:
            data[target_id] = {
                "groups": [],
                "paused_groups": [],
                "delay": 120,
                "active": False,
                "accounts": [],
                "texts": [],
                "stats": {"success": 0, "failed": 0, "last_error": "لا يوجد"},
                "state": None,
                "banned": False,
                "is_pro": False,
                "pro_expires_at": 0,
            }
        new_status = not data[target_id].get("banned", False)
        data[target_id]["banned"] = new_status
        await save_data(data)
        msg_res = (
            f"🚫 تم حظر (`{target_id}`)."
            if new_status
            else f"🟢 تم إلغاء حظر (`{target_id}`)."
        )
        await message.reply_text(
            msg_res, reply_markup=main_menu(admin_status, is_pro)
        )
        return

    elif state == "waiting_for_phone":
        temp_client = None
        try:
            temp_client = Client(
                f"session_{user_id}_{message.text}",
                api_id=API_ID,
                api_hash=API_HASH,
                in_memory=True,
            )
            await temp_client.connect()
            code_info = await temp_client.send_code(message.text)
            login_attempts[user_id] = {
                "client": temp_client,
                "phone": message.text,
                "hash": code_info.phone_code_hash,
            }
            data[user_id]["state"] = "waiting_for_otp"
            await save_data(data)
            await message.reply_text("📥 أرسل كود التحقق الآن:")
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
            await message.reply_text(
                "❌ انتهت الجلسة، حاول مجدداً.",
                reply_markup=main_menu(admin_status, is_pro),
            )
            return
        try:
            await attempt["client"].sign_in(
                attempt["phone"], attempt["hash"], message.text
            )
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {
                "session_string": session_str,
                "id": me.id,
                "username": me.username or "لا يوجد",
                "first_name": me.first_name,
            }
            data[user_id]["accounts"].append(account_info)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(
                "✅ تم ربط الحساب بنجاح!",
                reply_markup=main_menu(admin_status, is_pro),
            )
            if attempt.get("client") and attempt["client"].is_connected:
                await attempt["client"].disconnect()
            if user_id in login_attempts:
                del login_attempts[user_id]
        except SessionPasswordNeeded:
            data[user_id]["state"] = "waiting_for_password"
            await save_data(data)
            await message.reply_text("🔐 أرسل كلمة مرور التحقق بخطوتين:")
            return
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            await save_data(data)
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
            await message.reply_text(
                "❌ انتهت الجلسة، حاول مجدداً.",
                reply_markup=main_menu(admin_status, is_pro),
            )
            return
        try:
            await attempt["client"].check_password(message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {
                "session_string": session_str,
                "id": me.id,
                "username": me.username or "لا يوجد",
                "first_name": me.first_name,
            }
            data[user_id]["accounts"].append(account_info)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(
                "✅ تم ربط الحساب بنجاح!",
                reply_markup=main_menu(admin_status, is_pro),
            )
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
            groups_list = data[user_id].setdefault("groups", [])

            if not is_pro and len(groups_list) >= 5:
                await message.reply_text(
                    "❌ وصلت للحد الأقصى في الباقة المجانية (5 مجموعات).",
                    reply_markup=main_menu(admin_status, is_pro),
                )
                data[user_id]["state"] = None
                await save_data(data)
                return

            if group_input in groups_list:
                await message.reply_text(
                    "⚠️ هذه المجموعة مضافة مسبقاً!",
                    reply_markup=main_menu(admin_status, is_pro),
                )
            else:
                groups_list.append(group_input)
                await message.reply_text(
                    f"✅ تمت إضافة السوبر: {group_input}",
                    reply_markup=main_menu(admin_status, is_pro),
                )

            data[user_id]["state"] = None
            await save_data(data)
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
            await message.reply_text(
                msg, reply_markup=main_menu(admin_status, is_pro)
            )
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
                msg_data = {
                    "type": "text",
                    "content": text_content,
                    "btn_text": btn_text,
                    "btn_url": btn_url,
                }
            elif message.photo:
                msg_data = {
                    "type": "photo",
                    "file_id": message.photo.file_id,
                    "caption": text_content,
                    "btn_text": btn_text,
                    "btn_url": btn_url,
                }
            elif message.video:
                msg_data = {
                    "type": "video",
                    "file_id": message.video.file_id,
                    "caption": text_content,
                    "btn_text": btn_text,
                    "btn_url": btn_url,
                }
            else:
                await message.reply_text("❌ أرسل نص، صورة، أو فيديو فقط!")
                return

            data[user_id]["texts"].append(msg_data)
            data[user_id]["state"] = None
            await save_data(data)
            await message.reply_text(
                "✅ تم حفظ الرسالة بنجاح.",
                reply_markup=main_menu(admin_status, is_pro),
            )
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")


async def main():
    await app.start()
    await restore_config(app)
    asyncio.create_task(periodic_backup_worker(app))
    asyncio.create_task(background_publisher())
    logging.info("تم تشغيل البوت بنجاح!")
    await idle()
    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
