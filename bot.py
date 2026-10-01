import asyncio
import random
import os
import time
import math
from telethon import TelegramClient, events
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest

API_ID = 29510141
API_HASH = "14c074a5aed49dc7752a9f8d54cf4ad4"
SESSION = 'spam'

word_list = []
spam_task = None
spam_running = False
spam_delay = 0.0
spam_typing_task = None
follow_running = False
forward_task = None
forward_running = False
forward_delay = 0.5
selected_saved_msg = None
flood_guard_enabled = True

client = TelegramClient(SESSION, API_ID, API_HASH)


class TextFloodGuard:
    def __init__(self, is_premium=False):
        self.is_premium = is_premium
        self.capacity = 40 if is_premium else 20
        self.refill_rate = 3.0 if is_premium else 1.0
        self.tokens = self.capacity
        self.last_update = time.time()

        self.total_sent = 0
        self.daily_limit = 30000 if is_premium else 15000

        self.last_send_times = []

    async def wait_if_needed(self):
        self.total_sent += 1
        now = time.time()

        self.tokens = min(self.capacity, self.tokens + (now - self.last_update) * self.refill_rate)
        self.last_update = now

        self.last_send_times = [t for t in self.last_send_times if now - t < 8]
        instant_rate = len(self.last_send_times) / max(now - self.last_send_times[0], 1) if self.last_send_times else 0
        self.last_send_times.append(now)

        if instant_rate > 2.0:
            wait = min(instant_rate * 1.5, 8)
            print(f"[FLOD] تخفيف {wait:.1f}ث (rate={instant_rate:.1f})")
            await asyncio.sleep(wait)
            self.last_send_times = []

        if self.tokens < 1:
            wait = min((1 - self.tokens) / self.refill_rate, 10)
            await asyncio.sleep(max(wait, 0.05))
            self.tokens = 1

        self.tokens -= 1

    def get_stats(self):
        now = time.time()
        recent = len([t for t in self.last_send_times if now - t < 8])
        rate = recent / max(now - self.last_send_times[0], 1) if self.last_send_times else 0
        return {
            "type": "🟣 Premium" if self.is_premium else "⚪ Free",
            "tokens": f"{self.tokens:.1f}/{self.capacity}",
            "refill": f"{self.refill_rate}/s",
            "rate": f"{rate:.2f} msg/s",
            "total": self.total_sent,
            "daily_max": self.daily_limit,
        }


flood_guard = None


async def keep_typing(chat_id):
    global spam_running
    while spam_running:
        try:
            async with client.action(chat_id, 'typing'):
                await asyncio.sleep(4)
        except:
            pass


async def spam_loop(chat_id, reply_to=None):
    global spam_running
    while spam_running:
        if not word_list:
            spam_running = False
            break
        word = random.choice(word_list)
        try:
            if flood_guard_enabled:
                await flood_guard.wait_if_needed()
            if reply_to:
                await client.send_message(chat_id, word, reply_to=reply_to)
            else:
                await client.send_message(chat_id, word)
        except Exception as e:
            print(f"send error: {e}")
        if spam_delay > 0:
            await asyncio.sleep(spam_delay)


async def forward_loop(chat_id):
    global forward_running
    while forward_running:
        if not selected_saved_msg:
            forward_running = False
            break
        try:
            await client.forward_messages(chat_id, selected_saved_msg)
        except Exception as e:
            print(f"forward error: {e}")
        await asyncio.sleep(forward_delay)


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.اوامري$'))
async def help_cmd(event):
    text = (
        "**قائمة الأوامر:**\n\n"
        "`.اوامري` - عرض الأوامر\n"
        "`.اضف كلمات` - إضافة كلمات من ملف (رد على الملف)\n"
        "`.نيكه` - بدء الإرسال العشوائي\n"
        "`.خلاص` - إيقاف الإرسال\n"
        "`.وقت الارسال [ثواني]` - ضبط زمن التأخير\n"
        "`.سرعه [ثواني]` - ضبط سرعة الإرسال\n"
        "`.تتبع` - تفعيل الرد التلقائي\n"
        "`.كافي` - إيقاف الرد التلقائي\n"
        "`.حماية` - تشغيل/إيقاف حماية الفلود\n"
        "`.الحماية` - عرض إحصائيات الحماية\n"
        "`.كتم` - مسح الرسائل وكتم المستخدم\n"
        "`.فكه` - فك الكتم\n"
        "`.تحديد` - تحديد رسالة من المحفوظات (رد على رسالة فيها)\n"
        "`.on` - تشغيل التحويل من المحفوظات\n"
        "`.off` - إيقاف التحويل من المحفوظات\n"
        "`delay [ثواني]` - ضبط زمن delay للتحويل"
    )
    await event.edit(text)


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.اضف كلمات$'))
async def add_words(event):
    if not event.is_reply:
        await event.edit("❌ يجب الرد على ملف الكلمات")
        return

    replied = await event.get_reply_message()
    if not replied.file:
        await event.edit("❌ هذا ليس ملفًا")
        return

    await event.edit("⏳ جاري التحميل...")
    path = await replied.download_media()
    if not path:
        await event.edit("❌ فشل تحميل الملف")
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        count = 0
        for line in lines:
            line = line.strip()
            if line:
                word_list.append(line)
                count += 1

        await event.edit(f"✅ تم إضافة {count} كلمة\n📊 الإجمالي: {len(word_list)}")
    except Exception as e:
        await event.edit(f"❌ خطأ: {e}")
    finally:
        try:
            os.remove(path)
        except:
            pass


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.نيكه$'))
async def start_spam(event):
    global spam_running, spam_task, spam_typing_task
    if not word_list:
        await event.edit("❌ لا توجد كلمات! أضف كلمات أولاً")
        return

    if spam_running:
        await event.edit("⚠️ الإرسال يعمل بالفعل")
        return

    reply_to = None
    if event.is_reply:
        replied = await event.get_reply_message()
        reply_to = replied.id
        print(f"spam targeting msg {reply_to}")

    spam_running = True
    spam_task = asyncio.ensure_future(spam_loop(event.chat_id, reply_to))
    spam_typing_task = asyncio.ensure_future(keep_typing(event.chat_id))
    state = "🛡️" if flood_guard_enabled else "🚫"
    msg = f"▶️ بدء الإرسال... ⏱ {spam_delay} ث {state}"
    if reply_to:
        msg += "\n🎯 مستهدف: على الرسالة المُشار إليها"
    await event.edit(msg)


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.خلاص$'))
async def stop_spam(event):
    global spam_running, spam_typing_task
    if not spam_running:
        await event.edit("⚠️ الإرسال متوقف بالفعل")
        return
    spam_running = False
    if spam_typing_task:
        spam_typing_task.cancel()
        spam_typing_task = None
    await event.edit("⏹️ تم إيقاف الإرسال")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.(?:وقت الارسال|سرعه) (.+)$'))
async def set_spam_time(event):
    global spam_delay
    try:
        delay = float(event.pattern_match.group(1))
        if delay < 0:
            await event.edit("❌ الوقت يجب أن يكون أكبر من 0")
            return
        spam_delay = delay
        await event.edit(f"✅ تم ضبط وقت الإرسال إلى {delay} ث")
    except ValueError:
        await event.edit("❌ قيمة غير صالحة")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.تتبع$'))
async def start_follow(event):
    global follow_running
    if not word_list:
        await event.edit("❌ لا توجد كلمات! أضف كلمات أولاً")
        return
    follow_running = True
    state = "🛡️" if flood_guard_enabled else "🚫"
    await event.edit(f"✅ تم تفعيل التتبع {state}")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.كافي$'))
async def stop_follow(event):
    global follow_running
    follow_running = False
    await event.edit("✅ تم إيقاف التتبع")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.حماية$'))
async def toggle_flood_guard(event):
    global flood_guard_enabled
    flood_guard_enabled = not flood_guard_enabled
    state = "🛡️ مفعلة" if flood_guard_enabled else "🚫 معطلة"
    await event.edit(f"حماية الفلود: {state}")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.الحماية$'))
async def show_flood_stats(event):
    if not flood_guard:
        await event.edit("❌ الحماية غير مهيأة")
        return
    s = flood_guard.get_stats()
    text = (
        f"**🛡️ حماية الفلود**\n\n"
        f"الحساب: {s['type']}\n"
        f"Tokens: {s['tokens']}\n"
        f"Refill: {s['refill']}\n"
        f"المعدل: {s['rate']}\n"
        f"المرسل: {s['total']}/{s['daily_max']}"
    )
    await event.edit(text)


@client.on(events.NewMessage(incoming=True))
async def auto_follow(event):
    if follow_running and event.is_private and word_list:
        word = random.choice(word_list)
        try:
            async with client.action(event.chat_id, 'typing'):
                await asyncio.sleep(0.3)
            if flood_guard_enabled:
                await flood_guard.wait_if_needed()
            await event.reply(word)
        except:
            pass


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.كتم$'))
async def mute_user(event):
    if not event.is_reply:
        await event.edit("❌ يجب الرد على المستخدم")
        return

    replied = await event.get_reply_message()
    user_id = replied.sender_id
    await event.edit("⏳ جاري الحذف والكتم...")

    try:
        async for msg in client.iter_messages(event.chat_id, from_user=user_id, limit=100):
            await msg.delete()
    except:
        pass

    try:
        await client(BlockRequest(id=user_id))
        await event.edit("✅ تم مسح الرسائل وكتم المستخدم")
    except Exception as e:
        await event.edit(f"❌ فشل كتم: {e}")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.فكه$'))
async def unmute_user(event):
    if not event.is_reply:
        await event.edit("❌ يجب الرد على المستخدم")
        return

    replied = await event.get_reply_message()
    user_id = replied.sender_id

    try:
        await client(UnblockRequest(id=user_id))
        await event.edit("✅ تم فك الكتم")
    except Exception as e:
        await event.edit(f"❌ فشل فك الكتم: {e}")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.تحديد$'))
async def select_saved(event):
    global selected_saved_msg
    if not event.is_reply:
        await event.edit("❌ رد على الرسالة في المحفوظات")
        return
    if str(event.chat_id) != str((await client.get_me()).id):
        await event.edit("❌ استخدم هذا الأمر في المحفوظات فقط")
        return
    replied = await event.get_reply_message()
    selected_saved_msg = replied
    await event.edit(f"✅ تم تحديد الرسالة\n📝 {replied.text[:50] or '[وسائط]'}...")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.on$'))
async def start_forward(event):
    global forward_running, forward_task
    if not selected_saved_msg:
        await event.edit("❌ لم يتم تحديد رسالة! استخدم .تحديد أولاً")
        return

    if forward_running:
        await event.edit("⚠️ التحويل يعمل بالفعل")
        return

    forward_running = True
    forward_task = asyncio.ensure_future(forward_loop(event.chat_id))
    await event.edit(f"▶️ تشغيل التحويل من المحفوظات... delay: {forward_delay} ث")


@client.on(events.NewMessage(outgoing=True, pattern=r'^\.off$'))
async def stop_forward(event):
    global forward_running
    if not forward_running:
        await event.edit("⚠️ التحويل متوقف بالفعل")
        return
    forward_running = False
    await event.edit("⏹️ تم إيقاف التحويل")


@client.on(events.NewMessage(outgoing=True, pattern=r'^delay (.+)$'))
async def set_forward_delay(event):
    global forward_delay
    try:
        delay = float(event.pattern_match.group(1))
        if delay <= 0:
            await event.edit("❌ الوقت يجب أن يكون أكبر من 0")
            return
        forward_delay = delay
        await event.edit(f"✅ تم ضبط delay إلى {delay} ث")
    except ValueError:
        await event.edit("❌ قيمة غير صالحة")


async def main():
    await client.start()
    me = await client.get_me()
    global flood_guard
    is_premium = getattr(me, 'premium', False)
    flood_guard = TextFloodGuard(is_premium=is_premium)
    s = flood_guard.get_stats()
    status = "بريميوم" if is_premium else "عادي"
    guard = "🛡️ مفعلة" if flood_guard_enabled else "🚫 معطلة"
    print(f"✓ Userbot spam.py شغال | حساب {status}")
    print(f"✓ {s['tokens']} tokens | refill {s['refill']} | rate {s['rate']}")
    print(f"✓ عدد الكلمات المحملة: {len(word_list)}")
    print(f"✓ حماية الفلود: {guard}")
    await client.run_until_disconnected()


if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())


