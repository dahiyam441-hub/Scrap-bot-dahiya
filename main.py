import asyncio,logging,os
from aiohttp import web
from dotenv import load_dotenv
from telegram.ext import Application,CommandHandler,CallbackQueryHandler,ChatJoinRequestHandler
from app.db import init_db,get_setting
from app.handlers import start,dashboard,button,add_route_cmd,routes_cmd,route_on,route_off,route_delete,branding,sync_cmd,brandlist,branddel,pausesync,jobs_cmd,admin_add,admin_del,admins_cmd,bulkbrand
from app.telethon_worker import TelethonWorker

load_dotenv()
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'),format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
log=logging.getLogger('dahiya-auto-forwarder')

async def health(request): return web.json_response({'status':'ok','service':'dahiya-auto-forwarder'})
async def run_health_server():
    app=web.Application(); app.router.add_get('/',health); app.router.add_get('/health',health)
    runner=web.AppRunner(app); await runner.setup(); site=web.TCPSite(runner,'0.0.0.0',int(os.getenv('PORT','8080'))); await site.start(); return runner
async def auto_approve_join_request(update,context):
    req=update.chat_join_request
    if await get_setting('auto_approve','off')=='on':
        try: await context.bot.approve_chat_join_request(req.chat.id,req.from_user.id)
        except Exception: log.exception('Could not approve join request for chat %s',req.chat.id)
async def main():
    token=os.getenv('BOT_TOKEN','').strip()
    if not token: raise RuntimeError('BOT_TOKEN missing in environment variables.')
    await init_db(); app=Application.builder().token(token).build(); worker=TelethonWorker(app); app.bot_data['telethon_worker']=worker
    app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('admin',dashboard))
    app.add_handler(CommandHandler('addroute',add_route_cmd)); app.add_handler(CommandHandler('routes',routes_cmd))
    app.add_handler(CommandHandler('routeon',route_on)); app.add_handler(CommandHandler('routeoff',route_off)); app.add_handler(CommandHandler('delroute',route_delete))
    app.add_handler(CommandHandler('branding',branding)); app.add_handler(CommandHandler('sync',sync_cmd)); app.add_handler(CommandHandler('pausesync',pausesync)); app.add_handler(CommandHandler('jobs',jobs_cmd))
    app.add_handler(CommandHandler('brandlist',brandlist)); app.add_handler(CommandHandler('branddel',branddel)); app.add_handler(CommandHandler('addadmin',admin_add)); app.add_handler(CommandHandler('deladmin',admin_del)); app.add_handler(CommandHandler('admins',admins_cmd)); app.add_handler(CommandHandler('bulkbrand',bulkbrand))
    app.add_handler(CallbackQueryHandler(button)); app.add_handler(ChatJoinRequestHandler(auto_approve_join_request))
    runner=None
    try:
        await app.initialize(); await app.start(); await app.updater.start_polling(drop_pending_updates=False)
        runner=await run_health_server(); await worker.start()
        log.info('Dahiya Auto Forwarder running; health endpoint available.')
        await asyncio.Event().wait()
    finally:
        await worker.stop()
        if runner: await runner.cleanup()
        if app.updater and app.updater.running: await app.updater.stop()
        if app.running: await app.stop()
        await app.shutdown()
if __name__=='__main__': asyncio.run(main())
