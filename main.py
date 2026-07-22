import os
import json
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, UserNotParticipant
from pyrogram.enums import ChatMemberStatus

# --- الإعدادات ---
BOT_TOKEN = "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A"
API_ID = 33057479
API_HASH = "0adc25ac386d50e8ee9f3b987863c4c0"
ADMIN_USERNAME = "scofr"
REQUIRED_CHANNEL = "@m_55wa"  # قناة الاشتراك الإجباري

app = Client("publisher_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
DATA_FILE = "users_config.json"
login_attempts = {}

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: 
        try:
            data = json.load(f)
            for uid, udata in data.items():
                if uid == "_settings": continue
                if isinstance(udata, dict):
                    if "accounts" not in udata: udata["accounts"] = []
                    if "texts" not in udata: udata["texts"] = []
                    if "groups" not in udata: udata["groups"] = []
                    if "banned" not in udata: udata["banned"] = False
            return data
        except:
            return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user):
    return user.username and user.username.lower() == ADMIN_USERNAME.lower()

async def is_subscribed(client, user_id):
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.RESTRICTED]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Subscription check error: {e}")
        return True

# --- القوائم الرئيسية ---
def main_menu(is_admin_user=False):
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"), InlineKeyboardButton("👤 حساباتي", callback_data="show_accounts")],
        [InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group"), InlineKeyboardButton("👥 السوبرات", callback_data="show_groups")],
        [InlineKeyboardButton("✉️ رسائل النشر", callback_data="show_texts"), InlineKeyboardButton("⏱️ ضبط الوقت", callback_data="set_time")],
        [InlineKeyboardButton("🟢 بدء النشر", callback_data="start_pub"), InlineKeyboardButton("🔴 إيقاف النشر", callback_data="stop_pub")],
        [InlineKeyboardButton("👑 المطور", url="https://t.me/scofr")]
    ]
    if is_admin_user:
        keyboard.insert(0, [InlineKeyboardButton("🛠️ لوحة تحكم المطور", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])

def subscription_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url="https://t.me/m_55wa")],
        [InlineKeyboardButton("✅ لقد اشتركت، تحقق الآن", callback_data="check_subscription")]
    ])

# --- محرك النشر التلقائي في الخلفية ---
async def background_publisher():
    while True:
        await asyncio.sleep(10)
        try:
            data = load_data()
            for user_id, u_data in data.items():
                if user_id == "_settings": continue
                if u_data.get("active") and u_data.get("accounts") and u_data.get("groups") and u_data.get("texts"):
                    delay = u_data.get("delay", 120)
                    accounts = u_data.get("accounts")
                    texts = u_data.get("texts")
                    groups = u_data.get("groups")
                    
                    for acc in accounts:
                        session_str = acc.get("session_string")
                        try:
                            async with Client(f"worker_{user_id}_{acc.get('id')}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True) as user_client:
                                for group in groups:
                                    for text in texts:
                                        try:
                                            await user_client.send_message(group, text)
                                            await asyncio.sleep(3)
                                        except Exception as grp_err:
                                            print(f"فشل النشر في المجموعات: {grp_err}")
                        except Exception as client_err:
                            print(f"خطأ في جلسة الحساب: {client_err}")
                    
                    await asyncio.sleep(delay)
        except Exception as e:
            print(f"خطأ في المحرك: {e}")

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = str(message.from_user.id)
    
    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            "❌ عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!\n\nرابط القناة: https://t.me/m_55wa\n\nبعد الاشتراك، اضغط على زر التحقق بالأسفل 👇",
            reply_markup=subscription_markup()
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        await message.reply_text("❌ عذراً، لقد تم حظرك من استخدام هذا البوت.")
        return

    if user_id not in data:
        data[user_id] = {"groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "state": None, "banned": False}
    else:
        if "accounts" not in data[user_id]: data[user_id]["accounts"] = []
        if "texts" not in data[user_id]: data[user_id]["texts"] = []
        if "groups" not in data[user_id]: data[user_id]["groups"] = []
        if "banned" not in data[user_id]: data[user_id]["banned"] = False
    
    data[user_id]["state"] = None
    save_data(data)
    
    welcome_template = data.get("_settings", {}).get("welcome_message", "أهلاً بك يا {name} في بوت النشر التلقائي.\n\nاستخدم الأزرار أدناه للتحكم بحساباتك، مجموعاتك، وإدارة عمليات النشر بكل سهولة.")
    welcome_text = welcome_template.replace("{name}", message.from_user.first_name)

    await message.reply_text(welcome_text, reply_markup=main_menu(admin_status))

@app.on_callback_query()
async def callback_handler(client, call):
    user_id = str(call.from_user.id)
    admin_status = is_admin(call.from_user)

    if call.data == "check_subscription":
        if await is_subscribed(client, call.from_user.id):
            await call.answer("✅ تم التحقق من اشتراكك بنجاح! أهلاً بك.", show_alert=True)
            await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status))
        else:
            await call.answer("❌ لم تقم بالاشتراك في القناة بعد! اشترك أولاً ثم حاول مجدداً.", show_alert=True)
        return

    if not await is_subscribed(client, call.from_user.id):
        await call.answer("❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
        try:
            await call.message.edit_text(
                "❌ عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!\n\nرابط القناة: https://t.me/m_55wa",
                reply_markup=subscription_markup()
            )
        except:
            pass
        return

    data = load_data()

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        await call.answer("❌ عذراً، تم حظرك من استخدام البوت.", show_alert=True)
        return

    if user_id not in data: 
        data[user_id] = {"groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "state": None, "banned": False}

    if call.data == "back_main":
        data[user_id]["state"] = None
        save_data(data)
        await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status))
        
    elif call.data == "admin_panel":
        if not admin_status:
            await call.answer("❌ عذراً، هذه اللوحة للمطور فقط!", show_alert=True)
            return
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 إدارة المشتركين", callback_data="admin_member_count"), InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🚫 حظر/إلغاء حظر عضو", callback_data="admin_ban_user")],
            [InlineKeyboardButton("✏️ تعديل رسالة الترحيب", callback_data="admin_set_welcome")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ])
        await call.message.edit_text("👑 **مرحباً بك في لوحة تحكم الأدمن الخاصة:**", reply_markup=admin_kb)

    elif call.data == "admin_member_count":
        if not admin_status:
            await call.answer("❌ غير مسموح!", show_alert=True)
            return
        all_users = load_data()
        count = len([uid for uid in all_users if uid != "_settings"])
        await call.answer(f"📊 إجمالي الأعضاء المشتركين في البوت: {count}", show_alert=True)

    elif call.data == "admin_broadcast":
        if not admin_status:
            await call.answer("❌ غير مسموح!", show_alert=True)
            return
        data[user_id]["state"] = "waiting_for_admin_broadcast"
        save_data(data)
        await call.message.edit_text("📢 أرسل الآن الرسالة (نص، صورة، فيديو...) التي تريد إذاعتها لجميع الأعضاء:", reply_markup=back_menu())

    elif call.data == "admin_ban_user":
        if not admin_status:
            await call.answer("❌ غير مسموح!", show_alert=True)
            return
        data[user_id]["state"] = "waiting_for_ban_user_id"
        save_data(data)
        await call.message.edit_text("🚫 أرسل الآن آيدي المستخدم (ID) المراد حظره أو إلغاء حظره:", reply_markup=back_menu())

    elif call.data == "admin_set_welcome":
        if not admin_status:
            await call.answer("❌ غير مسموح!", show_alert=True)
            return
        await call.answer()
        settings = data.setdefault("_settings", {})
        current_welcome = settings.get("welcome_message", "أهلاً بك يا {name} في بوت النشر التلقائي.")
        data[user_id]["state"] = "waiting_for_new_welcome"
        save_data(data)
        try:
            await call.message.edit_text(
                f"✏️ رسالة الترحيب الحالية:\n{current_welcome}\n\nأرسل رسالة الترحيب الجديدة الآن (يمكنك استخدام {{name}} لاسم المستخدم):",
                reply_markup=back_menu()
            )
        except Exception as e:
            print(f"Error: {e}")

    elif call.data == "show_accounts":
        accs = data[user_id].get("accounts", [])
        if accs:
            text = f"👤 الحسابات المضافة: (`{len(accs)}`)\n\n"
            for i, acc in enumerate(accs, 1):
                text += f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"
            keyboard = [
                [InlineKeyboardButton("➕ إضافة حساب آخر", callback_data="add_account")],
                [InlineKeyboardButton("🗑️ حذف جميع الحسابات", callback_data="clear_accounts")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ]
            await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await call.message.edit_text("❌ ليس لديك أي حسابات مضافة.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")], [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))
            
    elif call.data == "add_account":
        data[user_id]["state"] = "waiting_for_phone"
        save_data(data)
        await call.message.edit_text("📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +9665xxxxxxxx):", reply_markup=back_menu())
        
    elif call.data == "clear_accounts":
        data[user_id]["accounts"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu())

    elif call.data == "show_groups":
        groups = data[user_id].get("groups", [])
        text = f"👥 السوبرات والمجموعات المضافة: (`{len(groups)}`)\n\n"
        for i, g in enumerate(groups, 1):
            text += f"{i}. `{g}`\n"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group")],
            [InlineKeyboardButton("🗑️ تفريغ السوبرات", callback_data="clear_groups")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif call.data == "add_group":
        data[user_id]["state"] = "waiting_for_group"
        save_data(data)
        await call.message.edit_text("📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):", reply_markup=back_menu())
        
    elif call.data == "clear_groups":
        data[user_id]["groups"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم تفريغ قائمة السوبرات.", reply_markup=back_menu())

    elif call.data == "show_texts":
        texts = data[user_id].get("texts", [])
        text = f"✉️ رسائل النشر المحفوظة: (`{len(texts)}`)\n\n"
        for i, t in enumerate(texts, 1):
            preview = t[:40] + "..." if len(t) > 40 else t
            text += f"{i}. {preview}\n"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة رسالة جديدة", callback_data="add_text")],
            [InlineKeyboardButton("🗑️ حذف جميع الرسائل", callback_data="clear_texts")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif call.data == "add_text":
        data[user_id]["state"] = "waiting_for_text"
        save_data(data)
        await call.message.edit_text("✍️ أرسل نص رسالة النشر الجديدة:", reply_markup=back_menu())
        
    elif call.data == "clear_texts":
        data[user_id]["texts"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم حذف جميع الرسائل.", reply_markup=back_menu())

    elif call.data == "set_time":
        data[user_id]["state"] = "waiting_for_time"
        save_data(data)
        await call.message.edit_text("⏱️ أرسل مدة النشر بالثواني (مثلاً 120):", reply_markup=back_menu())
        
    elif call.data == "start_pub":
        if not data[user_id].get("accounts") or not data[user_id].get("texts") or not data[user_id].get("groups"):
            await call.answer("❌ يجب إضافة حساب، ورسالة، ومجموعة واحدة على الأقل أولاً!", show_alert=True)
        else:
            data[user_id]["active"] = True
            save_data(data)
            await call.answer("🟢 تم تفعيل النشر التلقائي بنجاح!", show_alert=True)
            
    elif call.data == "stop_pub":
        data[user_id]["active"] = False
        save_data(data)
        await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)
        
    try:
        await call.answer()
    except:
        pass

@app.on_message(~filters.command("start"))
async def message_handler(client, message):
    user_id = str(message.from_user.id)
    
    if not await is_subscribed(client, message.from_user.id):
        await message.reply_text(
            "❌ عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!\n\nرابط القناة: https://t.me/m_55wa",
            reply_markup=subscription_markup()
        )
        return

    data = load_data()
    admin_status = is_admin(message.from_user)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        return

    if user_id not in data or not data[user_id].get("state"): return
    state = data[user_id]["state"]

    if not message.text:
        return

    if state == "waiting_for_admin_broadcast":
        if not admin_status: return
        data[user_id]["state"] = None
        save_data(data)
        success, failed = 0, 0
        status_msg = await message.reply_text("⏳ جاري بدء الإذاعة لجميع المشتركين...")
        all_users = load_data()
        for target_id in all_users:
            if target_id == "_settings": continue
            try:
                await message.copy(chat_id=int(target_id))
                success += 1
                await asyncio.sleep(0.1)
            except Exception:
                failed += 1
        await status_msg.edit_text(f"✅ تمت الإذاعة بنجاح!\n- تم الإرسال إلى: {success}\n- فشل: {failed}", reply_markup=main_menu(admin_status))
        return

    elif state == "waiting_for_ban_user_id":
        if not admin_status: return
        target_id = message.text.strip()
        data[user_id]["state"] = None
        if target_id not in data:
            data[target_id] = {"groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "state": None, "banned": False}
        current_status = data[target_id].get("banned", False)
        new_status = not current_status
        data[target_id]["banned"] = new_status
        save_data(data)
        msg_result = f"🚫 تم حظر المستخدم (`{target_id}`)." if new_status else f"🟢 تم إلغاء حظر المستخدم (`{target_id}`)."
        await message.reply_text(msg_result, reply_markup=main_menu(admin_status))
        return

    elif state == "waiting_for_new_welcome":
        if not admin_status: return
        if "_settings" not in data: data["_settings"] = {}
        data["_settings"]["welcome_message"] = message.text
        data[user_id]["state"] = None
        save_data(data)
        await message.reply_text("✅ تم تحديث رسالة الترحيب بنجاح!", reply_markup=main_menu(admin_status))
        return

    elif state == "waiting_for_phone":
        try:
            temp_client = Client(f"session_{user_id}_{message.text}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await temp_client.connect()
            code_info = await temp_client.send_code(message.text)
            login_attempts[user_id] = {"client": temp_client, "phone": message.text, "hash": code_info.phone_code_hash}
            data[user_id]["state"] = "waiting_for_otp"
            save_data(data)
            await message.reply_text("📥 تم إرسال كود التحقق من تيليجرام. أرسل الكود هنا الآن:")
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ في رقم الهاتف: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_otp":
        attempt = login_attempts.get(user_id)
        if not attempt:
            await message.reply_text("❌ انتهت الجلسة، أعد إرسال رقم الهاتف.")
            data[user_id]["state"] = None
            save_data(data)
            return
        try:
            await attempt["client"].sign_in(attempt["phone"], attempt["hash"], message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username if me.username else "لا يوجد", "first_name": me.first_name}
            if "accounts" not in data[user_id]: data[user_id]["accounts"] = []
            data[user_id]["accounts"].append(account_info)
            await attempt["client"].disconnect()
            del login_attempts[user_id]
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status))
        except SessionPasswordNeeded:
            data[user_id]["state"] = "waiting_for_password"
            save_data(data)
            await message.reply_text("🔐 الحساب محمي بكلمة مرور. أرسلها الآن:")
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ في الكود: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_password":
        attempt = login_attempts.get(user_id)
        if not attempt:
            await message.reply_text("❌ انتهت الجلسة.")
            data[user_id]["state"] = None
            save_data(data)
            return
        try:
            await attempt["client"].check_password(message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username if me.username else "لا يوجد", "first_name": me.first_name}
            if "accounts" not in data[user_id]: data[user_id]["accounts"] = []
            data[user_id]["accounts"].append(account_info)
            await attempt["client"].disconnect()
            del login_attempts[user_id]
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status))
        except Exception as e:
            await message.reply_text(f"❌ كلمة المرور غير صحيحة: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_group":
        try:
            group_input = message.text.strip()
            if "t.me/" in group_input:
                group_input = "@" + group_input.split("t.me/")[-1].strip("/")
            elif not group_input.startswith("@"):
                group_input = "@" + group_input
            if "groups" not in data[user_id]: data[user_id]["groups"] = []
            data[user_id]["groups"].append(group_input)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text(f"✅ تم إضافة السوبر بنجاح: {group_input}", reply_markup=main_menu(admin_status))
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_text":
        try:
            if "texts" not in data[user_id]: data[user_id]["texts"] = []
            data[user_id]["texts"].append(message.text)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم حفظ الرسالة بنجاح.", reply_markup=main_menu(admin_status))
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_time":
        try:
            data[user_id]["delay"] = int(message.text)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ضبط الوقت بنجاح.", reply_markup=main_menu(admin_status))
        except Exception as e:
            await message.reply_text(f"❌ أخلِق رقماً صحيحاً بالثواني: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

# --- سيرفر الويب المدمج (تنبيه Render / UptimeRobot) ---
async def handle_ping(reader, writer):
    try:
        await reader.read(100)
        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 15\r\n\r\nBot is running!"
        writer.write(response.encode())
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
    print(f"Web server started on port {port}")

    asyncio.create_task(background_publisher())

    await app.start()
    print("البوت يعمل الآن بنجاح...")

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
