import asyncio
import os
import random
from pymongo import MongoClient
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

# رابط قاعدة البيانات السحابية MongoDB (مع كلمة المرور الخاصة بك)
MONGO_URI = (
    "mongodb+srv://sap786118_db_user:77880zzpo@cluster0.extvh0l.mongodb.net"
    "/?appName=Cluster0"
)

# اتصال قاعدة البيانات
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["telegram_publisher_bot"]
users_col = db["users"]
settings_col = db["settings"]

app = Client(
    "publisher_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)
login_attempts = {}


def load_settings():
  settings = settings_col.find_one({"_id": "global_settings"})
  if not settings:
    settings = {
        "_id": "global_settings",
        "welcome_message": (
            "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي."
        ),
        "developers": [],
    }
    settings_col.insert_one(settings)
  return settings


def save_settings(settings):
  settings_col.replace_one({"_id": "global_settings"}, settings, upsert=True)


def load_user_data(user_id):
  uid_str = str(user_id)
  user_data = users_col.find_one({"_id": uid_str})
  if not user_data:
    user_data = {
        "_id": uid_str,
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
    users_col.insert_one(user_data)
  return user_data


def save_user_data(user_id, data):
  uid_str = str(user_id)
  data["_id"] = uid_str
  users_col.replace_one({"_id": uid_str}, data, upsert=True)


def is_admin(user):
  if user.username and user.username.lower() == MAIN_ADMIN_USERNAME.lower():
    return True
  settings = load_settings()
  devs = settings.get("developers", [])
  if user.id in devs:
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
  except Exception as e:
    print(f"Subscription check error: {e}")
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
      all_users = list(users_col.find())
      for u_data in all_users:
        user_id = u_data["_id"]
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

                      current_u = load_user_data(user_id)
                      current_u["stats"]["success"] = (
                          current_u["stats"].get("success", 0) + 1
                      )
                      save_user_data(user_id, current_u)

                      await asyncio.sleep(3)
                    except Exception as grp_err:
                      print(f"فشل النشر في المجموعات: {grp_err}")
                      current_u = load_user_data(user_id)
                      current_u["stats"]["failed"] = (
                          current_u["stats"].get("failed", 0) + 1
                      )
                      save_user_data(user_id, current_u)
            except Exception as client_err:
              print(f"خطأ في جلسة الحساب: {client_err}")

          actual_delay = random.randint(int(delay), int(delay) + 30)
          await asyncio.sleep(actual_delay)
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
  u_data = load_user_data(user_id)

  if u_data.get("banned", False) and not admin_status:
    await message.reply_text("❌ عذراً، لقد تم حظرك من استخدام هذا البوت.")
    return

  u_data["state"] = None
  save_user_data(user_id, u_data)

  settings = load_settings()
  welcome_template = settings.get(
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
          "❌ لم تقم بالاشتراك في القناة بعد! اشترك أولاً ثم حاول مجدداً.",
          show_alert=True,
      )
    return

  if not await is_subscribed(client, user_id):
    await call.answer("❌ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
    try:
      await call.message.edit_text(
          "❌ عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه.\n\nرابط"
          " القناة: https://t.me/m_55wa",
          reply_markup=subscription_markup(),
      )
    except:
      pass
    return

  u_data = load_user_data(user_id)
  if u_data.get("banned", False) and not admin_status:
    await call.answer("❌ عذراً، تم حظرك من استخدام البوت.", show_alert=True)
    return

  if call.data == "back_main":
    u_data["state"] = None
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "إليك لوحة التحكم:", reply_markup=main_menu(admin_status)
    )

  elif call.data == "bot_guide":
    guide_text = (
        "📖 **دليل استخدام بوت النشر التلقائي الذكي:**\n\n1️⃣ **إضافة حساب (👤"
        " حساباتي):** اربط حسابك برقم الهاتف وكود التحقق ليعمل البوت كمساعد"
        " شخصي للنشر.\n2️⃣ **إضافة السوبرات (👥 السوبرات):** أرسل معرفات المجموعات"
        " أو السوبرات التي تريد النشر فيها.\n3️⃣ **رسائل النشر (✉️ رسائل النشر):**"
        " أرسل نصوصاً، صوراً، أو فيديوهات مع الوصف (الكابشن) ليقوم البوت"
        " بنشرها.\n4️⃣ **ضبط الوقت (⏱️ ضبط الوقت):** حدد الفاصل الزمني الأساسي"
        " بالثواني.\n5️⃣ **التحكم بالنشر (🟢/🔴):** بعد استيفاء الشروط، اضغط على"
        " بدء النشر ليعمل تلقائياً.\n"
    )
    await call.message.edit_text(guide_text, reply_markup=back_menu())

  elif call.data == "admin_panel":
    if not admin_status:
      await call.answer("❌ عذراً، هذه اللوحة للمطورين فقط!", show_alert=True)
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
            InlineKeyboardButton(
                "🚫 حظر/إلغاء حظر عضو", callback_data="admin_ban_user"
            ),
        ],
        [
            InlineKeyboardButton(
                "✏️ تعديل رسالة الترحيب", callback_data="admin_set_welcome"
            ),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_main"),
        ],
    ])
    await call.message.edit_text(
        "👑 **مرحباً بك في لوحة تحكم الأدمن والمطورين:**", reply_markup=admin_kb
    )

  elif call.data == "admin_developers":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    settings = load_settings()
    devs = settings.get("developers", [])
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
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "➕ أرسل الآن **آيدي المستخدم (ID)** للمطور الجديد ليحصل على صلاحيات"
        " لوحة الأدمن:",
        reply_markup=back_menu(),
    )

  elif call.data == "remove_developer":
    if not admin_status:
      return
    u_data["state"] = "waiting_for_remove_dev_id"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🗑️ أرسل الآن **آيدي المستخدم (ID)** للمطور المراد إزالته من الصلاحيات:",
        reply_markup=back_menu(),
    )

  elif call.data == "admin_member_count":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    count = users_col.count_documents({})
    await call.answer(
        f"📊 إجمالي الأعضاء المشتركين في البوت: {count}", show_alert=True
    )

  elif call.data == "admin_broadcast":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    u_data["state"] = "waiting_for_admin_broadcast"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "📢 أرسل الآن الرسالة (نص، صورة، فيديو...) التي تريد إذاعتها لجميع"
        " الأعضاء:",
        reply_markup=back_menu(),
    )

  elif call.data == "admin_ban_user":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    u_data["state"] = "waiting_for_ban_user_id"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🚫 أرسل الآن **آيدي المستخدم (ID)** المراد حظره أو إلغاء حظره:",
        reply_markup=back_menu(),
    )

  elif call.data == "admin_set_welcome":
    if not admin_status:
      await call.answer("❌ غير مسموح!", show_alert=True)
      return
    await call.answer()
    settings = load_settings()
    current_welcome = settings.get(
        "welcome_message", "أهلاً بك يا {name}، هذا بوت النشر التلقائي الذكي."
    )
    u_data["state"] = "waiting_for_new_welcome"
    save_user_data(user_id, u_data)
    try:
      await call.message.edit_text(
          f"✏️ رسالة الترحيب الحالية:\n{current_welcome}\n\nأرسل رسالة الترحيب"
          " الجديدة الآن (يمكنك استخدام {{name}} لاسم المستخدم):",
          reply_markup=back_menu(),
      )
    except Exception as e:
      print(f"Error editing welcome message: {e}")

  elif call.data == "show_accounts":
    accs = u_data.get("accounts", [])
    if accs:
      text = f"👤 **الحسابات المضافة:** (`{len(accs)}`)\n\n"
      for i, acc in enumerate(accs, 1):
        text += (
            f"{i}. {acc.get('first_name')} (@{acc.get('username', 'لا يوجد')})\n"
        )
      keyboard = [
          [
              InlineKeyboardButton(
                  "➕ إضافة حساب آخر", callback_data="add_account"
              )
          ],
          [
              InlineKeyboardButton(
                  "🗑️ حذف جميع الحسابات", callback_data="clear_accounts"
              )
          ],
          [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
      ]
      await call.message.edit_text(
          text, reply_markup=InlineKeyboardMarkup(keyboard)
      )
    else:
      await call.message.edit_text(
          "❌ ليس لديك أي حسابات مضافة.",
          reply_markup=InlineKeyboardMarkup([[
              InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")
          ], [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]),
      )

  elif call.data == "add_account":
    u_data["state"] = "waiting_for_phone"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +9665xxxxxxxx):",
        reply_markup=back_menu(),
    )

  elif call.data == "clear_accounts":
    u_data["accounts"] = []
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🗑️ تم حذف جميع الحسابات.", reply_markup=back_menu()
    )

  elif call.data == "show_groups":
    groups = u_data.get("groups", [])
    paused = u_data.get("paused_groups", [])
    text = f"👥 **السوبرات والمجموعات المضافة:** (`{len(groups)}`)\n\n"
    for i, g in enumerate(groups, 1):
      status = "⏸️ (موقوفة مؤقتاً)" if g in paused else "🟢 (نشطة)"
      text += f"{i}. `{g}` - {status}\n"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة سوبر", callback_data="add_group")],
        [
            InlineKeyboardButton(
                "🔄 تبديل حالة مجموعة", callback_data="toggle_group_pause"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑️ تفريغ السوبرات", callback_data="clear_groups"
            )
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )

  elif call.data == "add_group":
    u_data["state"] = "waiting_for_group"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "📥 أرسل معرف السوبر أو الرابط (مثال: `@Group`):",
        reply_markup=back_menu(),
    )

  elif call.data == "toggle_group_pause":
    u_data["state"] = "waiting_for_toggle_group"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🔄 أرسل معرف السوبر الذي تريد إيقافه مؤقتاً أو تفعيله:",
        reply_markup=back_menu(),
    )

  elif call.data == "show_paused_groups":
    paused = u_data.get("paused_groups", [])
    text = f"⏸️ **المجموعات الموقوفة مؤقتاً:** (`{len(paused)}`)\n\n"
    for i, g in enumerate(paused, 1):
      text += f"{i}. `{g}`\n"
    await call.message.edit_text(text, reply_markup=back_menu())

  elif call.data == "show_stats":
    stats = u_data.get("stats", {"success": 0, "failed": 0})
    text = (
        f"📊 **إحصائيات النشر الخاصة بك:**\n\n✅ الرسائل الناجحة:"
        f" `{stats.get('success', 0)}`\n❌ الرسائل الفاشلة:"
        f" `{stats.get('failed', 0)}`\n"
    )
    await call.message.edit_text(text, reply_markup=back_menu())

  elif call.data == "clear_groups":
    u_data["groups"] = []
    u_data["paused_groups"] = []
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🗑️ تم تفريغ قائمة السوبرات.", reply_markup=back_menu()
    )

  elif call.data == "show_texts":
    texts = u_data.get("texts", [])
    text = f"✉️ **رسائل والوسائط المحفوظة:** (`{len(texts)}`)\n\n"
    for i, t in enumerate(texts, 1):
      if isinstance(t, str):
        preview = t[:40] + "..." if len(t) > 40 else t
      else:
        m_type = t.get("type")
        preview = (
            f"[{m_type.upper()}] "
            + (t.get("caption", "")[:30] or "بدون وصف")
        )
      text += f"{i}. {preview}\n"
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ إضافة رسالة/وسائط جديدة", callback_data="add_text"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑️ حذف جميع الرسائل", callback_data="clear_texts"
            )
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )

  elif call.data == "add_text":
    u_data["state"] = "waiting_for_text"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "✍️ أرسل نص رسالة النشر أو صورة/فيديو مع الكابشن الآن:",
        reply_markup=back_menu(),
    )

  elif call.data == "clear_texts":
    u_data["texts"] = []
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "🗑️ تم حذف جميع الرسائل.", reply_markup=back_menu()
    )

  elif call.data == "set_time":
    u_data["state"] = "waiting_for_time"
    save_user_data(user_id, u_data)
    await call.message.edit_text(
        "⏱️ أرسل مدة النشر الأساسية بالثواني (مثلاً 120):",
        reply_markup=back_menu(),
    )

  elif call.data == "start_pub":
    if (
        not u_data.get("accounts")
        or not u_data.get("texts")
        or not u_data.get("groups")
    ):
      await call.answer(
          "❌ يجب إضافة حساب، ورسالة/وسائط، ومجموعة واحدة على الأقل أولاً!",
          show_alert=True,
      )
    else:
      u_data["active"] = True
      save_user_data(user_id, u_data)
      await call.answer("🟢 تم تفعيل النشر التلقائي بنجاح!", show_alert=True)

  elif call.data == "stop_pub":
    u_data["active"] = False
    save_user_data(user_id, u_data)
    await call.answer("🔴 تم إيقاف النشر التلقائي.", show_alert=True)

  try:
    await call.answer()
  except:
    pass


@app.on_message(~filters.command("start"))
async def message_handler(client, message):
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
  u_data = load_user_data(user_id)

  if u_data.get("banned", False) and not admin_status:
    return

  state = u_data.get("state")
  if not state:
    return

  if state == "waiting_for_new_dev_id":
    if not admin_status:
      return
    try:
      new_dev_id = int(message.text.strip())
      settings = load_settings()
      if new_dev_id not in settings["developers"]:
        settings["developers"].append(new_dev_id)
        save_settings(settings)
        await message.reply_text(
            f"✅ تم إضافة الآيدي (`{new_dev_id}`) لقائمة المطورين بنجاح وأصبح لديه"
            " صلاحيات لوحة الأدمن!",
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
    save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_remove_dev_id":
    if not admin_status:
      return
    try:
      rem_dev_id = int(message.text.strip())
      settings = load_settings()
      if rem_dev_id in settings["developers"]:
        settings["developers"].remove(rem_dev_id)
        save_settings(settings)
        await message.reply_text(
            f"🗑️ تمت إزالة الآيدي (`{rem_dev_id}`) من قائمة المطورين بنجاح.",
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
    save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_admin_broadcast":
    if not admin_status:
      return
    u_data["state"] = None
    save_user_data(user_id, u_data)

    success = 0
    failed = 0
    status_msg = await message.reply_text("⏳ جاري بدء الإذاعة لجميع المشتركين...")

    all_users = list(users_col.find())
    for target in all_users:
      target_id = target["_id"]
      try:
        await message.copy(chat_id=int(target_id))
        success += 1
        await asyncio.sleep(0.1)
      except Exception:
        failed += 1

    await status_msg.edit_text(
        f"✅ تمت الإذاعة بنجاح! 🚀\n\n- تم الإرسال إلى: {success} مستخدم\n- فشل"
        f" الإرسال لـ: {failed} مستخدم",
        reply_markup=main_menu(admin_status),
    )
    return

  elif state == "waiting_for_ban_user_id":
    if not admin_status:
      return
    target_id = message.text.strip()
    u_data["state"] = None
    save_user_data(user_id, u_data)

    target_data = load_user_data(target_id)
    current_status = target_data.get("banned", False)
    new_status = not current_status
    target_data["banned"] = new_status
    save_user_data(target_id, target_data)

    msg_result = (
        f"🚫 تم حظر المستخدم (`{target_id}`) بنجاح."
        if new_status
        else f"🟢 تم إلغاء حظر المستخدم (`{target_id}`) بنجاح."
    )
    await message.reply_text(msg_result, reply_markup=main_menu(admin_status))
    return

  elif state == "waiting_for_new_welcome":
    if not admin_status:
      return
    settings = load_settings()
    settings["welcome_message"] = message.text
    save_settings(settings)
    u_data["state"] = None
    save_user_data(user_id, u_data)
    await message.reply_text(
        "✅ تم تحديث رسالة الترحيب بنجاح!", reply_markup=main_menu(admin_status)
    )
    return

  elif state == "waiting_for_phone":
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
      u_data["state"] = "waiting_for_otp"
      save_user_data(user_id, u_data)
      await message.reply_text(
          "📥 تم إرسال كود التحقق من تيليجرام. **أرسل الكود هنا الآن:**"
      )
    except Exception as e:
      await message.reply_text(f"❌ حدث خطأ في رقم الهاتف: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_otp":
    attempt = login_attempts.get(user_id)
    if not attempt:
      await message.reply_text(
          "❌ انتهت الجلسة، الرجاء إعادة إرسال رقم الهاتف من لوحة التحكم."
      )
      u_data["state"] = None
      save_user_data(user_id, u_data)
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
          "username": me.username if me.username else "لا يوجد",
          "first_name": me.first_name,
      }

      u_data["accounts"].append(account_info)
      await attempt["client"].disconnect()
      del login_attempts[user_id]
      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(
          "✅ تم ربط الحساب بنجاح وإضافته لقائمتك!",
          reply_markup=main_menu(admin_status),
      )

    except SessionPasswordNeeded:
      u_data["state"] = "waiting_for_password"
      save_user_data(user_id, u_data)
      await message.reply_text(
          "🔐 هذا الحساب محمي بكلمة مرور (التحقق بخطوتين). **أرسل كلمة المرور"
          " الآن:**"
      )
    except Exception as e:
      await message.reply_text(f"❌ حدث خطأ في الكود: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_password":
    attempt = login_attempts.get(user_id)
    if not attempt:
      await message.reply_text("❌ انتهت الجلسة، الرجاء إعادة إرسال رقم الهاتف.")
      u_data["state"] = None
      save_user_data(user_id, u_data)
      return
    try:
      await attempt["client"].check_password(message.text)
      me = await attempt["client"].get_me()
      session_str = await attempt["client"].export_session_string()

      account_info = {
          "session_string": session_str,
          "id": me.id,
          "username": me.username if me.username else "لا يوجد",
          "first_name": me.first_name,
      }

      u_data["accounts"].append(account_info)
      await attempt["client"].disconnect()
      del login_attempts[user_id]
      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(
          "✅ تم التحقق من كلمة المرور وربط الحساب بنجاح!",
          reply_markup=main_menu(admin_status),
      )

    except Exception as e:
      await message.reply_text(f"❌ كلمة المرور غير صحيحة: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_group":
    try:
      group_input = message.text.strip()
      if "t.me/" in group_input:
        group_input = "@" + group_input.split("t.me/")[-1].strip("/")
      elif not group_input.startswith("@"):
        group_input = "@" + group_input

      u_data["groups"].append(group_input)
      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(
          f"✅ تم إضافة السوبر بنجاح: {group_input}",
          reply_markup=main_menu(admin_status),
      )
    except Exception as e:
      await message.reply_text(f"❌ حدث خطأ: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_toggle_group":
    try:
      g_input = message.text.strip()
      if not g_input.startswith("@"):
        g_input = "@" + g_input

      paused = u_data.setdefault("paused_groups", [])
      if g_input in paused:
        paused.remove(g_input)
        msg = f"🟢 تم إلغاء الإيقاف المؤقت وإعادة تفعيل المجموعة: {g_input}"
      else:
        paused.append(g_input)
        msg = f"⏸️ تم إيقاف النشر في المجموعة مؤقتاً: {g_input}"

      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(msg, reply_markup=main_menu(admin_status))
    except Exception as e:
      await message.reply_text(f"❌ حدث خطأ: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_text":
    try:
      msg_data = {}
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
        await message.reply_text("❌ يرجى إرسال نص، صورة، أو فيديو فقط!")
        return

      u_data["texts"].append(msg_data)
      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(
          "✅ تم حفظ وإضافة الرسالة/الوسائط بنجاح.",
          reply_markup=main_menu(admin_status),
      )
    except Exception as e:
      await message.reply_text(f"❌ حدث خطأ: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return

  elif state == "waiting_for_time":
    try:
      u_data["delay"] = int(message.text)
      u_data["state"] = None
      save_user_data(user_id, u_data)
      await message.reply_text(
          "✅ تم ضبط وقت النشر بنجاح.", reply_markup=main_menu(admin_status)
      )
    except Exception as e:
      await message.reply_text(f"❌ يجب إدخال رقم صحيح بالثواني: {e}")
      u_data["state"] = None
      save_user_data(user_id, u_data)
    return


# --- سيرفر الويب المدمج (لمنع البوت من النوم على Render) ---
async def handle_ping(reader, writer):
  try:
    await reader.read(100)
    response = (
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length:"
        " 15\r\n\r\nBot is running!"
    )
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
  server = await asyncio.start_server(handle_ping, "0.0.0.0", port)
  print(f"Web server started on port {port}")

  # تشغيل محرك النشر الخلفي في الخلفية
  asyncio.create_task(background_publisher())

  # بدء تشغيل البوت
  await app.start()
  print("البوت يعمل الآن بنجاح مع قاعدة بيانات MongoDB وسيرفر الويب المدمج...")

  await idle()
  await app.stop()


if __name__ == "__main__":
  loop = asyncio.get_event_loop()
  loop.run_until_complete(main())

