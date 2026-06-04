import asyncio
import logging
import os
from aiohttp import web
from database import Database
from ai_processor import AIProcessor
from scheduler import setup_scheduler
from api import create_app
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://adeushev-create.github.io/flux-app")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()
ai = AIProcessor(groq_api_key=GROQ_API_KEY)

AVATARS = ["🦊","🐺","🦁","🐯","🦅","🐉","🦋","🦩","🐬","🦄","🐸","🦀"]

def get_avatar(user_id: int) -> str:
    return AVATARS[user_id % len(AVATARS)]

def get_topic_emoji(topic: str) -> str:
    emojis = {
        "Работа": "💼", "Обучение": "📚", "Проект": "🚀",
        "Идея": "💡", "Книга": "📖", "Видео": "🎬",
        "Ссылка": "🔗", "Здоровье": "💪",
        "Личное": "🌱", "Финансы": "💰", "Разное": "📌",
    }
    for key in emojis:
        if key.lower() in topic.lower():
            return emojis[key]
    return "📌"

@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.save_user(message.from_user.id)
    db.save_username(message.from_user.id, message.from_user.username or '', message.from_user.first_name or 'User')
    avatar = get_avatar(message.from_user.id)
    name = message.from_user.first_name or "друг"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="⚡ Открыть FLUX",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]])
    await message.answer(
        f"{avatar} Привет, {name}! Я твой FLUX — поток идей.\n\n"
        f"Просто:\n"
        f"🎤 Надиктуй голосовое — расшифрую и сохраню\n"
        f"✍️ Напиши текст — сохраню как идею\n"
        f"🔗 Скинь ссылку — определю тему\n\n"
        f"Каждую пятницу в 18:00 пришлю сводку 📊\n\n"
        f"/list — идеи за неделю\n"
        f"/summary — сводка прямо сейчас\n"
        f"/done [номер] — отметить выполненным\n"
        f"/stats — твой прогресс и XP",
        reply_markup=keyboard
    )

@dp.message(Command("list"))
async def cmd_list(message: Message):
    ideas = db.get_week_ideas(message.from_user.id)
    if not ideas:
        await message.answer("📭 За эту неделю пока нет идей. Надиктуй первую!")
        return
    text = "📋 *Твои идеи за неделю:*\n\n"
    for i, idea in enumerate(ideas, 1):
        status = "✅" if idea["done"] else "⬜"
        emoji = get_topic_emoji(idea["topic"])
        text += f"{status} {i}. {emoji} *{idea['topic']}*\n"
        text += f"   {idea['content'][:100]}{'...' if len(idea['content']) > 100 else ''}\n"
        if idea.get("url"):
            text += f"   🔗 {idea['url']}\n"
        text += "\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("summary"))
async def cmd_summary(message: Message):
    await message.answer("⏳ Генерирую сводку...")
    ideas = db.get_week_ideas(message.from_user.id)
    if not ideas:
        await message.answer("📭 За эту неделю нет идей.")
        return
    summary = await ai.generate_weekly_summary(ideas)
    await message.answer(summary, parse_mode="Markdown")

@dp.message(Command("done"))
async def cmd_done(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Используй: /done [номер]\nНапример: /done 3")
        return
    idx = int(args[1]) - 1
    ideas = db.get_week_ideas(message.from_user.id)
    if idx < 0 or idx >= len(ideas):
        await message.answer("❌ Такого номера нет. Проверь /list")
        return
    idea = ideas[idx]
    xp_gained = db.mark_done(idea["id"], message.from_user.id)
    total_xp = db.get_user_xp(message.from_user.id)
    avatar = get_avatar(message.from_user.id)
    await message.answer(
        f"✅ Выполнено!\n"
        f"⚡ +{xp_gained} XP\n"
        f"{avatar} Всего XP: {total_xp}"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = db.get_user_stats(message.from_user.id)
    level = stats["xp"] // 100 + 1
    xp_in_level = stats["xp"] % 100
    bar = "█" * (xp_in_level // 10) + "░" * (10 - xp_in_level // 10)
    avatar = get_avatar(message.from_user.id)
    levels = ["Новичок","Искатель","Строитель","Архитектор","Мастер","Легенда"]
    level_name = levels[min(level-1, len(levels)-1)]
    await message.answer(
        f"{avatar} *Твой профиль FLUX*\n\n"
        f"🎯 {level_name} (ур. {level})\n"
        f"[{bar}] {xp_in_level}/100 XP\n\n"
        f"📊 Статистика:\n"
        f"💡 Идей записано: {stats['total_ideas']}\n"
        f"✅ Выполнено: {stats['done_count']}\n"
        f"🔗 Ссылок: {stats['links_count']}\n"
        f"⚡ Всего XP: {stats['xp']}",
        parse_mode="Markdown"
    )

@dp.message(F.voice)
async def handle_voice(message: Message):
    await message.answer("🎤 Расшифровываю...")
    try:
        file = await bot.get_file(message.voice.file_id)
        file_path = f"/tmp/voice_{message.voice.file_id}.ogg"
        await bot.download_file(file.file_path, file_path)
        transcribed_text = await ai.transcribe_voice(file_path)
        if not transcribed_text:
            await message.answer("❌ Не удалось расшифровать. Попробуй ещё раз.")
            return
        await process_and_save(message, transcribed_text)
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await message.answer("❌ Ошибка. Попробуй текстом.")

@dp.message(F.text)
async def handle_text(message: Message):
    if message.text.startswith("/"):
        return
    db.save_username(message.from_user.id, message.from_user.username or '', message.from_user.first_name or 'User')
    await process_and_save(message, message.text)

async def process_and_save(message: Message, text: str):
    processing_msg = await message.answer("🧠 Анализирую...")
    try:
        analysis = await ai.analyze_idea(text)
        topic = analysis.get("topic", "Разное")
        clean_text = analysis.get("clean_text", text)
        url = analysis.get("url")
        estimated_hours = analysis.get("estimated_hours")
        xp_reward = analysis.get("xp_reward", 10)
        db.save_idea(
            user_id=message.from_user.id,
            content=clean_text,
            raw_text=text,
            topic=topic,
            url=url,
            estimated_hours=estimated_hours,
            xp_reward=xp_reward
        )
        emoji = get_topic_emoji(topic)
        response = f"✅ Сохранено!\n\n{emoji} *{topic}*\n{clean_text[:200]}"
        if url:
            response += f"\n🔗 Ссылка сохранена"
        if estimated_hours:
            response += f"\n⏱ ~{estimated_hours}ч · +{xp_reward} XP"
        await processing_msg.edit_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Processing error: {e}")
        await processing_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")

async def run_api():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"API running on port {port}")

async def main():
    db.init()
    scheduler = setup_scheduler(bot, db, ai)
    scheduler.start()
    await run_api()
    logger.info("FLUX Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
