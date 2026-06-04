from aiohttp import web
from database import Database
import logging, os, tempfile, json
from datetime import datetime, date

logger = logging.getLogger(__name__)
db = Database()

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}

def safe_json(obj):
    """Конвертирует все несериализуемые типы в строки"""
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe_json(i) for i in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bool):
        return int(obj)
    return obj

async def get_ideas(request):
    try:
        user_id = request.rel_url.query.get('user_id')
        if not user_id:
            return web.json_response({'error': 'no user_id'}, status=400, headers=CORS)
        ideas = db.get_week_ideas(int(user_id))
        stats = db.get_user_stats(int(user_id))
        return web.Response(
            text=json.dumps({'ideas': safe_json(ideas), 'stats': safe_json(stats)}, ensure_ascii=False),
            content_type='application/json',
            headers=CORS
        )
    except Exception as e:
        logger.error(f"get_ideas error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def add_idea(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        content = data.get('content', '')
        topic = data.get('topic', 'Разное')
        url = data.get('url')
        if not user_id or not content:
            return web.json_response({'error': 'missing fields'}, status=400, headers=CORS)
        idea_id = db.save_idea(
            user_id=int(user_id), content=content, raw_text=content,
            topic=topic, url=url,
            estimated_hours=data.get('estimated_hours'),
            xp_reward=data.get('xp_reward', 10)
        )
        return web.json_response({'ok': True, 'idea_id': idea_id}, headers=CORS)
    except Exception as e:
        logger.error(f"add_idea error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def mark_done(request):
    try:
        data = await request.json()
        idea_id = data.get('idea_id')
        user_id = data.get('user_id')
        if not idea_id or not user_id:
            return web.json_response({'error': 'missing'}, status=400, headers=CORS)
        xp = db.mark_done(int(idea_id), int(user_id))
        total_xp = db.get_user_xp(int(user_id))
        return web.json_response({'ok': True, 'xp_gained': xp, 'total_xp': total_xp}, headers=CORS)
    except Exception as e:
        logger.error(f"mark_done error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def voice_endpoint(request):
    from ai_processor import AIProcessor
    ai = AIProcessor(groq_api_key=os.getenv('GROQ_API_KEY'))
    try:
        data = await request.post()
        file_field = data.get('file')
        if not file_field:
            return web.json_response({'error': 'no file'}, status=400, headers=CORS)
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            tmp.write(file_field.file.read())
            tmp_path = tmp.name
        text = await ai.transcribe_voice(tmp_path)
        os.remove(tmp_path)
        return web.json_response({'text': text or ''}, headers=CORS)
    except Exception as e:
        logger.error(f"voice error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def get_leaderboard(request):
    try:
        board = db.get_leaderboard(20)
        user_ids = [r['user_id'] for r in board]
        names = db.get_usernames(user_ids)
        for i, row in enumerate(board):
            uid = row['user_id']
            row['name'] = names.get(uid, f'Игрок {str(uid)[-4:]}')
            row['rank'] = i + 1
        return web.Response(
            text=json.dumps({'leaderboard': safe_json(board)}, ensure_ascii=False),
            content_type='application/json',
            headers=CORS
        )
    except Exception as e:
        logger.error(f"leaderboard error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)


async def update_idea(request):
    try:
        data = await request.json()
        idea_id = data.get('idea_id')
        user_id = data.get('user_id')
        if not idea_id or not user_id:
            return web.json_response({'error': 'missing'}, status=400, headers=CORS)
        ok = db.update_idea(
            idea_id=int(idea_id), user_id=int(user_id),
            content=data.get('content'),
            topic=data.get('topic'),
            url=data.get('url'),
            estimated_hours=data.get('estimated_hours')
        )
        return web.json_response({'ok': ok}, headers=CORS)
    except Exception as e:
        logger.error(f"update_idea error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def delete_idea(request):
    try:
        data = await request.json()
        idea_id = data.get('idea_id')
        user_id = data.get('user_id')
        if not idea_id or not user_id:
            return web.json_response({'error': 'missing'}, status=400, headers=CORS)
        ok = db.delete_idea(int(idea_id), int(user_id))
        return web.json_response({'ok': ok}, headers=CORS)
    except Exception as e:
        logger.error(f"delete_idea error: {e}")
        return web.json_response({'error': str(e)}, status=500, headers=CORS)

async def options_handler(request):
    return web.Response(headers=CORS)

async def health(request):
    return web.json_response({'status': 'ok'})

def create_app():
    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_get('/api/ideas', get_ideas)
    app.router.add_post('/api/ideas', add_idea)
    app.router.add_post('/api/done', mark_done)
    app.router.add_post('/api/voice', voice_endpoint)
    app.router.add_get('/api/leaderboard', get_leaderboard)
    app.router.add_post('/api/ideas/update', update_idea)
    app.router.add_post('/api/ideas/delete', delete_idea)
    app.router.add_route('OPTIONS', '/api/ideas', options_handler)
    app.router.add_route('OPTIONS', '/api/ideas/update', options_handler)
    app.router.add_route('OPTIONS', '/api/ideas/delete', options_handler)
    app.router.add_route('OPTIONS', '/api/done', options_handler)
    app.router.add_route('OPTIONS', '/api/voice', options_handler)
    return app
