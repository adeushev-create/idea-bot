import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)

# Часовой пояс Павлодара (UTC+5)
TIMEZONE = pytz.timezone("Asia/Almaty")


def setup_scheduler(bot, db, ai):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Пятница в 18:00 по Павлодару
    scheduler.add_job(
        send_weekly_summary,
        CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=TIMEZONE),
        args=[bot, db, ai],
        id="weekly_summary"
    )

    # Понедельник в 9:00 — мотивационное напоминание
    scheduler.add_job(
        send_monday_reminder,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=TIMEZONE),
        args=[bot, db],
        id="monday_reminder"
    )

    logger.info("Scheduler configured: Friday 18:00, Monday 09:00 (Pavlodar time)")
    return scheduler


async def send_weekly_summary(bot, db, ai):
    """Отправляет еженедельную сводку всем пользователям"""
    users = db.get_all_active_users()
    logger.info(f"Sending weekly summary to {len(users)} users")

    for user_id in users:
        try:
            ideas = db.get_week_ideas(user_id)
            if not ideas:
                await bot.send_message(
                    user_id,
                    "🗓 Пятница! За эту неделю ты ничего не записал.\n"
                    "На выходных надиктуй свои идеи — я сохраню 💡"
                )
                continue

            await bot.send_message(user_id, "⏳ Готовлю твою сводку недели...")
            summary = await ai.generate_weekly_summary(ideas)
            await bot.send_message(user_id, summary, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error sending summary to {user_id}: {e}")


async def send_monday_reminder(bot, db):
    """Напоминание в понедельник"""
    users = db.get_all_active_users()

    for user_id in users:
        try:
            stats = db.get_user_stats(user_id)
            xp = stats.get("xp", 0)
            level = xp // 100 + 1

            await bot.send_message(
                user_id,
                f"☀️ Новая неделя начинается!\n\n"
                f"🎯 Твой уровень: {level} | ⚡ {xp} XP\n\n"
                f"Надиктуй голосовым или напиши свои планы и идеи на неделю — "
                f"в пятницу соберём всё в удобный чеклист 📋"
            )
        except Exception as e:
            logger.error(f"Error sending reminder to {user_id}: {e}")
