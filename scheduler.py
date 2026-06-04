import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import random

logger = logging.getLogger(__name__)
TIMEZONE = pytz.timezone("Asia/Almaty")

QUOTES = [
    ("Идея без действия — просто мечта.", "Эйнштейн"),
    ("Всё начинается с идеи.", "Эрл Найтингейл"),
    ("Воображение важнее знания.", "Эйнштейн"),
    ("Лучший способ предсказать будущее — создать его.", "Питер Друкер"),
    ("Не ждите. Время никогда не будет подходящим.", "Наполеон Хилл"),
    ("Идеи без действий — это просто галлюцинации.", "Томас Эдисон"),
    ("Единственный способ делать великую работу — любить то, что делаешь.", "Стив Джобс"),
    ("Успех — это переход от неудачи к неудаче без потери энтузиазма.", "Черчилль"),
    ("Начните там, где вы есть. Используйте то, что имеете. Делайте то, что можете.", "Артур Эш"),
    ("Тысячемильный путь начинается с первого шага.", "Лао-цзы"),
    ("Реализованная идея стоит больше тысячи придуманных.", "Неизвестный автор"),
    ("Мозг — это инструмент. Используй его или потеряешь.", "Неизвестный автор"),
]

MIDWEEK_TEMPLATES = [
    "💡 «{quote}» — {author}\n\nУ тебя {count} идей ждут своего часа. Может пора одну реализовать? 👇",
    "⚡ Мудрость дня: «{quote}» — {author}\n\n{count} идей в копилке — неплохо! Но реализованные считаются 😏 Открой FLUX.",
    "🧠 «{quote}» — {author}\n\nЭта неделя на исходе. Твои {count} идей всё ещё ждут. Успеешь? 🔥",
    "🚀 Сегодня среда — середина пути.\n\n«{quote}» — {author}\n\nТы записал {count} идей. Одно действие сегодня = прогресс к пятнице.",
    "🎯 Напоминание от FLUX:\n\n«{quote}» — {author}\n\n{count} идей в базе. Илон Маск записывает в 3 ночи. А ты? 😤",
]

ZERO_IDEAS_TEMPLATES = [
    "👀 Эй! Неделя почти прошла, а идей — ноль.\n\n«{quote}» — {author}\n\nНадиктуй хоть одну — это 10 секунд. Обещаю не осуждать 😄",
    "🦉 Дуолинго бы уже плакал...\n\nНи одной идеи за неделю! «{quote}» — {author}\n\nОткрой FLUX и исправь это 👇",
    "💭 Ты точно о чём-то думал на этой неделе?\n\n«{quote}» — {author}\n\nЗапиши одну мысль — и неделя уже не зря! 🔥",
]


def setup_scheduler(bot, db, ai):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Пятница 18:00 — еженедельная сводка
    scheduler.add_job(
        send_weekly_summary,
        CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=TIMEZONE),
        args=[bot, db, ai],
        id="weekly_summary"
    )

    # Среда 12:00 — мотивационный пуш с цитатой
    scheduler.add_job(
        send_midweek_push,
        CronTrigger(day_of_week="wed", hour=12, minute=0, timezone=TIMEZONE),
        args=[bot, db],
        id="midweek_push"
    )

    logger.info("Scheduler: Friday 18:00 + Wednesday 12:00 (Pavlodar)")
    return scheduler


async def send_weekly_summary(bot, db, ai):
    users = db.get_all_active_users()
    logger.info(f"Sending weekly summary to {len(users)} users")
    quote, author = random.choice(QUOTES)

    for user_id in users:
        try:
            ideas = db.get_week_ideas(user_id)
            if not ideas:
                await bot.send_message(
                    user_id,
                    f"🗓 Пятница!\n\nЗа эту неделю ты ничего не записал.\n\n"
                    f"«{quote}» — {author}\n\n"
                    f"На выходных — отличное время начать 💡"
                )
                continue

            await bot.send_message(user_id, "⏳ Готовлю сводку недели...")
            summary = await ai.generate_weekly_summary(ideas)
            await bot.send_message(
                user_id,
                f"{summary}\n\n─────────────\n💬 «{quote}» — {author}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending summary to {user_id}: {e}")


async def send_midweek_push(bot, db):
    users = db.get_all_active_users()
    logger.info(f"Sending midweek push to {len(users)} users")

    for user_id in users:
        try:
            ideas = db.get_week_ideas(user_id)
            count = len(ideas)
            quote, author = random.choice(QUOTES)

            if count == 0:
                template = random.choice(ZERO_IDEAS_TEMPLATES)
            else:
                template = random.choice(MIDWEEK_TEMPLATES)

            msg = template.format(quote=quote, author=author, count=count)
            await bot.send_message(user_id, msg)

        except Exception as e:
            logger.error(f"Error sending midweek push to {user_id}: {e}")
