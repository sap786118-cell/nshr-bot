import os
import json
import asyncio
import random
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, UserNotParticipant
from pyrogram.enums import ChatMemberStatus

# --- الإعدادات ---
BOT_TOKEN = "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A"
API_ID = 33057479
API_HASH = "0adc25ac386d50e8ee9f3b987863c4c0"
MAIN_ADMIN_USERNAME = "scofr"  # المطور الأساسي
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
                    if "paused_groups" not in udata: udata["paused_groups"] = []
                    if "stats" not in udata: udata["stats"] = {"success": 0, "failed": 0}
                    if "banned" not in udata: udata["banned"] = False
                    if "is_pro" not in udata: udata["is_pro"] = False
            return data
        except:
            return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)

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
        [InlineKeyboardButton("👥 السوبرات", callback_data="show_groups"), InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group")],
        [InlineKeyboardButton("⏸️ المجموعات المؤقتة", callback_data="show_paused_groups"), InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
        [InlineKeyboardButton("⏱️ ضبط الوقت", callback_data="set_time"), InlineKeyboardButton("✉️ رسائل النشر", callback_data="show_texts")],
        [InlineKeyboardButton("📖 شرح البوت", callback_data="bot_guide")],
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

# --- محرك النشر الذكي في الخلفية ---
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
                    paused_groups = u_data.get("paused_groups", [])
                    
                    # إذا كان مجاني، نكتفي بالحساب الأول فقط كحماية وإجبار للترقية
                    active_accounts = accounts if u_data.get("is_pro") else accounts[:1]
                    
                    for acc in active_accounts:
                        session_str = acc.get("session_string")
                        try:
                            async with Client(f"worker_{user_id}_{acc.get('id')}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True) as user_client:
                                for group in groups:
                                    if group in paused_groups:
                                        continue
                                    for t_item in texts:
                                        try:
                                            if isinstance(t_item, str):
                                                await user_client.send_message(group, t_item)
                                            else:
                                                m_type = t_item.get("type")
                                                if m_type == "text":
                                                    await user_client.send_message(group, t_item.get("content"))
                                                elif m_type == "photo":
                                                    await user_client.send_photo(group, t_item.get("file_id"), caption=t_item.get("caption"))
                                                elif m_type == "video":
                                                    await user_client.send_video(group, t_item.get("file_id"), caption=t_item.get("caption"))
                                            
                                            fresh_data = load_data()
                                            if user_id in fresh_data:
                                                fresh_data[user_id]["stats"]["success"] = fresh_data[user_id]["stats"].get("success", 0) + 1
                                                save_data(fresh_data)
                                                
                                            await asyncio.sleep(3)
                                        except Exception as grp_err:
                                            fresh_data = load_data()
                                            if user_id in fresh_data:
                                                fresh_data[user_id]["stats"]["failed"] = fresh_data[user_id]["stats"].get("failed", 0) + 1
                                                save_data(fresh_data)
                        except Exception as client_err:
                            print(f"خطأ في جلسة الحساب: {client_err}")
                    
                    actual_delay = random.randint(int(delay), int(delay) + 30)
                    await asyncio.sleep(actual_delay)
        except Exception as e:
            print(f"خطأ في المحرك: {e}")

@app.on_message(filters.command("start"))
async def start_command(client, message):
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
        data[user_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False}
    else:
        if "accounts" not in data[user_id]: data[user_id]["accounts"] = []
        if "texts" not in data[user_id]: data[user_id]["texts"] = []
        if "groups" not in data[user_id]: data[user_id]["groups"] = []
        if "paused_groups" not in data[user_id]: data[user_id]["paused_groups"] = []
        if "stats" not in data[user_id]: data[user_id]["stats"] = {"success": 0, "failed": 0}
        if "banned" not in data[user_id]: data[user_id]["banned"] = False
        if "is_pro" not in data[user_id]: data[user_id]["is_pro"] = False
    
    data[user_id]["state"] = None
    save_data(data)
    
    is_pro = data[user_id].get("is_pro", False)
    welcome_template = data.get("_settings", {}).get("welcome_message", "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي.")
    welcome_text = welcome_template.replace("{name}", message.from_user.first_name)
    
    if is_pro:
        welcome_text += "\n\n⭐ حسابك مفعل على **باقة Pro المدفوعة** (مميزات غير محدودة)."
    else:
        welcome_text += "\n\n👤 حسابك على **الباقة المجانية** (محدد بحساب واحد و 5 مجموعات كحد أقصى). للتفاصيل والترقية تواصل مع المطور."

    if admin_status:
        welcome_text += "\n\n👑 أهلاً بك يا أدمن/مطور، تم التعرف على صلاحياتك الكاملة."

    await message.reply_text(welcome_text, reply_markup=main_menu(admin_status, is_pro))

@app.on_callback_query()
async def callback_handler(client, call):
    user_id = str(call.from_user.id)
    admin_status = is_admin(call.from_user)

    if call.data == "check_subscription":
        if await is_subscribed(client, call.from_user.id):
            data = load_data()
            is_pro = data.get(user_id, {}).get("is_pro", False)
            await call.answer("✅ تم التحقق من اشتراكك بنجاح! أهلاً بك.", show_alert=True)
            await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status, is_pro))
        else:
            await call.answer("❌ لم تقم بالاشتراك في القناة بعد! اشترك أولاً ثم حاول مجدداً.", show_alert=True)
        return

    if not await is_subscribed(client, call.from_user.id):
        await call.answer("❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
        return

    data = load_data()
    if user_id not in data: 
        data[user_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False}

    is_pro = data[user_id].get("is_pro", False)

    if data.get(user_id, {}).get("banned", False) and not admin_status:
        await call.answer("❌ عذراً، تم حظرك من استخدام البوت.", show_alert=True)
        return

    if call.data == "back_main":
        data[user_id]["state"] = None
        save_data(data)
        await call.message.edit_text("إليك لوحة التحكم:", reply_markup=main_menu(admin_status, is_pro))
        
    elif call.data == "bot_guide":
        guide_text = (
            "📖 **دليل استخدام بوت النشر التلقائي الذكي:**\n\n"
            "👤 **الباقة المجانية:**\n"
            "- ربط حساب واحد.\n"
            "- إضافة حتى 5 مجموعات/سوبرات.\n\n"
            "⭐ **باقة Pro المدفوعة:**\n"
            "- ربط حسابات متعددة غير محدودة والنشر بالتناوب.\n"
            "- إضافة مجموعات وسوبرات بلا حدود.\n"
            "- أولوية قصوى ودعم فني خاص.\n\n"
            "💳 لترقية حسابك لـ Pro، تواصل مع المطور مباشرة."
        )
        await call.message.edit_text(guide_text, reply_markup=back_menu())

    elif call.data == "admin_panel":
        if not admin_status:
            await call.answer("❌ عذراً، هذه اللوحة للمطورين فقط!", show_alert=True)
            return
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 عدد الأعضاء", callback_data="admin_member_count"), InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⭐ إدارة اشتراكات Pro", callback_data="admin_pro_management")],
            [InlineKeyboardButton("👥 إدارة المطورين", callback_data="admin_developers"), InlineKeyboardButton("🚫 حظر/إلغاء حظر", callback_data="admin_ban_user")],
            [InlineKeyboardButton("✏️ تعديل الترحيب", callback_data="admin_set_welcome"), InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ])
        await call.message.edit_text("👑 **لوحة تحكم الأدمن والمطورين:**", reply_markup=admin_kb)

    elif call.data == "admin_pro_management":
        if not admin_status: return
        pro_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ تفعيل Pro لمستخدم", callback_data="add_pro_user"), InlineKeyboardButton("❌ إزالة Pro عن مستخدم", callback_data="remove_pro_user")],
            [InlineKeyboardButton("📋 قائمة مشتركي Pro", callback_data="list_pro_users")],
            [InlineKeyboardButton("🔙 رجوع لوحة الأدمن", callback_data="admin_panel")]
        ])
        await call.message.edit_text("⭐ **إدارة اشتراكات Pro المدفوعة:**", reply_markup=pro_kb)

    elif call.data == "add_pro_user":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_pro_add_id"
        save_data(data)
        await call.message.edit_text("➕ أرسل الآن **آيدي المستخدم (ID)** لمنحه باقة Pro المدفوعة:", reply_markup=back_menu())

    elif call.data == "remove_pro_user":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_pro_remove_id"
        save_data(data)
        await call.message.edit_text("❌ أرسل الآن **آيدي المستخدم (ID)** لإرجاعه للباقة المجانية:", reply_markup=back_menu())

    elif call.data == "list_pro_users":
        if not admin_status: return
        all_u = load_data()
        pro_list = [uid for uid, uval in all_u.items() if uid != "_settings" and isinstance(uval, dict) and uval.get("is_pro")]
        text = f"⭐ **قائمة المشتركين بنظام Pro:** (`{len(pro_list)}`)\n\n"
        for i, pid in enumerate(pro_list, 1):
            text += f"{i}. آيدي: `{pid}`\n"
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_pro_management")]]))

    elif call.data == "admin_developers":
        if not admin_status: return
        devs = data.setdefault("_settings", {}).get("developers", [])
        dev_text = f"👥 **قائمة المطورين الإضافيين:** (`{len(devs)}`)\n\n"
        for i, d in enumerate(devs, 1):
            dev_text += f"{i}. آيدي: `{d}`\n"
        dev_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة مطور", callback_data="add_developer"), InlineKeyboardButton("🗑️ حذف مطور", callback_data="remove_developer")],
            [InlineKeyboardButton("🔙 رجوع لوحة الأدمن", callback_data="admin_panel")]
        ])
        await call.message.edit_text(dev_text, reply_markup=dev_kb)

    elif call.data == "add_developer":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_new_dev_id"
        save_data(data)
        await call.message.edit_text("➕ أرسل آيدي المطور الجديد:", reply_markup=back_menu())

    elif call.data == "remove_developer":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_remove_dev_id"
        save_data(data)
        await call.message.edit_text("🗑️ أرسل آيدي المطور المراد إزالته:", reply_markup=back_menu())

    elif call.data == "admin_member_count":
        if not admin_status: return
        count = len([uid for uid in load_data() if uid != "_settings"])
        await call.answer(f"📊 إجمالي الأعضاء: {count}", show_alert=True)

    elif call.data == "admin_broadcast":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_admin_broadcast"
        save_data(data)
        await call.message.edit_text("📢 أرسل رسالة الإذاعة الآن:", reply_markup=back_menu())

    elif call.data == "admin_ban_user":
        if not admin_status: return
        data[user_id]["state"] = "waiting_for_ban_user_id"
        save_data(data)
        await call.message.edit_text("🚫 أرسل آيدي المستخدم للحظر/إلغاء الحظر:", reply_markup=back_menu())

    elif call.data == "admin_set_welcome":
        if not admin_status: return
        settings = data.setdefault("_settings", {})
        data[user_id]["state"] = "waiting_for_new_welcome"
        save_data(data)
        await call.message.edit_text(f"✏️ أرسل رسالة الترحيب الجديدة (استخدم {{name}} للاسم):", reply_markup=back_menu())

    elif call.data == "show_accounts":
        accs = data[user_id].get("accounts", [])
        pro_status_text = "⭐ مفعل (Pro)" if is_pro else "👤 مجاني (محدد بحساب واحد)"
        text = f"👤 **الحسابات المضافة:** (`{len(accs)}`) | الباقة: {pro_status_text}\n\n"
        for i, acc in enumerate(accs, 1):
            text += f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
            [InlineKeyboardButton("🗑️ حذف جميع الحسابات", callback_data="clear_accounts")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif call.data == "add_account":
        # قيد الباقة المجانية: حساب واحد فقط
        if not is_pro and len(data[user_id].get("accounts", [])) >= 1:
            await call.answer("❌ عذراً، الباقة المجانية تسمح بحساب واحد فقط! قم بالترقية إلى Pro لإضافة حسابات غير محدودة.", show_alert=True)
            return
        data[user_id]["state"] = "waiting_for_phone"
        save_data(data)
        await call.message.edit_text("📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +9665xxxxxxxx):", reply_markup=back_menu())
        
    elif call.data == "clear_accounts":
        data[user_id]["accounts"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu())

    elif call.data == "show_groups":
        groups = data[user_id].get("groups", [])
        paused = data[user_id].get("paused_groups", [])
        pro_status_text = "⭐ Pro (غير محدود)" if is_pro else f"👤 مجاني ({len(groups)}/5 مجموعات)"
        text = f"👥 **السوبرات والمجموعات المضافة:** | {pro_status_text}\n\n"
        for i, g in enumerate(groups, 1):
            status = "⏸️ (موقوفة)" if g in paused else "🟢 (نشطة)"
            text += f"{i}. `{g}` - {status}\n"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group")],
            [InlineKeyboardButton("🔄 تبديل حالة مجموعة", callback_data="toggle_group_pause")],
            [InlineKeyboardButton("🗑️ تفريغ السوبرات", callback_data="clear_groups")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif call.data == "add_group":
        # قيد الباقة المجانية: 5 مجموعات كحد أقصى
        if not is_pro and len(data[user_id].get("groups", [])) >= 5:
            await call.answer("❌ لقد وصلت للحد الأقصى في الباقة المجانية (5 مجموعات). اشترك في Pro لإضافة مجموعات غير محدودة!", show_alert=True)
            return
        data[user_id]["state"] = "waiting_for_group"
        save_data(data)
        await call.message.edit_text("📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):", reply_markup=back_menu())
        
    elif call.data == "toggle_group_pause":
        data[user_id]["state"] = "waiting_for_toggle_group"
        save_data(data)
        await call.message.edit_text("🔄 أرسل معرف السوبر لإيقافه مؤقتاً أو تفعيله:", reply_markup=back_menu())

    elif call.data == "show_paused_groups":
        paused = data[user_id].get("paused_groups", [])
        text = f"⏸️ **المجموعات الموقوفة مؤقتاً:** (`{len(paused)}`)\n\n"
        for i, g in enumerate(paused, 1):
            text += f"{i}. `{g}`\n"
        await call.message.edit_text(text, reply_markup=back_menu())

    elif call.data == "show_stats":
        stats = data[user_id].get("stats", {"success": 0, "failed": 0})
        text = f"📊 **إحصائيات النشر:**\n\n✅ ناجحة: `{stats.get('success', 0)}`\n❌ فاشلة: `{stats.get('failed', 0)}`"
        await call.message.edit_text(text, reply_markup=back_menu())

    elif call.data == "clear_groups":
        data[user_id]["groups"] = []
        data[user_id]["paused_groups"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم تفريغ قائمة السوبرات.", reply_markup=back_menu())

    elif call.data == "show_texts":
        texts = data[user_id].get("texts", [])
        text = f"✉️ **رسائل والوسائط المحفوظة:** (`{len(texts)}`)\n\n"
        for i, t in enumerate(texts, 1):
            preview = t[:40] if isinstance(t, str) else f"[{t.get('type')}]"
            text += f"{i}. {preview}\n"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة رسالة/وسائط جديدة", callback_data="add_text")],
            [InlineKeyboardButton("🗑️ حذف جميع الرسائل", callback_data="clear_texts")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif call.data == "add_text":
        data[user_id]["state"] = "waiting_for_text"
        save_data(data)
        await call.message.edit_text("✍️ أرسل نص رسالة النشر أو الوسائط الآن:", reply_markup=back_menu())
        
    elif call.data == "clear_texts":
        data[user_id]["texts"] = []
        save_data(data)
        await call.message.edit_text("🗑️ تم حذف جميع الرسائل.", reply_markup=back_menu())

    elif call.data == "set_time":
        data[user_id]["state"] = "waiting_for_time"
        save_data(data)
        await call.message.edit_text("⏱️ أرسل مدة النشر الأساسية بالثواني (مثلاً 120):", reply_markup=back_menu())
        
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
            f"❌ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!**\n\nرابط القناة: https://t.me/{REQUIRED_CHANNEL.replace('@', '')}",
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

    if state == "waiting_for_pro_add_id":
        if not admin_status: return
        try:
            target_id = message.text.strip()
            if target_id not in data:
                data[target_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": True}
            else:
                data[target_id]["is_pro"] = True
            save_data(data)
            await message.reply_text(f"⭐ تم ترقية المستخدم (`{target_id}`) إلى باقة **Pro المدفوعة** بنجاح!", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {e}")
        data[user_id]["state"] = None
        save_data(data)
        return

    elif state == "waiting_for_pro_remove_id":
        if not admin_status: return
        try:
            target_id = message.text.strip()
            if target_id in data:
                data[target_id]["is_pro"] = False
                save_data(data)
                await message.reply_text(f"👤 تم إرجاع المستخدم (`{target_id}`) إلى **الباقة المجانية**.", reply_markup=main_menu(admin_status, is_pro))
            else:
                await message.reply_text("❌ هذا المستخدم غير مسجل في قاعدة البيانات.")
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {e}")
        data[user_id]["state"] = None
        save_data(data)
        return

    elif state == "waiting_for_new_dev_id":
        if not admin_status: return
        try:
            new_dev = int(message.text.strip())
            settings = data.setdefault("_settings", {})
            devs = settings.setdefault("developers", [])
            if new_dev not in devs:
                devs.append(new_dev)
                save_data(data)
                await message.reply_text(f"✅ تم إضافة الآيدي `{new_dev}` للمطورين.", reply_markup=main_menu(admin_status, is_pro))
            else:
                await message.reply_text("⚠️ موجود مسبقاً.")
        except ValueError:
            await message.reply_text("❌ آيدي غير صحيح!")
        data[user_id]["state"] = None
        save_data(data)
        return

    elif state == "waiting_for_remove_dev_id":
        if not admin_status: return
        try:
            rem_dev = int(message.text.strip())
            devs = data.setdefault("_settings", {}).setdefault("developers", [])
            if rem_dev in devs:
                devs.remove(rem_dev)
                save_data(data)
                await message.reply_text(f"🗑️ تمت إزالة الآيدي `{rem_dev}` من المطورين.", reply_markup=main_menu(admin_status, is_pro))
            else:
                await message.reply_text("❌ غير موجود.")
        except ValueError:
            await message.reply_text("❌ آيدي غير صحيح!")
        data[user_id]["state"] = None
        save_data(data)
        return

    elif state == "waiting_for_admin_broadcast":
        if not admin_status: return
        data[user_id]["state"] = None
        save_data(data)
        success, failed = 0, 0
        status_msg = await message.reply_text("⏳ جاري الإذاعة...")
        all_users = load_data()
        for target_id in all_users:
            if target_id == "_settings": continue
            try:
                await message.copy(chat_id=int(target_id))
                success += 1
                await asyncio.sleep(0.1)
            except:
                failed += 1
        await status_msg.edit_text(f"✅ تمت الإذاعة بنجاح!\n- نجح: {success}\n- فشل: {failed}", reply_markup=main_menu(admin_status, is_pro))
        return

    elif state == "waiting_for_ban_user_id":
        if not admin_status: return
        target_id = message.text.strip()
        data[user_id]["state"] = None
        if target_id not in data:
            data[target_id] = {"groups": [], "paused_groups": [], "delay": 120, "active": False, "accounts": [], "texts": [], "stats": {"success": 0, "failed": 0}, "state": None, "banned": False, "is_pro": False}
        new_status = not data[target_id].get("banned", False)
        data[target_id]["banned"] = new_status
        save_data(data)
        msg_res = f"🚫 تم حظر المستخدم (`{target_id}`)." if new_status else f"🟢 تم إلغاء حظر المستخدم (`{target_id}`)."
        await message.reply_text(msg_res, reply_markup=main_menu(admin_status, is_pro))
        return

    elif state == "waiting_for_new_welcome":
        if not admin_status: return
        data.setdefault("_settings", {})["welcome_message"] = message.text
        data[user_id]["state"] = None
        save_data(data)
        await message.reply_text("✅ تم تحديث الترحيب.", reply_markup=main_menu(admin_status, is_pro))
        return

    elif state == "waiting_for_phone":
        try:
            temp_client = Client(f"session_{user_id}_{message.text}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await temp_client.connect()
            code_info = await temp_client.send_code(message.text)
            login_attempts[user_id] = {"client": temp_client, "phone": message.text, "hash": code_info.phone_code_hash}
            data[user_id]["state"] = "waiting_for_otp"
            save_data(data)
            await message.reply_text("📥 أرسل كود التحقق من تيليجرام الآن:")
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_otp":
        attempt = login_attempts.get(user_id)
        if not attempt:
            data[user_id]["state"] = None
            save_data(data)
            return
        try:
            await attempt["client"].sign_in(attempt["phone"], attempt["hash"], message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username or "لا يوجد", "first_name": me.first_name}
            data[user_id]["accounts"].append(account_info)
            await attempt["client"].disconnect()
            del login_attempts[user_id]
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status, is_pro))
        except SessionPasswordNeeded:
            data[user_id]["state"] = "waiting_for_password"
            save_data(data)
            await message.reply_text("🔐 أرسل كلمة مرور التحقق بخطوتين:")
        except Exception as e:
            await message.reply_text(f"❌ خطأ في الكود: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_password":
        attempt = login_attempts.get(user_id)
        try:
            await attempt["client"].check_password(message.text)
            me = await attempt["client"].get_me()
            session_str = await attempt["client"].export_session_string()
            account_info = {"session_string": session_str, "id": me.id, "username": me.username or "لا يوجد", "first_name": me.first_name}
            data[user_id]["accounts"].append(account_info)
            await attempt["client"].disconnect()
            del login_attempts[user_id]
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status, is_pro))
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
            
            data[user_id]["groups"].append(group_input)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text(f"✅ تم إضافة السوبر: {group_input}", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_toggle_group":
        try:
            g_input = message.text.strip()
            if not g_input.startswith("@"): g_input = "@" + g_input
            paused = data[user_id].setdefault("paused_groups", [])
            if g_input in paused:
                paused.remove(g_input)
                msg = f"🟢 أعيد تفعيل: {g_input}"
            else:
                paused.append(g_input)
                msg = f"⏸️ تم إيقاف: {g_input}"
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text(msg, reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_text":
        try:
            if message.text:
                msg_data = {"type": "text", "content": message.text}
            elif message.photo:
                msg_data = {"type": "photo", "file_id": message.photo.file_id, "caption": message.caption or ""}
            elif message.video:
                msg_data = {"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}
            else:
                await message.reply_text("❌ أرسل نص، صورة، أو فيديو فقط!")
                return
            data[user_id]["texts"].append(msg_data)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم حفظ الرسالة/الوسائط بنجاح.", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

    elif state == "waiting_for_time":
        try:
            data[user_id]["delay"] = int(message.text)
            data[user_id]["state"] = None
            save_data(data)
            await message.reply_text("✅ تم ضبط الوقت.", reply_markup=main_menu(admin_status, is_pro))
        except Exception as e:
            await message.reply_text(f"❌ أدخل رقماً صحيحاً: {e}")
            data[user_id]["state"] = None
            save_data(data)
        return

# --- سيرفر الويب المدمج لـ Render ---
async def handle_ping(reader, writer):
    try:
        await reader.read(100)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 15\r\n\r\nBot is running!")
        await writer.drain()
    except:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def main():
    port = int(os.environ.get("PORT", 8080))
    server = await asyncio.start_server(handle_ping, '0.0.0.0', port)
    asyncio.create_task(background_publisher())
    await app.start()
    print("البوت يعمل الآن بنجاح...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
