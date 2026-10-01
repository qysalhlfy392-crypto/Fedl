import asyncio
import random
import os
import time
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.types import ChatBannedRights
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError, AuthKeyUnregisteredError

# ============================================================
#                       الإعدادات العامة
# ============================================================
API_ID = 31594689
API_HASH = "5d8c914c4ad11bd0b572aec0f47f4bb7"

# المجلدات والملفات الخاصة بالحسابات
SESSIONS_DIR = Path("user_sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
ACCOUNTS_FILE = "accounts.json"

# ============================================================
#                       إدارة الحسابات
# ============================================================
class AccountManager:
    def __init__(self):
        self.accounts = {}  
        self.load_accounts()
    
    def load_accounts(self):
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for user_id, user_accs in data.items():
                    uid = int(user_id)
                    if isinstance(user_accs, dict) and "session" in user_accs:
                        user_accs = [user_accs]
                    
                    self.accounts[uid] = []
                    for info in user_accs:
                        self.accounts[uid].append({
                            "session": info.get("session", ""),
                            "client": None,
                            "data": {
                                "word_list": info.get("word_list", []),
                                "spam_running": False,
                                "spam_delay": 0.5,
                                "spam_task": None,
                                "spam_target_msg_id": None,
                                "line_running": False,
                                "line_target_id": None,
                                "line_chat_id": None,
                                "line_delay": 1.0,
                                "line_task": None,
                                "follow_running": False,
                                "followed_user_id": info.get("followed_user_id", None),
                                "follow_chat_id": info.get("follow_chat_id", None),
                                "muted_users": set(tuple(x) for x in info.get("muted_users", [])),
                                "forward_running": False,
                                "forward_delay": 1.0,
                                "forward_task": None,
                                "selected_messages": info.get("selected_messages", []),
                                "anti_flood_enabled": info.get("anti_flood_enabled", False),
                                "space_char": info.get("space_char", None),
                                "time_name_enabled": info.get("time_name_enabled", False),
                                "time_font_style": info.get("time_font_style", 1),
                                "time_name_task": info.get("time_name_task", None),
                                "original_first_name": info.get("original_first_name", None),
                                "monitored_chats": info.get("monitored_chats", {}),
                                "user_absent_monitors": info.get("user_absent_monitors", {}),
                                "absent_tasks": {},
                                "stats": info.get("stats", {"spam": 0, "follow": 0, "forward": 0, "delete": 0, "flash": 0}),
                                "user_info": info.get("user_info", {}),
                                "tracked_targets": info.get("tracked_targets", {})
                            }
                        })
    
    def save_accounts(self):
        data = {}
        for user_id, user_accs in self.accounts.items():
            accs_list = []
            for info in user_accs:
                accs_list.append({
                    "session": info["session"],
                    "word_list": info["data"]["word_list"],
                    "followed_user_id": info["data"]["followed_user_id"],
                    "follow_chat_id": info["data"]["follow_chat_id"],
                    "muted_users": [list(x) for x in info["data"]["muted_users"]],
                    "selected_messages": info["data"]["selected_messages"],
                    "anti_flood_enabled": info["data"]["anti_flood_enabled"],
                    "space_char": info["data"].get("space_char", None),
                    "time_name_enabled": info["data"].get("time_name_enabled", False),
                    "time_font_style": info["data"].get("time_font_style", 1),
                    "original_first_name": info["data"].get("original_first_name", None),
                    "monitored_chats": info["data"].get("monitored_chats", {}),
                    "stats": info["data"]["stats"],
                    "user_info": info["data"]["user_info"],
                    "tracked_targets": info["data"].get("tracked_targets", {})
                })
               
            data[str(user_id)] = accs_list
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    async def add_account_interactive(self):
        print("\n--- تسجيل دخول حساب جديد ---")
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        try:
            await client.connect()
            phone = input("أدخل رقم هاتفك مع رمز الدولة (مثال: +96478xxxxxxxx): ").strip()
            await client.send_code_request(phone)
            code = input("أدخل كود التحقق الذي وصلك على تليجرام: ").strip()
            try:
                await client.sign_in(phone=phone, code=code.replace(" ", ""))
            except SessionPasswordNeededError:
                password = input("الحساب محمي بالتحقق بخطوتين. أرسل كلمة المرور: ").strip()
                await client.sign_in(password=password)
            
            session_str = client.session.save()
            me = await client.get_me()
            await client.disconnect()
            
            self._save_new_account(me, session_str)
            print(f"✅ تم تسجيل الدخول بنجاح لـ {me.first_name}!")
            return me.id
        except Exception as e:
            await client.disconnect()
            print(f"❌ خطأ أثناء تسجيل الدخول: {e}")
            return None

    def _save_new_account(self, me, session_string):
        user_id = me.id
        if user_id not in self.accounts:
            self.accounts[user_id] = []
        
        for acc in self.accounts[user_id]:
            if acc["session"] == session_string:
                return
        
        new_acc = {
            "session": session_string,
            "client": None,
            "data": {
                "word_list": [],
                "spam_running": False,
                "spam_delay": 0.5,
                "spam_task": None,
                "spam_target_msg_id": None,
                "line_running": False,
                "line_target_id": None,
                "line_chat_id": None,
                "line_delay": 1.0,
                "line_task": None,
                "follow_running": False,
                "followed_user_id": None,
                "follow_chat_id": None,
                "muted_users": set(),
                "forward_running": False,
                "forward_delay": 1.0,
                "forward_task": None,
                "selected_messages": [],
                "anti_flood_enabled": False,
                "space_char": None,
                "time_name_enabled": False,
                "time_font_style": 1,
                "time_name_task": None,
                "original_first_name": me.first_name,
                "monitored_chats": {},
                "user_absent_monitors": {},
                "absent_tasks": {},
                "stats": {"spam": 0, "follow": 0, "forward": 0, "delete": 0, "flash": 0},
                "user_info": {"id": me.id, "first_name": me.first_name, "username": me.username},
                "tracked_targets": {}
            }
        }
        self.accounts[user_id].append(new_acc)
        self.save_accounts()

    async def start_all_user_accounts(self):
        for user_id, user_accs in self.accounts.items():
            for acc in user_accs:
                if not acc["client"]:
                    try:
                        client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                        await client.start()
                        acc["client"] = client
                        
                        me = await client.get_me()
                        if not acc["data"].get("original_first_name"):
                            clean_name = me.first_name
                            for suffix in [" | 𝟥:𝟢𝟨", " | 𝟑:𝟎𝟕", " | 𝟯:𝟬𝳀", " | 𝟛:𝟘𝟠"]:
                                if suffix in clean_name:
                                    clean_name = clean_name.split(" | ")[0]
                            acc["data"]["original_first_name"] = clean_name
                        
                        self.register_handlers(user_id, client, acc)
                        
                        if acc["data"].get("time_name_enabled", False):
                            self.start_time_name_loop(client, acc["data"])
                        print(f"✅ تم تشغيل السورس بنجاح على حساب: {me.first_name}")
                    except Exception as e:
                        print(f"⚠️ فشل تشغيل الحساب: {e}")

    def start_time_name_loop(self, client, data):
        if data.get("time_name_task"):
            data["time_name_task"].cancel()

        def convert_digits(text, style):
            maps = {
                1: {"0": "𝟢", "1": "𝟣", "2": "𝟤", "3": "𝟥", "4": "𝟦", "5": "𝟧", "6": "𝟨", "7": "𝟩", "8": "𝟪", "9": "𝟫"},
                2: {"0": "𝟎", "1": "𝟏", "2": "𝟐", "3": "𝟑", "4": "𝟒", "5": "𝟓", "6": "𝟔", "7": "𝟕", "8": "𝟖", "9": "𝟗"},
                3: {"0": "𝟯", "1": "𝟭", "2": "𝟮", "3": "𝟯", "4": "𝟰", "5": "𝟱", "6": "𝟲", "7": "𝟳", "8": "𝟴", "9": "𝟵"},
                4: {"0": "𝟘", "1": "𝟙", "2": "𝟚", "3": "𝟛", "4": "𝟜", "5": "𝟝", "6": "𝟞", "7": "𝟟", "8": "𝟠", "9": "𝟡"}
            }
            m = maps.get(style, maps[1])
            return "".join([m.get(char, char) for char in text])

        async def loop():
            while data.get("time_name_enabled", False):
                try:
                    now_iraq = datetime.now(ZoneInfo("Asia/Baghdad"))
                    hour_12 = now_iraq.strftime("%I")
                    minute = now_iraq.strftime("%M")
                    time_str = f"{hour_12}:{minute}"
                    
                    styled_time = convert_digits(time_str, data.get("time_font_style", 1))
                    
                    orig_name = data.get("original_first_name")
                    if not orig_name:
                        me = await client.get_me()
                        orig_name = me.first_name
                        for suffix in [" | 𝟥:𝟢𝟨", " | 𝟑:𝟎𝟕", " | 𝟯:𝟬𝳀", " | 𝟛:𝟘𝟠"]:
                            if suffix in orig_name:
                                orig_name = orig_name.split(" | ")[0]
                        data["original_first_name"] = orig_name
                    
                    new_first_name = f"{orig_name} | {styled_time}"
                    if len(new_first_name) > 64:
                        new_first_name = new_first_name[:64]
                    
                    await client(UpdateProfileRequest(first_name=new_first_name))
                except Exception as e:
                    print(f"خطأ في تحديث الاسم الوقتي: {e}")
                
                await asyncio.sleep(60)

        data["time_name_task"] = asyncio.create_task(loop())
    def register_handlers(self, user_id, client, data_dict):
        data = data_dict["data"]
        
        if "delete" not in data["stats"]:
            data["stats"]["delete"] = 0
        if "flash" not in data["stats"]:
            data["stats"]["flash"] = 0
        if "line_running" not in data:
            data["line_running"] = False
        if "line_target_id" not in data:
            data["line_target_id"] = None
        if "line_chat_id" not in data:
            data["line_chat_id"] = None
        if "line_delay" not in data:
            data["line_delay"] = 1.0
        if "line_task" not in data:
            data["line_task"] = None
        if "space_char" not in data:
            data["space_char"] = None
        if "time_name_enabled" not in data:
            data["time_name_enabled"] = False
        if "time_font_style" not in data:
            data["time_font_style"] = 1
        if "monitored_chats" not in data:
            data["monitored_chats"] = {}
        if "user_absent_monitors" not in data:
            data["user_absent_monitors"] = {}
        if "absent_tasks" not in data:
            data["absent_tasks"] = {}
        if "muted_users" not in data:
            data["muted_users"] = set()
        if "tracked_targets" not in data:
            data["tracked_targets"] = {}

        def format_text(text):
            char = data.get("space_char")
            if char and text:
                return text.replace(" ", f" {char} ")
            return text

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اوامري$'))
        async def show_all_commands(event):
            help_text = (
                "🤖 **قائمة أوامر ومميزات سورس كوتو:**\n\n"
                "⏱️ **أوامر الوقت والاسم:**\n"
                "• `.تفعيل الوقت` - تفعيل الاسم الوقتي بتوقيت العراق\n"
                "• `.تعطيل الوقت` - إيقاف الاسم الوقتي\n"
                "• `.خطوطي` - عرض خطوط الساعة المتاحة\n"
                "• `.تفعيل [1-4]` - تغيير خط الساعة\n\n"
                "✨ **أوامر المسافات والحركة:**\n"
                "• `.فعل [1-6]` - إضافة رموز والحركات للمسافات\n"
                "• `.تعطيل` - إلغاء رموز المسافات\n\n"
                "🚀 **أوامر التكرار والتسطير والتتبع:**\n"
                "• `.اضف كلمات` - (بالرد على ملف txt) لإضافة كلمات التكرار\n"
                "• `.تكرار` - (بالرد على شخص) لبدء التكرار\n"
                "• `.خلاص` - إيقاف التكرار\n"
                "• `.سرعة [رقم]` - ضبط سرعة التكرار\n"
                "• `.تسطير` - (بالرد على شخص) لبدء التسطير بالكلمات\n"
                "• `.قف` - إيقاف التسطير\n"
                "• `.سطر [رقم]` - ضبط سرعة التسطير\n"
                "• `.تتبع` - (بالرد على شخص) لتتبعه (يدعم عدة أشخاص)\n"
                "• `.كافي` - إيقاف تتبع المستخدم\n"
                "• `.كافي الكل` - إيقاف جميع التتبعات\n\n"
                "🔇 **أوامر الكتم والحماية:**\n"
                "• `.كتم` - (بالرد على شخص) لكتمه وحذف رسائله تلقائياً\n"
                "• `.فكه` - (بالرد على شخص) لإلغاء الكتم الفردي\n"
                "• `.مسح المكتومين` - مسح جميع الأشخاص المكتومين دفعة واحدة\n"
                "• `.تفعيل حماية` / `.تعطيل حماية` - التحكم بحماية الفلود\n"
                "• `.مراقبه` - (رد على شخص) لمراقبة غيابه\n"
                "• `.بطل` - لإيقاف مراقبة غياب المستخدم فردياً\n"
                "• `.مسح المراقبين` - إيقاف ومسح جميع مراقبات الغياب دفعة واحدة\n"
                "• `.راقب` - تفعيل مراقبة رسائلك المحذوفة في الشات الحالي\n"
                "• `.توقف` - إيقاف مراقبة الحذف في الشات الحالي\n"
                "• `.مسح` - مسح آخر 1000 رسالة خاصة بك في الشات\n"
                "• `.فلش` - طرد الأعضاء غير المشرفين من المجموعة\n\n"
                "🔄 **أوامر التحويل (Forward):**\n"
                "• `.تحديد` - (رد على رسالة بالمحفوظات) لإضافتها للتحويل\n"
                "• `.لتحدد` - إزالة رسالة من قائمة التحويل\n"
                "• `.اعاده` - مسح قائمة التحويل بالكامل\n"
                "• `.on` / `.off` - تشغيل وإيقاف التحويل المستمر\n"
                "• `delay [رقم]` - ضبط سرعة التحويل"
            )
            await event.edit(help_text)

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.كتم$'))
        async def mute_user_cmd(event):
            if not event.is_reply:
                await event.edit("❌ **يجب الرد على الشخص المراد كتمه بكلمة `.كتم`!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            target_user = await reply.get_sender()
            if not target_user:
                await event.edit("❌ **لم يتم التعرف على المستخدم المستهدف!**")
                await asyncio.sleep(2)
                await event.delete()
                return

            chat_id = event.chat_id
            target_id = target_user.id
            key = (chat_id, target_id)

            data["muted_users"].add(key)
            self.save_accounts()

            await event.edit(f"🔇 **تم كتم المستخدم:** `{target_user.first_name}` **في هذا الشات بنجاح!**\nسيتم حذف رسائله تلقائياً فور إرسالها.")
            await asyncio.sleep(2.5)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فكه$'))
        async def unmute_user_cmd(event):
            if not event.is_reply:
                await event.edit("❌ **يجب الرد على الشخص المراد إلغاء كتمه بكلمة `.فكه`!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            target_user = await reply.get_sender()
            if not target_user:
                await event.edit("❌ **لم يتم التعرف على المستخدم المستهدف!**")
                await asyncio.sleep(2)
                await event.delete()
                return

            chat_id = event.chat_id
            target_id = target_user.id
            key = (chat_id, target_id)

            if key in data["muted_users"]:
                data["muted_users"].remove(key)
                self.save_accounts()
                await event.edit(f"🔊 **تم إلغاء كتم المستخدم:** `{target_user.first_name}` **في هذا الشات.**")
            else:
                await event.edit("⚠️ **هذا المستخدم ليس مكتوماً في هذا الشات أساساً.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مسح المكتومين$'))
        async def clear_all_mutes_cmd(event):
            count = len(data["muted_users"])
            data["muted_users"].clear()
            self.save_accounts()
            await event.edit(f"🧹 **تم مسح جميع المكتومين بنجاح!** (عدد المحذوفين: `{count}`)")
            await asyncio.sleep(2.5)
            await event.delete()

        @client.on(events.NewMessage)
        async def handle_muted_user_messages(event):
            try:
                if not event.sender_id or event.out:
                    return
                
                chat_id = event.chat_id
                sender_id = event.sender_id
                key = (chat_id, sender_id)

                if key in data["muted_users"]:
                    try:
                        await event.delete()
                    except Exception:
                        if not event.is_private:
                            chat = await event.get_chat()
                            me = await client.get_me()
                            try:
                                participant = await client.get_permissions(chat, me)
                                if participant.is_admin or participant.is_creator:
                                    banned_rights = ChatBannedRights(until_date=None, view_messages=False, send_messages=True)
                                    await client(EditBannedRequest(chat.id, sender_id, banned_rights))
                            except:
                                pass
            except Exception as e:
                print(f"خطأ في معالجة رسائل المكتومين: {e}")

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل الوقت$'))
        async def enable_time_name(event):
            data["time_name_enabled"] = True
            me = await client.get_me()
            orig = me.first_name
            for suffix in [" | 𝟥:𝟢𝟨", " | 𝟑:𝟎𝟕", " | 𝟯:𝟬𝳀", " | 𝟯:𝟬7", " | 𝟛:𝟘𝟠"]:
                if suffix in orig:
                    orig = orig.split(" | ")[0]
            data["original_first_name"] = orig
            self.save_accounts()
            self.start_time_name_loop(client, data)
            await event.edit("✅ **تم تفعيل ميزة الاسم الوقتي بتوقيت العراق بنجاح!**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تعطيل الوقت$'))
        async def disable_time_name(event):
            data["time_name_enabled"] = False
            if data.get("time_name_task"):
                data["time_name_task"].cancel()
                data["time_name_task"] = None
            try:
                orig = data.get("original_first_name")
                if orig:
                    await client(UpdateProfileRequest(first_name=orig))
            except:
                pass
            self.save_accounts()
            await event.edit("⚠️ **تم تعطيل ميزة الاسم الوقتي وإعادة اسمك الأصلي.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خطوطي$'))
        async def show_time_fonts(event):
            await event.edit(
                "📋 **قائمة خطوط الساعة المتاحة لتغيير خط الاسم الوقتي:**\n\n"
                "• `.تفعيل 1` - يتحول خط الساعه إلى: `𝟥:𝟢𝟨`\n"
                "• `.تفعيل 2` - يتحول خط الساعه إلى: `𝟑:𝟎𝟕`\n"
                "• `.تفعيل 3` - يتحول خط الساعه إلى: `𝟯:𝟬𝟳`\n"
                "• `.تفعيل 4` - يتحول خط الساعه إلى: `𝟛:𝟘𝟠`"
            )
            await asyncio.sleep(10)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل 1$'))
        async def set_time_font_1(event):
            data["time_font_style"] = 1
            self.save_accounts()
            await event.edit("✅ **تم تغيير خط الساعة إلى:** `𝟥:𝟢𝟨`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل 2$'))
        async def set_time_font_2(event):
            data["time_font_style"] = 2
            self.save_accounts()
            await event.edit("✅ **تم تغيير خط الساعة إلى:** `𝟑:𝟎𝟕`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل 3$'))
        async def set_time_font_3(event):
            data["time_font_style"] = 3
            self.save_accounts()
            await event.edit("✅ **تم تغيير خط الساعة إلى:** `𝟯:𝟬𝟳`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل 4$'))
        async def set_time_font_4(event):
            data["time_font_style"] = 4
            self.save_accounts()
            await event.edit("✅ **تم تغيير خط الساعة إلى:** `𝟛:𝟘𝟠`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 1$'))
        async def set_space_1(event):
            data["space_char"] = "~"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `~`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 2$'))
        async def set_space_2(event):
            data["space_char"] = "+"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `+`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 3$'))
        async def set_space_3(event):
            data["space_char"] = "-"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `-`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 4$'))
        async def set_space_4(event):
            data["space_char"] = "×"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `×`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 5$'))
        async def set_space_5(event):
            data["space_char"] = "～"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `～`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فعل 6$'))
        async def set_space_6(event):
            data["space_char"] = "✞"
            self.save_accounts()
            await event.edit("✅ **تم تفعيل ميزة المسافات بالحركة:** `✞`")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تعطيل$'))
        async def disable_space(event):
            data["space_char"] = None
            self.save_accounts()
            await event.edit("⚠️ **تم تعطيل ميزة المسافات بنجاح.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage)
        async def track_user_activity_for_absence(event):
            try:
                if not event.sender_id:
                    return
                sender_id = event.sender_id
                chat_id = event.chat_id
                key = (chat_id, sender_id)
                
                if key in data["user_absent_monitors"]:
                    chat_username = getattr(event.chat, 'username', None) if hasattr(event, 'chat') and event.chat else None
                    if chat_id < 0:
                        clean_cid = str(chat_id).replace('-100', '')
                        msg_link = f"https://t.me/c/{clean_cid}/{event.id}"
                    elif chat_username:
                        msg_link = f"https://t.me/{chat_username}/{event.id}"
                    else:
                        msg_link = f"مجموعة ID: `{chat_id}`"

                    data["user_absent_monitors"][key]["last_seen"] = time.time()
                    data["user_absent_monitors"][key]["last_msg_link"] = msg_link
                    
                    if key in data["absent_tasks"]:
                        data["absent_tasks"][key].cancel()
                    
                    async def check_absence_loop():
                        try:
                            while key in data["user_absent_monitors"]:
                                await asyncio.sleep(180)
                                info = data["user_absent_monitors"].get(key)
                                if not info:
                                    break
                                user_name = info.get("name", "مستخدم")
                                user_username = f"@{info.get('username')}" if info.get("username") else "لا يوجد يوزر"
                                msg_link_val = info.get("last_msg_link", "غير متوفر")
                                
                                alert_text = (
                                    f"⏰ **تنبيه غياب مستخدم!**\n\n"
                                    f"👤 الشخص: **{user_name}**\n"
                                    f"🔗 المعرف: {user_username}\n"
                                    f"🆔 الآيدي: `{sender_id}`\n"
                                    f"⏳ ما زال غائباً عن الشات لمدة **3 دقائق أخرى**.\n"
                                    f"📌 رابط آخر رسالة له: {msg_link_val}"
                                )
                                await client.send_message('me', alert_text)
                        except asyncio.CancelledError:
                            pass

                    data["absent_tasks"][key] = asyncio.create_task(check_absence_loop())
            except Exception as e:
                print(f"خطأ في تتبع غياب المستخدم: {e}")

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مراقبه$'))
        async def monitor_user_absence_cmd(event):
            if not event.is_reply:
                await event.edit("❌ **يجب الرد على الشخص المراد مراقبة غيابه بكلمة `.مراقبه`!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            target_user = await reply.get_sender()
            if not target_user:
                await event.edit("❌ **لم يتم التعرف على المستخدم المستهدف!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            chat_id = event.chat_id
            target_id = target_user.id
            key = (chat_id, target_id)
            
            chat_username = getattr(event.chat, 'username', None) if hasattr(event, 'chat') and event.chat else None
            if chat_id < 0:
                clean_cid = str(chat_id).replace('-100', '')
                msg_link = f"https://t.me/c/{clean_cid}/{reply.id}"
            elif chat_username:
                msg_link = f"https://t.me/{chat_username}/{reply.id}"
            else:
                msg_link = f"مجموعة ID: `{chat_id}`"

            data["user_absent_monitors"][key] = {
                "name": target_user.first_name,
                "username": target_user.username,
                "last_seen": time.time(),
                "last_msg_link": msg_link
            }
            
            if key in data["absent_tasks"]:
                data["absent_tasks"][key].cancel()

            async def check_absence_initial_loop():
                try:
                    while key in data["user_absent_monitors"]:
                        await asyncio.sleep(180)
                        info = data["user_absent_monitors"].get(key)
                        if not info:
                            break
                        user_name = info.get("name", "مستخدم")
                        user_username = f"@{info.get('username')}" if info.get("username") else "لا يوجد يوزر"
                        l_link = info.get("last_msg_link", "غير متوفر")
                        
                        alert_text = (
                            f"⏰ **تنبيه غياب مستخدم!**\n\n"
                            f"👤 الشخص: **{user_name}**\n"
                            f"🔗 المعرف: {user_username}\n"
                            f"🆔 الآيدي: `{target_id}`\n"
                            f"⏳ ما زال غائباً عن الشات لمدة **3 دقائق أخرى**.\n"
                            f"📌 رابط آخر رسالة له: {l_link}"
                        )
                        await client.send_message('me', alert_text)
                except asyncio.CancelledError:
                    pass

            data["absent_tasks"][key] = asyncio.create_task(check_absence_initial_loop())
            
            await event.edit(f"👁️‍🗨️ **تم بدء مراقبة غياب المستخدم:** `{target_user.first_name}`\nسيتم تنبيهك دورياً في المحفوظات كلما غاب لمدة 3 دقائق.")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.بطل$'))
        async def stop_user_absence_cmd(event):
            if not event.is_reply:
                await event.edit("❌ **يجب الرد على الشخص المراد إيقاف مراقبته بكلمة `.بطل`!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            target_user = await reply.get_sender()
            if not target_user:
                await event.edit("❌ **لم يتم التعرف على المستخدم المستهدف!**")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            chat_id = event.chat_id
            target_id = target_user.id
            key = (chat_id, target_id)
            
            if key in data["user_absent_monitors"]:
                del data["user_absent_monitors"][key]
                if key in data["absent_tasks"]:
                    data["absent_tasks"][key].cancel()
                    del data["absent_tasks"][key]
                await event.edit(f"⚠️ **تم إيقاف مراقبة غياب المستخدم:** `{target_user.first_name}`")
            else:
                await event.edit("⚠️ **هذا المستخدم ليس قيد المراقبة في هذا الشات أساساً.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مسح المراقبين$'))
        async def clear_all_absent_monitors_cmd(event):
            for t in data["absent_tasks"].values():
                t.cancel()
            data["absent_tasks"].clear()
            count = len(data["user_absent_monitors"])
            data["user_absent_monitors"].clear()
            await event.edit(f"🧹 **تم مسح وإيقاف جميع مراقبات الغياب بنجاح!** (عددها: `{count}`)")
            await asyncio.sleep(2.5)
            await event.delete()

        @client.on(events.MessageDeleted)
        async def monitor_deleted_messages(event):
            try:
                chat_id = event.chat_id
                if chat_id not in data["monitored_chats"]:
                    return

                me = await client.get_me()
                for msg_id in event.deleted_ids:
                    try:
                        msg_obj = await client.get_messages(chat_id, ids=msg_id)
                        if msg_obj and msg_obj.sender_id != me.id:
                            continue
                    except:
                        pass

                    chat = await event.get_chat() if hasattr(event, 'get_chat') else None
                    chat_title = getattr(chat, 'title', 'مجموعة/شات') if chat else 'شات'
                    chat_username = getattr(chat, 'username', None) if chat else None
                    if chat_id < 0:
                        chat_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{msg_id}"
                    elif chat_username:
                        chat_link = f"https://t.me/{chat_username}/{msg_id}"
                    else:
                        chat_link = f"مجموعة ID: `{chat_id}`"

                    alert_msg = (
                        f"🗑️ **تنبيه حذف إحدى رسائلك!**\n\n"
                        f"📍 الشات/المجموعة: **{chat_title}**\n"
                        f"🔗 الرابط: {chat_link}\n"
                        f"🆔 آيدي الرسالة المحذوفة: `{msg_id}`"
                    )
                    await client.send_message('me', alert_msg)
            except Exception as e:
                print(f"خطأ في مراقبة حذف الرسائل: {e}")

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.راقب$'))
        async def start_group_monitor(event):
            chat_id = event.chat_id
            data["monitored_chats"][chat_id] = {"title": getattr(event.chat, 'title', 'شات') if hasattr(event, 'chat') else 'شات'}
            self.save_accounts()
            await event.edit("👁️ **تم تفعيل مراقبة رسائلك في هذا الشات بنجاح!**\nسيتم تنبيهك في المحفوظات عند حذف أي رسالة خاصة بك هنا.")
            await asyncio.sleep(3)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.توقف$'))
        async def stop_group_monitor(event):
            chat_id = event.chat_id
            if chat_id in data["monitored_chats"]:
                del data["monitored_chats"][chat_id]
                self.save_accounts()
                await event.edit("⚠️ **تم إيقاف مراقبة الرسائل في هذا الشات.**")
            else:
                await event.edit("⚠️ **هذا الشات ليس قيد المراقبة أساساً.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.اضف كلمات$'))
        async def add_words(event):
            if not event.is_reply:
                await event.edit("❌ رد على ملف txt!")
                return
            reply = await event.get_reply_message()
            if not reply.document:
                await event.edit("❌ هذا ليس ملفاً!")
                return
            await event.edit("⏳ جاري التحميل...")
            path = await reply.download_media()
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                count = 0
                for line in lines:
                    line = line.strip()
                    if line:
                        data["word_list"].append(line)
                        count += 1
                await event.edit(f"✅ تم إضافة {count} كلمة\n📊 الإجمالي: {len(data['word_list'])}")
                self.save_accounts()
            except Exception as e:
                await event.edit(f"❌ خطأ: {e}")
            finally:
                try:
                    os.remove(path)
                except:
                    pass
            await asyncio.sleep(2)
            await event.delete()
        
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تكرار$'))
        async def start_spam(event):
            if not data["word_list"]:
                await event.edit("❌ لا توجد كلمات! أضف كلمات أولاً")
                await asyncio.sleep(2)
                await event.delete()
                return
            if not event.is_reply:
                await event.edit("❌ يجب الرد على رسالة الشخص المراد التكرار عليه بكلمة `.تكرار`!")
                await asyncio.sleep(2)
                await event.delete()
                return
            if data["spam_running"]:
                await event.edit("⚠️ التكرار يعمل بالفعل!")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            data["spam_target_msg_id"] = reply.id
            data["spam_running"] = True
            chat_id = event.chat_id
            
            await event.edit(f"🚀 بدء التكرار بالرد على المستخدم المستهدف... السرعة: {data['spam_delay']}ث")
            await asyncio.sleep(1)
            await event.delete()
            
            async def spam_loop():
                while data["spam_running"]:
                    word = random.choice(data["word_list"])
                    processed_word = format_text(word)
                    try:
                        if data.get("spam_target_msg_id"):
                            await client.send_message(chat_id, processed_word, reply_to=data["spam_target_msg_id"])
                        else:
                            await client.send_message(chat_id, processed_word)
                        data["stats"]["spam"] += 1
                        self.save_accounts()
                    except FloodWaitError as e:
                        if data["anti_flood_enabled"]:
                            await asyncio.sleep(e.seconds + 2)
                    except Exception as e:
                        pass
                    if data["spam_running"]:
                        await asyncio.sleep(data["spam_delay"])
            data["spam_task"] = asyncio.create_task(spam_loop())
        
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.خلاص$'))
        async def stop_spam(event):
            if not data["spam_running"]:
                await event.edit("⚠️ التكرار متوقف بالفعل")
                await asyncio.sleep(2)
                await event.delete()
                return
            data["spam_running"] = False
            data["spam_target_msg_id"] = None
            if data["spam_task"]:
                data["spam_task"].cancel()
                data["spam_task"] = None
            await event.edit("🛑 تم إيقاف التكرار بنجاح")
            await asyncio.sleep(2)
            await event.delete()
        
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سرعة (\d+\.?\d*)$'))
        async def set_speed(event):
            try:
                delay = float(event.pattern_match.group(1))
                if delay < 0:
                    await event.edit("❌ الوقت يجب أن يكون أكبر من 0")
                else:
                    data["spam_delay"] = delay
                    await event.edit(f"✅ تم ضبط السرعة إلى {delay} ثانية")
            except ValueError:
                await event.edit("❌ قيمة غير صالحة")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تسطير$'))
        async def start_line_spam(event):
            if not data["word_list"]:
                await event.edit("❌ لا توجد كلمات مضافة!")
                await asyncio.sleep(2)
                await event.delete()
                return
            if not event.is_reply:
                await event.edit("❌ يجب الرد على الشخص المراد التسطير عليه بكلمة `.تسطير`!")
                await asyncio.sleep(2)
                await event.delete()
                return
            if data["line_running"]:
                await event.edit("⚠️ ميزة التسطير تعمل بالفعل!")
                await asyncio.sleep(2)
                await event.delete()
                return
            
            reply = await event.get_reply_message()
            target_user = await reply.get_sender()
            if not target_user:
                await event.edit("❌ لم يتم التعرف على المستخدم المستهدف!")
                await asyncio.sleep(2)
                await event.delete()
                return

            data["line_target_id"] = target_user.id
            data["line_chat_id"] = event.chat_id
            data["line_running"] = True
            chat_id = event.chat_id
            
            await event.edit(f"✍️ **بدء عملية التسطير للمستخدم:** `{target_user.first_name}`")
            await asyncio.sleep(1.5)
            await event.delete()
            
            async def line_loop():
                word_index = 0
                try:
                    while data["line_running"]:
                        if not data["word_list"]:
                            break
                        word = data["word_list"][word_index % len(data["word_list"])]
                        word_index += 1
                        processed_word = format_text(word)
                        try:
                            async with client.action(chat_id, 'typing'):
                                await asyncio.sleep(min(data["line_delay"], 2.0))
                            await client.send_message(chat_id, processed_word, reply_to=reply.id)
                            data["stats"]["spam"] += 1
                            self.save_accounts()
                        except FloodWaitError as e:
                            if data["anti_flood_enabled"]:
                                await asyncio.sleep(e.seconds + 2)
                        except Exception as e:
                            pass
                        if data["line_running"]:
                            await asyncio.sleep(data["line_delay"])
                except asyncio.CancelledError:
                    pass

            data["line_task"] = asyncio.create_task(line_loop())

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.قف$'))
        async def stop_line_spam(event):
            if not data["line_running"]:
                await event.edit("⚠️ التسطير متوقف بالفعل.")
                await asyncio.sleep(2)
                await event.delete()
                return
            data["line_running"] = False
            data["line_target_id"] = None
            data["line_chat_id"] = None
            if data["line_task"]:
                data["line_task"].cancel()
                data["line_task"] = None
            await event.edit("🛑 **تم إيقاف التسطير بنجاح.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.سطر\s+(\d+\.?\d*)$'))
        async def set_line_speed(event):
            try:
                delay = float(event.pattern_match.group(1))
                if delay <= 0:
                    await event.edit("❌ يجب أن تكون السرعة أكبر من 0 ثانية.")
                else:
                    data["line_delay"] = delay
                    self.save_accounts()
                    await event.edit(f"✅ **تم ضبط سرعة التسطير لتصبح كل** `{delay}` **ثانية.**")
            except ValueError:
                await event.edit("❌ قيمة غير صالحة.")
            await asyncio.sleep(2)
            await event.delete()
            
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تفعيل حماية$'))
        async def enable_antiflood(event):
            data["anti_flood_enabled"] = True
            self.save_accounts()
            await event.edit("🛡️ **تم تفعيل حماية الفلود بنجاح.**")
            await asyncio.sleep(2)
            await event.delete()

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تعطيل حماية$'))
        async def disable_antiflood(event):
            data["anti_flood_enabled"] = False
            self.save_accounts()
            await event.edit("⚠️ **تم تعطيل حماية الفلود.**")
            await asyncio.sleep(2)
            await event.delete()
            
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.مسح$'))
        async def fast_delete_messages(event):
            chat_id = event.chat_id
            await event.delete()
            deleted_count = 0
            message_ids_to_delete = []
            
            async for msg in client.iter_messages(chat_id, from_user='me', limit=1000):
                message_ids_to_delete.append(msg.id)
                if len(message_ids_to_delete) >= 100:
                    try:
                        await client.delete_messages(chat_id, message_ids_to_delete)
                        deleted_count += len(message_ids_to_delete)
                    except Exception:
                        pass
                    message_ids_to_delete = []
                    await asyncio.sleep(0.1)
            
            if message_ids_to_delete:
                try:
                    await client.delete_messages(chat_id, message_ids_to_delete)
                    deleted_count += len(message_ids_to_delete)
                except Exception:
                    pass
            
            data["stats"]["delete"] += deleted_count
            self.save_accounts()
            notice = await client.send_message(chat_id, f"🗑️ **تم مسح رسائلك بنجاح!** عددها: `{deleted_count}`")
            await asyncio.sleep(3)
            try:
                await notice.delete()
            except:
                pass
            
        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.فلش$'))
        async def flash_group_members(event):
            if not event.is_group:
                await event.edit("❌ **هذا الأمر يعمل داخل المجموعات فقط!**")
                await asyncio.sleep(2)
                await event.delete()
                return

            await event.edit("⚡ **جاري فحص الصلاحيات وبدء التفليش...**")
            chat = await event.get_chat()
            me = await client.get_me()
            
            try:
                participant = await client.get_permissions(chat, me)
                if not participant.is_admin and not participant.is_creator:
                    await event.edit("❌ **أنت لست مشرفاً في هذه المجموعة!**")
                    await asyncio.sleep(2)
                    await event.delete()
                    return
            except Exception as e:
                await event.edit(f"❌ **فشل التحقق:** {e}")
                await asyncio.sleep(2)
                await event.delete()
                return

            kicked_count = 0
            banned_rights = ChatBannedRights(until_date=None, view_messages=True)

            try:
                async for user in client.iter_participants(chat):
                    if user.id == me.id or user.bot:
                        continue
                    try:
                        p = await client.get_permissions(chat, user)
                        if p.is_admin or p.is_creator:
                            continue
                    except:
                        pass

                    try:
                        await client(EditBannedRequest(chat.id, user.id, banned_rights))
                        kicked_count += 1
                        data["stats"]["flash"] += 1
                        self.save_accounts()
                        await asyncio.sleep(0.3)
                    except:
                        pass

                await event.client.send_message(event.chat_id, f"🚀 **تم الانتهاء من التفليش!** المطرودين: `{kicked_count}`")
            except Exception as e:
                await event.client.send_message(event.chat_id, f"❌ حدث خطأ: {e}")
            try:
                await event.delete()
            except:
                pass

        @client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحديد$'))
        async def set_forward_messages(event):
            if not event.is_reply:
                await event.edit("❌ يجب الرد على رسالة في المحفوظات!")
                await asyncio.sleep(3)
                await event.delete()
                return
            reply = await event.get_reply_message()
            me = aw
