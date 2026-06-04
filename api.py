from aiohttp import web
from database import Database
import logging, os, tempfile

logger = logging.getLogger(__name__)
db = Database()

CORS = {'Access-Control-Allow-Origin': '*'}

async def get_ideas(request):
    user_id = request.rel_url.query.get('user_id')
    if not user_id:
        return web.json_response({'error': 'no user_id'}, status=400)
    ideas = db.get_week_ideas(int(user_id))
    stats = db.get_user_stats(int(user_id))
    for idea in ideas:
        for k,v in idea.items():
            if isinstance(v, bool): idea[k] = int(v)
    return web.json_response({'ideas': ideas, 'stats': stats}, headers=CORS)

async def add_idea(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        content = data.get('content', '')
        if not user_id or not content:
            return web.json_response({'error': 'missing fields'}, status=400)
        idea_id = db.save_idea(
            user_id=int(user_id), content=content, raw_text=content,
            topic=data.get('topic', 'Разное'), url=data.get('url'),
            estimated_hours=data.get('estimated_hours'),
            xp_reward=data.get('xp_reward', 10)
        )
        return web.json_response({'ok': True, 'idea_id': idea_id}, headers=CORS)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def mark_done(request):
    try:
        data = await request.json()
        idea_id = data.get('idea_id')
        user_id = data.get('user_id')
        if not idea_id or not user_id:
            return web.json_response({'error': 'missing'}, status=400)
        xp = db.mark_done(int(idea_id), int(user_id))
        total_xp = db.get_user_xp(int(user_id))
        return web.json_response({'ok': True, 'xp_gained': xp, 'total_xp': total_xp}, headers=CORS)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def voice_endpoint(request):
    from ai_processor import AIProcessor
    ai = AIProcessor(groq_api_key=os.getenv('GROQ_API_KEY'))
    try:
        data = await request.post()
        file_field = data.get('file')
        if not file_field:
            return web.json_response({'error': 'no file'}, status=400)
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            tmp.write(file_field.file.read())
            tmp_path = tmp.name
        text = await ai.transcribe_voice(tmp_path)
        os.remove(tmp_path)
        return web.json_response({'text': text or ''}, headers=CORS)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def options_handler(request):
    return web.Response(headers={**CORS,
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'})

async def health(request):
    return web.json_response({'status': 'ok'})

def create_app():
    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_get('/api/ideas', get_ideas)
    app.router.add_post('/api/ideas', add_idea)
    app.router.add_post('/api/done', mark_done)
    app.router.add_post('/api/voice', voice_endpoint)
    app.router.add_route('OPTIONS', '/api/ideas', options_handler)
    app.router.add_route('OPTIONS', '/api/done', options_handler)
    app.router.add_route('OPTIONS', '/api/voice', options_handler)
    return app
