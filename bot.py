import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message

from database import Database
from ai_processor import AIProcessor
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()
ai = AIProcessor(groq_api_key=GROQ_API_KEY)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.save_user(message.from_user.id)
    await message.answer(
        "👋 Привет! Я твой личный ассистент для идей.\n\n"
        "Просто:\n"
        "🎤 Надиктуй голосовое — расшифрую и сохраню\n"
        "✍️ Напиши текст — сохраню как идею\n"
        "🔗 Скинь ссылку — сохраню с темой\n\n"
        "Каждую пятницу в 18:00 пришлю сводку недели 📊\n\n"
        "Команды:\n"
        "/list — все идеи за неделю\n"
        "/summary — сводка прямо сейчас\n"
        "/done [номер] — отметить задачу выполненной\n"
        "/stats — твоя статистика и XP"
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
        topic_emoji = get_topic_emoji(idea["topic"])
        text += f"{status} {i}. {topic_emoji} *{idea['topic']}*\n"
        text += f"   {idea['content'][:100]}{'...' if len(idea['content']) > 100 else ''}\n"
        if idea.get("url"):
            text += f"   🔗 {idea['url']}\n"
        text += "\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("summary"))
async def cmd_summary(message: Message):
    await message.answer("⏳ Генерирую сводку, подожди немного...")
    ideas = db.get_week_ideas(message.from_user.id)
    if not ideas:
        await message.answer("📭 За эту неделю нет идей для сводки.")
        return
    summary = await ai.generate_weekly_summary(ideas)
    await message.answer(summary, parse_mode="Markdown")


@dp.message(Command("done"))
async def cmd_done(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Используй: /done [номер идеи]\nНапример: /done 3")
        return

    idx = int(args[1]) - 1
    ideas = db.get_week_ideas(message.from_user.id)
    if idx < 0 or idx >= len(ideas):
        await message.answer("❌ Такого номера нет. Проверь /list")
        return

    idea = ideas[idx]
    xp_gained = db.mark_done(idea["id"], message.from_user.id)
    total_xp = db.get_user_xp(message.from_user.id)

    await message.answer(
        f"✅ Отлично! Задача выполнена!\n"
        f"⚡ +{xp_gained} XP\n"
        f"🏆 Всего XP: {total_xp}"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = db.get_user_stats(message.from_user.id)
    level = stats["xp"] // 100 + 1
    xp_in_level = stats["xp"] % 100
    progress_bar = "█" * (xp_in_level // 10) + "░" * (10 - xp_in_level // 10)

    await message.answer(
        f"🏆 *Твоя статистика*\n\n"
        f"⚡ XP: {stats['xp']}\n"
        f"🎯 Уровень: {level}\n"
        f"[{progress_bar}] {xp_in_level}/100\n\n"
        f"📊 За всё время:\n"
        f"💡 Идей записано: {stats['total_ideas']}\n"
        f"✅ Задач выполнено: {stats['done_count']}\n"
        f"🔗 Ссылок сохранено: {stats['links_count']}",
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
        logger.error(f"Voice processing error: {e}")
        await message.answer("❌ Ошибка при обработке голосового. Попробуй текстом.")


@dp.message(F.text)
async def handle_text(message: Message):
    if message.text.startswith("/"):
        return
    await process_and_save(message, message.text)


async def process_and_save(message: Message, text: str):
    processing_msg = await message.answer("🧠 Анализирую и сохраняю...")
    try:
        analysis = await ai.analyze_idea(text)
        topic = analysis.get("topic", "Разное")
        clean_text = analysis.get("clean_text", text)
        url = analysis.get("url", None)
        estimated_hours = analysis.get("estimated_hours", None)
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

        topic_emoji = get_topic_emoji(topic)
        response = f"✅ Сохранено!\n\n{topic_emoji} *{topic}*\n{clean_text[:200]}"
        if url:
            response += f"\n🔗 Ссылка сохранена"
        if estimated_hours:
            response += f"\n⏱ Примерно {estimated_hours}ч"
            response += f"\n⚡ За выполнение: +{xp_reward} XP"

        await processing_msg.edit_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Processing error: {e}")
        await processing_msg.edit_text("❌ Ошибка при обработке. Попробуй ещё раз.")


def get_topic_emoji(topic: str) -> str:
    emojis = {
        "Работа": "💼", "Обучение": "📚", "Проект": "🚀",
        "Идея": "💡", "Ссылка": "🔗", "Здоровье": "💪",
        "Личное": "🌱", "Финансы": "💰", "Разное": "📌",
    }
    for key in emojis:
        if key.lower() in topic.lower():
            return emojis[key]
    return "📌"


async def main():
    db.init()
    scheduler = setup_scheduler(bot, db, ai)
    scheduler.start()
    logger.info("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
