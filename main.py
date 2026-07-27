import asyncio
import json
import os
import random
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import SessionPasswordNeeded, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- الإعدادات الأساسية للبوت ---
BOT_TOKEN = "8996776697:AAFquiMkylAqhbf_G5FbGYXSVnVa9LZ4k3A"
API_ID = 33057479
API_HASH = "0adc25ac386d50e8ee9f3b987863c4c0"
MAIN_ADMIN_USERNAME = "scofr"  # معرف المطور الأساسي
REQUIRED_CHANNEL = "@m_55wa"  # قناة الاشتراك الإجباري

DATA_FILE = "bot_data.json"


def load_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except:
      pass
  return {
      "users": {},
      "settings": {
          "welcome_message": (
              "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي."
          ),
          "developers": [],
      },
  }


def save_data(data):
  try:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=4)
  except Exception as e:
    print(f"Error saving data: {e}")


db_data = load_data()

app = Client(
    "publisher_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)
login_attempts = {}


def get_user_data(user_id):
  uid_str = str(user_id)
  if uid_str not in db_data["users"]:
    db_data["users"][uid_str] = {
        "groups": [],
        "paused_groups": [],
        "delay": 120,
        "active": False,
        "accounts": [],
        "texts": [],
        "stats": {"success": 0, "failed": 0},
        "state": None,
        "banned": False,
    }
    save_data(db_data)
  return db_data["users"][uid_str]


def is_admin(user):
  if user.username and user.username.lower() == MAIN_ADMIN_USERNAME.lower():
    return True
  if user.id in db_data["settings"].get("developers", []):
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


def main_menu(is_admin_user=False):
  keyboard = [
      [
          InlineKeyboardButton("👤 حساباتي", callback_data="show_accounts"),
          InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"),
      ],
      [
          InlineKeyboardButton("👥 السوبرات", callback_data="show_groups"),
          InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group"),
      ],
      [
          InlineKeyboardButton(
              "⏸️ المجموعات المؤقتة", callback_data="show_paused_groups"
          ),
          InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats"),
      ],
      [
          InlineKeyboardButton("⏱️ ضبط الوقت", callback_data="set_time"),
          InlineKeyboardButton("✉️ رسائل النشر", callback_data="show_texts"),
      ],
      [InlineKeyboardButton("📖 شرح البوت", callback_data="bot_guide")],
      [
          InlineKeyboardButton("🔴 إيقاف النشر", callback_data="stop_pub"),
          InlineKeyboardButton("🟢 بدء النشر", callback_data="start_pub"),
      ],
      [
          InlineKeyboardButton(
              "👑 المطور", url=f"https://t.me/{MAIN_ADMIN_USERNAME}"
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
      [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
  )


def subscription_markup():
  return InlineKeyboardMarkup([
      [InlineKeyboardButton("📢 اشترك في القناة", url="https://t.me/m_55wa")],
      [
          InlineKeyboardButton(
              "✅ لقد اشتركت، تحقق الآن", callback_data="check_subscription"
          )
      ],
  ])


# --- محرك النشر الذكي في الخلفية ---
async def background_publisher():
  while True:
    await asyncio.sleep(10)
    try:
      for user_id, u_data in list(db_data["users"].items()):
        if (
            u_data.get("active")
            and u_data.get("accounts")
            and u_data.get("groups")
            and u_data.get("texts")
        ):
          delay = u_data.get("delay", 120)
          accounts = u_data.get("accounts")
          texts = u_data.get("texts")
          groups = u_data.get("groups")
          paused_groups = u_data.get("paused_groups", [])

          for acc in accounts:
            session_str = acc.get("session_string")
            try:
              async with Client(
                  f"worker_{user_id}_{acc.get('id')}",
                  api_id=API_ID,
                  api_hash=API_HASH,
                  session_string=session_str,
                  in_memory=True,
              ) as user_client:
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
                          await user_client.send_message(
                              group, t_item.get("content")
                          )
                        elif m_type == "photo":
                          await user_client.send_photo(
                              group,
                              t_item.get("file_id"),
                              caption=t_item.get("caption"),
                          )
                        elif m_type == "video":
                          await user_client.send_video(
                              group,
                              t_item.get("file_id"),
                              caption=t_item.get("caption"),
                          )

                      u_data["stats"]["success"] = (
                          u_data["stats"].get("success", 0) + 1
                      )
                      save_data(db_data)
                      await asyncio.sleep(3)
                    except Exception as grp_err:
                      print(f"فشل النشر: {grp_err}")
                      u_data["stats"]["failed"] = (
                          u_data["stats"].get("failed", 0) + 1
                      )
                      save_data(db_data)
            except Exception as client_err:
              print(f"خطأ في جلسة الحساب: {client_err}")

          await asyncio.sleep(random.randint(int(delay), int(delay) + 30))
    except Exception as e:
      print(f"خطأ في المحرك: {e}")


@app.on_message(filters.command("start"))
async def start_command(client, message):
  user_id = message.from_user.id

  if not await is_subscribed(client, user_id):
    await message.reply_text(
        "❌ عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه.\n\nرابط"
        " القناة: https://t.me/m_55wa\n\nبعد الاشتراك، اضغط على زر التحقق بالأسفل"
        " 👇",
        reply_markup=subscription_markup(),
    )
    return

  admin_status = is_admin(message.from_user)
  u_data = get_user_data(user_id)

  if u_data.get("banned", False) and not admin_status:
    await message.reply_text("❌ عذراً، لقد تم حظرك من استخدام هذا البوت.")
    return

  u_data["state"] = None
  save_data(db_data)

  welcome_template = db_data["settings"].get(
      "welcome_message", "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي."
  )
  welcome_text = welcome_template.replace("{name}", message.from_user.first_name)

  if admin_status:
    welcome_text += "\n\n👑 أهلاً بك يا مطور، تم التعرف على صلاحياتك الكاملة."

  await message.reply_text(welcome_text, reply_markup=main_menu(admin_status))


@app.on_callback_query()
async def callback_handler(client, call):
  user_id = call.from_user.id
  admin_status = is_admin(call.from_user)

  if call.data == "check_subscription":
    if await is_subscribed(client, user_id):
      await call.answer(
          "✅ تم التحقق من اشتراكك بنجاح! أهلاً بك.", show_alert=True
      )
      await call.message.edit_text(
          "إليك لوحة التحكم:", reply_markup=main_menu(admin_status)
      )
    else:
      await call.answer(
          "❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True
      )
    return

  if not await is_subscribed(client, user_id):
    await call.answer("❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
    return

  u_data = get_user_data(user_id)
  if u_data.get("banned", False) and not admin_status:
    await call.answer("❌ تم حظرك.", show_alert=True)
    return

  if call.data == "back_main":
    u_data["state"] = None
    save_data(db_data)
    await call.message.edit_text(
        "إليك لوحة التحكم:", reply_markup=main_menu(admin_status)
    )

  elif call.data == "bot_guide":
    guide_text = (
        "📖 **دليل استخدام بوت النشر التلقائي الذكي:**\n\n1️⃣ **إضافة حساب (👤"
        " حساباتي):** اربط حسابك برقم الهاتف.\n2️⃣ **إضافة السوبرات (👥"
        " السوبرات):** أرسل معرفات المجموعات.\n3️⃣ **رسائل النشر (✉️ رسائل"
        " النشر):** أرسل النصوص أو الوسائط.\n4️⃣ **ضبط الوقت (⏱️ ضبط الوقت):**"
        " حدد الفاصل الزمني.\n5️⃣ **بدء النشر (🟢):** لتشغيل النشر التلقائي.\n"
    )
    await call.message.edit_text(guide_text, reply_markup=back_menu())

  elif call.data == "admin_panel":
    if not admin_status:
      await call.answer("❌ للمطورين فقط!", show_alert=True)
      return
    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 عدد الأعضاء", callback_data="admin_member_count"
            ),
            InlineKeyboardButton(
                "📢 إذاعة عامة", callback_data="admin_broadcast"
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 إدارة المطورين", callback_data="admin_developers"
            ),
            InlineKeyboardButton("🚫 حظر عضو", callback_data="admin_ban_user"),
        ],
        [
            InlineKeyboardButton(
                "✏️ تعديل الترحيب", callback_data="admin_set_welcome"
            ),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_main"),
        ],
    ])
    await call.message.edit_text(
        "👑 **لوحة تحكم الأدمن والمطورين:**", reply_markup=admin_kb
    )

  elif call.data == "admin_developers":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    devs = db_data["settings"].get("developers", [])
    dev_list_text = f"👥 **قائمة المطورين المضافين:** (`{len(devs)}`)\n\n"
    for i, d_id in enumerate(devs, 1):
      dev_list_text += f"{i}. آيدي: `{d_id}`\n"

    dev_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ إضافة مطور جديد", callback_data="add_developer"
            ),
            InlineKeyboardButton("🗑️ حذف مطور", callback_data="remove_developer"),
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع لوحة الأدمن", callback_data="admin_panel"
            )
        ],
    ])
    await call.message.edit_text(dev_list_text, reply_markup=dev_kb)

  elif call.data == "add_developer":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_new_dev_id"
    save_data(db_data)
    await call.message.edit_text(
        "➕ أرسل الآن **آيدي المستخدم (ID)** للمطور الجديد ليحصل على صلاحيات"
        " لوحة الأدمن:",
        reply_markup=back_menu(),
    )

  elif call.data == "remove_developer":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_remove_dev_id"
    save_data(db_data)
    await call.message.edit_text(
        "🗑️ أرسل الآن **آيدي المستخدم (ID)** للمطور المراد إزالته من الصلاحيات:",
        reply_markup=back_menu(),
    )

  elif call.data == "admin_member_count":
    if not admin_status:
      return
    count = len(db_data["users"])
    await call.answer(f"📊 إجمالي الأعضاء: {count}", show_alert=True)

  elif call.data == "admin_broadcast":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_admin_broadcast"
    save_data(db_data)
    await call.message.edit_text(
        "📢 أرسل رسالة الإذاعة الآن:", reply_markup=back_menu()
    )

  elif call.data == "admin_ban_user":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_ban_user_id"
    save_data(db_data)
    await call.message.edit_text(
        "🚫 أرسل الآن **آيدي المستخدم (ID)** المراد حظره أو إلغاء حظره:",
        reply_markup=back_menu(),
    )

  elif call.data == "admin_set_welcome":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_new_welcome"
    save_data(db_data)
    current_welcome = db_data["settings"].get(
        "welcome_message", "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي."
    )
    await call.message.edit_text(
        f"✏️ رسالة الترحيب الحالية:\n{current_welcome}\n\nأرسل رسالة الترحيب"
        " الجديدة:",
        reply_markup=back_menu(),
    )

  elif call.data == "show_accounts":
    accs = u_data.get("accounts", [])
    text = f"👤 **الحسابات المضافة:** (`{len(accs)}`)\n\n"
    for i, acc in enumerate(accs, 1):
      text += (
          f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"
      )
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
        [InlineKeyboardButton("🗑️ حذف الحسابات", callback_data="clear_accounts")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )

  elif call.data == "add_account":
    u_data["state"] = "waiting_for_phone"
    save_data(db_data)
    await call.message.edit_text(
        "📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +9665xxxxxxxx):",
        reply_markup=back_menu(),
    )

  elif call.data == "clear_accounts":
    u_data["accounts"] = []
    save_data(db_data)
    await call.message.edit_text(
        "🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu()
    )

  elif call.data == "show_groups":
    groups = u_data.get("groups", [])
    paused = u_data.get("paused_groups", [])
    text = f"👥 **السوبرات والمجموعات:** (`{len(groups)}`)\n\n"
    for i, g in enumerate(groups, 1):
      status = "⏸️ (موقوفة)" if g in paused else "🟢 (نشطة)"
      text += f"{i}. `{g}` - {status}\n"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group")],
        [InlineKeyboardButton("🗑️ تفريغ السوبرات", callback_data="clear_groups")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )

  elif call.data == "add_group":
    u_data["state"] = "waiting_for_group"
    save_data(db_data)
    await call.message.edit_text(
        "📥 أرسل معرف السوبر (مثال: `@Group`):", reply_markup=back_menu()
    )

  elif call.data == "clear_groups":
    u_data["groups"] = []
    u_data["paused_groups"] = []
    save_data(db_data)
    await call.message.edit_text(
        "🗑️ تم تفريغ قائمة السوبرات.", reply_markup=back_menu()
    )

  elif call.data == "show_stats":
    stats = u_data.get("stats", {"success": 0, "failed": 0})
    text = (
        f"📊 **إحصائياتك:**\n\n✅ ناجحة: `{stats.get('success', 0)}`\n❌ فاشلة:"
        f" `{stats.get('failed', 0)}`"
    )
    await call.message.edit_text(text, reply_markup=back_menu())

  elif call.data == "show_texts":
    texts = u_data.get("texts", [])
    text = f"✉️ **الرسائل المحفوظة:** (`{len(texts)}`)\n\n"
    for i, t in enumerate(texts, 1):
      preview = (
          t
          if isinstance(t, str)
          else f"[{t.get('type')}] {t.get('caption', '')}"
      )
      text += f"{i}. {preview[:30]}\n"
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ إضافة رسالة جديدة", callback_data="add_text"
            )
        ],
        [InlineKeyboardButton("🗑️ حذف الرسائل", callback_data="clear_texts")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )

  elif call.data == "add_text":
    u_data["state"] = "waiting_for_text"
    save_data(db_data)
    await call.message.edit_text(
        "✍️ أرسل نص النشر أو صورة/فيديو مع الكابشن:", reply_markup=back_menu()
    )

  elif call.data == "clear_texts":
    u_data["texts"] = []
    save_data(db_data)
    await call.message.edit_text("🗑️ تم حذف الرسائل.", reply_markup=back_menu())

  elif call.data == "set_time":
    u_data["state"] = "waiting_for_time"
    save_data(db_data)
    await call.message.edit_text(
        "⏱️ أرسل مدة النشر بالثواني (مثلاً 120):", reply_markup=back_menu()
    )

  elif call.data == "start_pub":
    if (
        not u_data.get("accounts")
        or not u_data.get("texts")
        or not u_data.get("groups")
    ):
      await call.answer("❌ أضف حساباً ورسالة ومجموعة أولاً!", show_alert=True)
    else:
      u_data["active"] = True
      save_data(db_data)
      await call.answer("🟢 تم تفعيل النشر التلقائي!", show_alert=True)

  elif call.data == "stop_pub":
    u_data["active"] = False
    save_data(db_data)
    await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)

  try:
    await call.answer()
  except:
    pass


@app.on_message(~filters.command("start"))
async def message_handler(client, message):
  user_id = message.from_user.id
  if not await is_subscribed(client, user_id):
    return

  admin_status = is_admin(message.from_user)
  u_data = get_user_data(user_id)
  state = u_data.get("state")
  if not state:
    return

  if state == "waiting_for_new_dev_id" and admin_status:
    try:
      new_dev_id = int(message.text.strip())
      if new_dev_id not in db_data["settings"]["developers"]:
        db_data["settings"]["developers"].append(new_dev_id)
        save_data(db_data)
        await message.reply_text(
            f"✅ تم إضافة الآيدي (`{new_dev_id}`) لقائمة المطورين بنجاح!",
            reply_markup=main_menu(admin_status),
        )
      else:
        await message.reply_text(
            "⚠️ هذا المستخدم موجود بالفعل في قائمة المطورين.",
            reply_markup=main_menu(admin_status),
        )
    except ValueError:
      await message.reply_text("❌ يرجى إرسال آيدي صحيح (أرقام فقط).")
    u_data["state"] = None
    save_data(db_data)
    return

  elif state == "waiting_for_remove_dev_id" and admin_status:
    try:
      rem_dev_id = int(message.text.strip())
      if rem_dev_id in db_data["settings"]["developers"]:
        db_data["settings"]["developers"].remove(rem_dev_id)
        save_data(db_data)
        await message.reply_text(
            f"🗑️ تمت إزالة الآيدي (`{rem_dev_id}`) من قائمة المطورين.",
            reply_markup=main_menu(admin_status),
        )
      else:
        await message.reply_text(
            "❌ هذا الآيدي غير موجود في قائمة المطورين.",
            reply_markup=main_menu(admin_status),
        )
    except ValueError:
      await message.reply_text("❌ يرجى إرسال آيدي صحيح (أرقام فقط).")
    u_data["state"] = None
    save_data(db_data)
    return

  elif state == "waiting_for_admin_broadcast" and admin_status:
    u_data["state"] = None
    save_data(db_data)
    success = 0
    for target_id in db_data["users"]:
      try:
        await message.copy(chat_id=int(target_id))
        success += 1
        await asyncio.sleep(0.1)
      except:
        pass
    await message.reply_text(
        f"✅ تمت الإذاعة إلى {success} مستخدم.",
        reply_markup=main_menu(admin_status),
    )
    return

  elif state == "waiting_for_ban_user_id" and admin_status:
    target_id = message.text.strip()
    u_data["state"] = None
    save_data(db_data)
    target_data = get_user_data(target_id)
    new_status = not target_data.get("banned", False)
    target_data["banned"] = new_status
    save_data(db_data)
    msg = (
        f"🚫 تم حظر المستخدم (`{target_id}`)."
        if new_status
        else f"🟢 تم إلغاء حظر المستخدم (`{target_id}`)."
    )
    await message.reply_text(msg, reply_markup=main_menu(admin_status))
    return

  elif state == "waiting_for_new_welcome" and admin_status:
    db_data["settings"]["welcome_message"] = message.text
    save_data(db_data)
    u_data["state"] = None
    save_data(db_data)
    await message.reply_text(
        "✅ تم تحديث رسالة الترحيب بنجاح!", reply_markup=main_menu(admin_status)
    )
    return

  elif state == "waiting_for_phone":
    try:
      temp_client = Client(
          f"session_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True
      )
      await temp_client.connect()
      code_info = await temp_client.send_code(message.text)
      login_attempts[user_id] = {
          "client": temp_client,
          "phone": message.text,
          "hash": code_info.phone_code_hash,
      }
      u_data["state"] = "waiting_for_otp"
      save_data(db_data)
      await message.reply_text("📥 أرسل كود التحقق الآن:")
    except Exception as e:
      await message.reply_text(f"❌ خطأ: {e}")
      u_data["state"] = None
      save_data(db_data)
    return

  elif state == "waiting_for_otp":
    attempt = login_attempts.get(user_id)
    if not attempt:
      u_data["state"] = None
      save_data(db_data)
      return
    try:
      await attempt["client"].sign_in(
          attempt["phone"], attempt["hash"], message.text
      )
      me = await attempt["client"].get_me()
      session_str = await attempt["client"].export_session_string()
      u_data["accounts"].append({
          "session_string": session_str,
          "id": me.id,
          "username": me.username or "لا يوجد",
          "first_name": me.first_name,
      })
      await attempt["client"].disconnect()
      del login_attempts[user_id]
      u_data["state"] = None
      save_data(db_data)
      await message.reply_text(
          "✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status)
      )
    except SessionPasswordNeeded:
      u_data["state"] = "waiting_for_password"
      save_data(db_data)
      await message.reply_text("🔐 أرسل كلمة مرور التحقق بخطوتين:")
    except Exception as e:
      await message.reply_text(f"❌ خطأ: {e}")
      u_data["state"] = None
      save_data(db_data)
    return

  elif state == "waiting_for_password":
    attempt = login_attempts.get(user_id)
    try:
      await attempt["client"].check_password(message.text)
      me = await attempt["client"].get_me()
      session_str = await attempt["client"].export_session_string()
      u_data["accounts"].append({
          "session_string": session_str,
          "id": me.id,
          "username": me.username or "لا يوجد",
          "first_name": me.first_name,
      })
      await attempt["client"].disconnect()
      del login_attempts[user_id]
      u_data["state"] = None
      save_data(db_data)
      await message.reply_text(
          "✅ تم ربط الحساب بنجاح!", reply_markup=main_menu(admin_status)
      )
    except Exception as e:
      await message.reply_text(f"❌ خطأ: {e}")
      u_data["state"] = None
      save_data(db_data)
    return

  elif state == "waiting_for_group":
    group_input = message.text.strip()
    if not group_input.startswith("@"):
      group_input = "@" + group_input
    u_data["groups"].append(group_input)
    u_data["state"] = None
    save_data(db_data)
    await message.reply_text(
        f"✅ تم إضافة السوبر: {group_input}",
        reply_markup=main_menu(admin_status),
    )
    return

  elif state == "waiting_for_text":
    if message.text:
      msg_data = {"type": "text", "content": message.text}
    elif message.photo:
      msg_data = {
          "type": "photo",
          "file_id": message.photo.file_id,
          "caption": message.caption or "",
      }
    elif message.video:
      msg_data = {
          "type": "video",
          "file_id": message.video.file_id,
          "caption": message.caption or "",
      }
    else:
      await message.reply_text("❌ أرسل نصاً أو صورة أو فيديو فقط!")
      return
    u_data["texts"].append(msg_data)
    u_data["state"] = None
    save_data(db_data)
    await message.reply_text(
        "✅ تم حفظ الرسالة بنجاح.", reply_markup=main_menu(admin_status)
    )
    return

  elif state == "waiting_for_time":
    try:
      u_data["delay"] = int(message.text)
      u_data["state"] = None
      save_data(db_data)
      await message.reply_text(
          "✅ تم ضبط الوقت.", reply_markup=main_menu(admin_status)
      )
    except:
      await message.reply_text("❌ أدخل رقماً صحيحاً بالثواني.")
      u_data["state"] = None
      save_data(db_data)
    return


# --- سيرفر الويب لمنع النوم على Render ---
async def handle_ping(reader, writer):
  try:
    await reader.read(100)
    response = (
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length:"
        " 15\r\n\r\nBot is running!"
    )
    writer.write(response.encode())
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
  server = await asyncio.start_server(handle_ping, "0.0.0.0", port)
  print(f"Web server started on port {port}")

  asyncio.create_task(background_publisher())
  await app.start()
  print("البوت يعمل الآن مع لوحة المطورين وسيرفر الويب وبدون قواعد خارجية...")
  await idle()
  await app.stop()


if __name__ == "__main__":
  asyncio.run(main())
