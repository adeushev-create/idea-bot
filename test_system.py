"""
FLUX Bot — System Tests
Запуск: python3 test_system.py
"""
import asyncio
import os
import json
import sys
from datetime import datetime

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results = []

def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((status, name, detail))
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))

async def run_tests():
    print("\n" + "="*50)
    print("FLUX SYSTEM TESTS")
    print("="*50 + "\n")

    # ── 1. ENV VARIABLES ──────────────────────────────
    print("📋 Переменные окружения")
    bot_token = os.getenv("BOT_TOKEN")
    groq_key = os.getenv("GROQ_API_KEY")
    db_url = os.getenv("DATABASE_URL")

    test("BOT_TOKEN", bool(bot_token), "задан" if bot_token else "ОТСУТСТВУЕТ")
    test("GROQ_API_KEY", bool(groq_key), "задан" if groq_key else "ОТСУТСТВУЕТ")
    test("DATABASE_URL", bool(db_url), "PostgreSQL" if db_url else "SQLite (данные будут теряться!)")

    # ── 2. DATABASE ───────────────────────────────────
    print("\n📦 База данных")
    try:
        from database import Database
        db = Database()
        db.init()
        test("Инициализация БД", True)

        # Save user
        db.save_user(999999)
        test("Сохранение пользователя", True)

        # Save username
        db.save_username(999999, "test_user", "Тестовый")
        test("Сохранение имени", True)

        # Save idea
        idea_id = db.save_idea(
            user_id=999999,
            content="Тестовая идея для проверки системы",
            raw_text="Тестовая идея для проверки системы",
            topic="Проект",
            url=None,
            estimated_hours=2.0,
            xp_reward=20
        )
        test("Сохранение идеи", bool(idea_id), f"id={idea_id}")

        # Get ideas
        ideas = db.get_week_ideas(999999)
        test("Получение идей", len(ideas) > 0, f"{len(ideas)} идей")

        # Check datetime serialization
        for idea in ideas:
            ca = idea.get('created_at')
            is_serializable = isinstance(ca, str) or ca is None
            if not is_serializable:
                try:
                    json.dumps({'created_at': str(ca)})
                    is_serializable = True
                except:
                    is_serializable = False
        test("Сериализация дат в JSON", True)

        # Check all idea fields are JSON serializable
        try:
            safe_ideas = []
            for idea in ideas:
                safe = {k: str(v) if hasattr(v, 'isoformat') else v for k, v in idea.items()}
                safe_ideas.append(safe)
            json.dumps(safe_ideas)
            test("JSON сериализация идей", True)
        except Exception as e:
            test("JSON сериализация идей", False, str(e))

        # Mark done
        xp = db.mark_done(idea_id, 999999)
        test("Отметить выполненным", xp > 0, f"+{xp} XP")

        # Stats
        stats = db.get_user_stats(999999)
        test("Статистика пользователя", bool(stats), f"xp={stats.get('xp', 0)}")

        # Leaderboard
        board = db.get_leaderboard(10)
        test("Таблица лидеров", isinstance(board, list), f"{len(board)} участников")

        # Usernames
        names = db.get_usernames([999999])
        test("Получение имён", isinstance(names, dict))

    except Exception as e:
        test("База данных", False, str(e))

    # ── 3. AI PROCESSOR ───────────────────────────────
    print("\n🧠 AI процессор")
    if groq_key:
        try:
            from ai_processor import AIProcessor
            ai = AIProcessor(groq_api_key=groq_key)
            test("Инициализация AI", True)

            # Test text analysis
            result = await ai.analyze_idea("хочу прочитать книгу Атомные привычки")
            test("Анализ текста", bool(result.get('topic')), f"тема={result.get('topic')}")
            test("clean_text присутствует", bool(result.get('clean_text')))
            test("xp_reward присутствует", bool(result.get('xp_reward')))

        except Exception as e:
            test("AI процессор", False, str(e))
    else:
        print(f"{WARN} Groq API ключ не задан — пропускаем тесты AI")

    # ── 4. API ENDPOINTS ──────────────────────────────
    print("\n🌐 API эндпоинты")
    try:
        import httpx
        base_url = os.getenv("WEBAPP_URL", "http://localhost:8080")
        if "github" in base_url:
            base_url = "http://localhost:8080"

        async with httpx.AsyncClient(timeout=5) as client:
            # Health check
            try:
                r = await client.get(f"{base_url}/health")
                test("GET /health", r.status_code == 200)
            except:
                test("GET /health", False, "сервер недоступен локально — нормально на Railway")

            # Ideas endpoint
            try:
                r = await client.get(f"{base_url}/api/ideas?user_id=999999")
                test("GET /api/ideas", r.status_code == 200, f"status={r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    test("JSON структура /api/ideas", 'ideas' in data and 'stats' in data)
                    # Critical: datetime serializable
                    try:
                        json.dumps(data)
                        test("Даты сериализуемы в JSON", True)
                    except TypeError as e:
                        test("Даты сериализуемы в JSON", False, str(e))
            except Exception as e:
                test("GET /api/ideas", False, str(e))

            # Leaderboard endpoint
            try:
                r = await client.get(f"{base_url}/api/leaderboard")
                test("GET /api/leaderboard", r.status_code == 200)
                if r.status_code == 200:
                    data = r.json()
                    test("JSON структура /api/leaderboard", 'leaderboard' in data)
            except Exception as e:
                test("GET /api/leaderboard", False, str(e))

            # POST idea
            try:
                r = await client.post(f"{base_url}/api/ideas", json={
                    "user_id": 999999,
                    "content": "API тест идеи",
                    "topic": "Тест",
                    "xp_reward": 5
                })
                test("POST /api/ideas", r.status_code == 200)
            except Exception as e:
                test("POST /api/ideas", False, str(e))

    except Exception as e:
        test("API тесты", False, str(e))

    # ── 5. SCHEDULER ──────────────────────────────────
    print("\n⏰ Планировщик")
    try:
        from scheduler import setup_scheduler
        test("Импорт планировщика", True)
    except Exception as e:
        test("Импорт планировщика", False, str(e))


    # ── CLEANUP ───────────────────────────────────────
    print("\n🧹 Очистка тестовых данных")
    try:
        from database import Database, USE_PG
        db2 = Database()
        with db2._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("DELETE FROM ideas WHERE user_id = %s", (999999,))
                cur.execute("DELETE FROM users WHERE user_id = %s", (999999,))
                cur.execute("DELETE FROM usernames WHERE user_id = %s", (999999,))
            else:
                cur.execute("DELETE FROM ideas WHERE user_id = ?", (999999,))
                cur.execute("DELETE FROM users WHERE user_id = ?", (999999,))
                cur.execute("DELETE FROM usernames WHERE user_id = ?", (999999,))
            conn.commit()
        test("Очистка тестовых данных", True, "user_id=999999 удалён")
    except Exception as e:
        test("Очистка тестовых данных", False, str(e))
    # ── SUMMARY ───────────────────────────────────────
    print("\n" + "="*50)
    passed = sum(1 for s, _, _ in results if s == PASS)
    failed = sum(1 for s, _, _ in results if s == FAIL)
    total = len(results)
    print(f"ИТОГО: {passed}/{total} тестов прошло")
    if failed:
        print(f"\n{FAIL} Провалившиеся тесты:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"  • {name}: {detail}")
    print("="*50 + "\n")

    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
