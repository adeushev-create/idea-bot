import re
import json
import logging
import httpx
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1"


class AIProcessor:
    def __init__(self, groq_api_key: str, gemini_api_key: str = None):
        self.groq_api_key = groq_api_key
        self.headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }

    async def transcribe_voice(self, file_path: str) -> Optional[str]:
        """Расшифровка голосового через Groq Whisper"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        f"{GROQ_API_URL}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.groq_api_key}"},
                        files={"file": ("voice.ogg", f, "audio/ogg")},
                        data={"model": "whisper-large-v3", "language": "ru"}
                    )
                if response.status_code == 200:
                    return response.json().get("text", "").strip()
                else:
                    logger.error(f"Groq Whisper error: {response.status_code} {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None

    async def analyze_idea(self, text: str) -> Dict:
        """Анализирует текст: определяет тему, извлекает URL, оценивает ресурсы"""
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)
        url = urls[0] if urls else None

        prompt = f"""Проанализируй эту идею/заметку и верни ТОЛЬКО JSON без пояснений и без markdown:

Текст: "{text}"

{{
  "topic": "одна из тем: Работа, Обучение, Проект, Идея, Здоровье, Личное, Финансы, Разное",
  "clean_text": "краткая суть в 1-2 предложениях на русском",
  "estimated_hours": null,
  "xp_reward": 10,
  "url": null
}}

Правила:
- topic: выбери самую подходящую тему
- clean_text: перефразируй кратко и чётко
- estimated_hours: null или число (если задача/обучение — сколько часов займёт)
- xp_reward: 5-10 простое, 15-25 среднее, 30-50 сложное
- url: вставь ссылку если есть в тексте, иначе null"""

        try:
            result = await self._groq_chat(prompt)
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if url and not data.get("url"):
                    data["url"] = url
                return data
        except Exception as e:
            logger.error(f"Analysis error: {e}")

        return {
            "topic": "Разное",
            "clean_text": text[:300],
            "estimated_hours": None,
            "xp_reward": 10,
            "url": url
        }

    async def generate_weekly_summary(self, ideas: List[Dict]) -> str:
        """Генерирует еженедельную сводку с чеклистом"""
        if not ideas:
            return "📭 За эту неделю нет идей."

        by_topic = {}
        for idea in ideas:
            topic = idea.get("topic", "Разное")
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(idea)

        total = len(ideas)
        done = sum(1 for i in ideas if i.get("done"))
        total_hours = sum(i.get("estimated_hours") or 0 for i in ideas if not i.get("done"))

        ideas_text = json.dumps(by_topic, ensure_ascii=False, default=str)

        prompt = f"""Создай еженедельную сводку для личного ассистента. Идеи и задачи за неделю.

Данные по темам (JSON):
{ideas_text}

Статистика: всего {total} идей, выполнено {done}, осталось {total - done}, примерно {total_hours:.1f}ч работы.

Создай сводку строго в этом формате:

🗓 СВОДКА НЕДЕЛИ

[1-2 предложения — что было сделано за неделю, мотивирующе]

По каждой теме:
[эмодзи] ТЕМА (N задач, ~Xч)
├ ⬜ Задача 1 — описание (~Xч, +XX XP)
├ ⬜ Задача 2 — описание
└ ✅ Выполненная задача

⏱ ПЛАН НА ВЫХОДНЫЕ
Конкретные действия по приоритету с номерами

📊 ПРОГРЕСС НЕДЕЛИ
[████░░░░░░] X% выполнено
Суммарный XP за всё: +XXX XP

Пиши по-русски, коротко, мотивирующе. Без лишних слов."""

        try:
            return await self._groq_chat(prompt, max_tokens=1500)
        except Exception as e:
            logger.error(f"Summary error: {e}")
            return self._fallback_summary(by_topic, total, done)

    def _fallback_summary(self, by_topic: Dict, total: int, done: int) -> str:
        text = "🗓 *СВОДКА НЕДЕЛИ*\n\n"
        text += f"📊 Всего: {total} идей, выполнено: {done}\n\n"
        for topic, ideas in by_topic.items():
            text += f"📌 *{topic}* ({len(ideas)})\n"
            for idea in ideas[:5]:
                status = "✅" if idea.get("done") else "⬜"
                text += f"{status} {idea['content'][:80]}\n"
            text += "\n"
        return text


    async def is_idea(self, text: str) -> dict:
        """Проверяет является ли текст идеей/заметкой или просто сообщением"""
        prompt = f"""Определи является ли этот текст идеей, заметкой, задачей или чем-то что стоит сохранить.

Текст: "{text}"

Верни ТОЛЬКО JSON без пояснений:
{{
  "is_idea": true или false,
  "confidence": число от 0 до 100,
  "reason": "одна фраза почему",
  "reply": "короткий дружелюбный ответ если это НЕ идея (1 предложение)"
}}

НЕ идеи (is_idea: false, confidence > 80):
- приветствия: "привет", "йоу", "хей", "ку"
- вопросы к боту: "ты тут?", "как дела?", "что умеешь?"
- короткие реакции: "ок", "понял", "круто", "спасибо"
- бессмысленный текст или случайные символы
- светская болтовня без конкретной мысли

ИДЕИ (is_idea: true):
- любые планы, задачи, цели
- "хочу X", "нужно сделать Y", "идея про Z"
- ссылки на статьи, видео, сайты
- заметки, мысли, наблюдения
- книги, курсы, что-то изучить"""
        
        try:
            result = await self._groq_chat(prompt, max_tokens=100)
            import re, json
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"is_idea error: {e}")
        
        # По умолчанию считаем идеей если длина > 15 символов
        return {"is_idea": len(text) > 15, "confidence": 50, "reason": "неизвестно"}

    async def _groq_chat(self, prompt: str, max_tokens: int = 800) -> str:
        """Запрос к Groq LLM (Llama)"""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{GROQ_API_URL}/chat/completions",
                headers=self.headers,
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens
                }
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise Exception(f"Groq LLM error: {response.status_code} {response.text}")
