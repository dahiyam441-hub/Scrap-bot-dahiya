import os
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import ContextTypes
from app import db

def owner_ids(): return {x.strip() for x in os.getenv('OWNER_IDS','').split(',') if x.strip()}
async def is_admin(uid): return str(uid) in owner_ids() or any(a['user_id']==str(uid) for a in await db.list_admins())
async def admin_only(update):
    if not await is_admin(update.effective_user.id): await update.effective_message.reply_text('⛔ Admin access only.'); return False
    return True
async def start(update,context): await update.effective_message.reply_text('🚀 Dahiya Auto Forwarder is online. Admins: /admin\nUse only chats you own or are authorized to manage.')
async def dashboard(update,context):
    if not await admin_only(update): return
    routes=await db.get_routes(); stats=await db.delivery_stats(); jobs=await db.list_sync_jobs(); approval=await db.get_setting('auto_approve','off')
    kb=[[InlineKeyboardButton('📡 Routes',callback_data='routes'),InlineKeyboardButton('🤝 Approval '+approval.upper(),callback_data='toggle_approval')],[InlineKeyboardButton('📊 Stats',callback_data='stats'),InlineKeyboardButton('🔄 Sync jobs',callback_data='jobs')],[InlineKeyboardButton('🏷 Branding rules',callback_data='brands')]]
    await update.effective_message.reply_text(f'⚙️ Dahiya Auto Forwarder\nRoutes: {len(routes)} | Sync jobs: {len(jobs)}\nDeliveries: {stats}\n\n/addroute SOURCE DEST\n/routeon ID | /routeoff ID | /delroute ID\n/sync SOURCE DEST [LIMIT]\n/pausesync JOB_ID\n/branding OLD | NEW\n/brandlist | /branddel ID\n/addadmin USER_ID | /deladmin USER_ID | /admins\n/bulkbrand [LIMIT]',reply_markup=InlineKeyboardMarkup(kb))
async def button(update,context):
    q=update.callback_query; await q.answer()
    if not await is_admin(q.from_user.id): return await q.edit_message_text('⛔ Admin access only.')
    if q.data=='routes':
        rs=await db.get_routes(); return await q.edit_message_text('📡 Routes\n'+'\n'.join(f"#{r['id']} {r['source_id']} → {r['dest_id']} [{'ON' if r['enabled'] else 'OFF'}]" for r in rs) if rs else 'No routes configured.')
    if q.data=='toggle_approval':
        v='off' if await db.get_setting('auto_approve','off')=='on' else 'on'; await db.set_setting('auto_approve',v); return await q.edit_message_text('Auto approval: '+v.upper())
    if q.data=='stats': return await q.edit_message_text('Delivery stats: '+str(await db.delivery_stats()))
    if q.data=='jobs':
        js=await db.list_sync_jobs(); return await q.edit_message_text('Sync jobs:\n'+'\n'.join(f"#{j['id']} {j['source_id']}→{j['dest_id']} {j['status']} processed={j['processed']} failed={j['failed']}" for j in js) if js else 'No sync jobs.')
    if q.data=='brands':
        bs=await db.list_branding(); return await q.edit_message_text('Branding:\n'+'\n'.join(f"#{b['id']} {b['old_text']} → {b['new_text']} [{'ON' if b['enabled'] else 'OFF'}]" for b in bs) if bs else 'No branding rules.')
async def add_route_cmd(u,c):
    if not await admin_only(u): return
    if len(c.args)!=2: return await u.effective_message.reply_text('Usage: /addroute SOURCE_CHAT_ID DEST_CHAT_ID')
    ok=await db.add_route(*c.args); await u.effective_message.reply_text('✅ Route added.' if ok else 'ℹ️ Route already exists.')
async def routes_cmd(u,c):
    if not await admin_only(u): return
    rs=await db.get_routes(); await u.effective_message.reply_text('\n'.join(f"#{r['id']} {r['source_id']} → {r['dest_id']} [{'ON' if r['enabled'] else 'OFF'}]" for r in rs) or 'No routes.')
async def route_toggle(u,c,on):
    if not await admin_only(u): return
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /routeon ID or /routeoff ID')
    n=await db.set_route(c.args[0],on); await u.effective_message.reply_text('✅ Updated.' if n else 'Route ID not found.')
async def route_on(u,c): await route_toggle(u,c,True)
async def route_off(u,c): await route_toggle(u,c,False)
async def route_delete(u,c):
    if not await admin_only(u): return
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /delroute ID')
    n=await db.delete_route(c.args[0]); await u.effective_message.reply_text('🗑 Deleted.' if n else 'Route not found.')
async def branding(u,c):
    if not await admin_only(u): return
    raw=u.effective_message.text.partition(' ')[2]
    if '|' not in raw: return await u.effective_message.reply_text('Usage: /branding OLD_TEXT | NEW_TEXT')
    old,new=(x.strip() for x in raw.split('|',1))
    if not old: return await u.effective_message.reply_text('OLD_TEXT cannot be empty.')
    i=await db.add_branding(old,new); await u.effective_message.reply_text(f'✅ Branding rule #{i} saved (future deliveries and /bulkbrand).')
async def brandlist(u,c):
    if not await admin_only(u): return
    bs=await db.list_branding(); await u.effective_message.reply_text('\n'.join(f"#{b['id']} {b['old_text']} → {b['new_text']} [{'ON' if b['enabled'] else 'OFF'}]" for b in bs) or 'No rules.')
async def branddel(u,c):
    if not await admin_only(u): return
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /branddel ID')
    await db.delete_branding(c.args[0]); await u.effective_message.reply_text('Branding rule deleted if it existed.')
async def sync_cmd(u,c):
    if not await admin_only(u): return
    if len(c.args) not in (2,3): return await u.effective_message.reply_text('Usage: /sync SOURCE_ID DEST_ID [LIMIT]')
    w=u.application.bot_data['telethon_worker']
    if not w.client: return await u.effective_message.reply_text('Telethon not connected. Configure API_ID, API_HASH and TELETHON_SESSION.')
    limit=int(c.args[2]) if len(c.args)==3 else None
    jid=await w.start_sync_task(c.args[0],c.args[1],limit); await u.effective_message.reply_text(f'⏳ Sync job #{jid} started. Use /pausesync {jid} to pause; /jobs to check progress.')
async def pausesync(u,c):
    if not await admin_only(u): return
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /pausesync JOB_ID')
    await u.application.bot_data['telethon_worker'].pause_sync(int(c.args[0])); await u.effective_message.reply_text('Pause requested. Current message will finish before checkpoint pause.')
async def jobs_cmd(u,c):
    if not await admin_only(u): return
    js=await db.list_sync_jobs(); await u.effective_message.reply_text('\n'.join(f"#{j['id']} {j['status']} {j['source_id']}→{j['dest_id']} processed={j['processed']} failed={j['failed']}" for j in js) or 'No jobs.')
async def admin_add(u,c):
    if str(u.effective_user.id) not in owner_ids(): return await u.effective_message.reply_text('⛔ Owner only.')
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /addadmin USER_ID')
    await db.add_admin(c.args[0],u.effective_user.id); await u.effective_message.reply_text('Admin added.')
async def admin_del(u,c):
    if str(u.effective_user.id) not in owner_ids(): return await u.effective_message.reply_text('⛔ Owner only.')
    if len(c.args)!=1: return await u.effective_message.reply_text('Usage: /deladmin USER_ID')
    await db.remove_admin(c.args[0]); await u.effective_message.reply_text('Admin removed if present.')
async def admins_cmd(u,c):
    if not await admin_only(u): return
    a=await db.list_admins(); await u.effective_message.reply_text('Additional admins: '+(', '.join(x['user_id'] for x in a) if a else 'none')+'\nOwner IDs are set in OWNER_IDS.')
async def bulkbrand(u,c):
    if not await admin_only(u): return
    w=u.application.bot_data['telethon_worker']
    try: n=await w.bulk_rebrand(int(c.args[0]) if c.args else 500); await u.effective_message.reply_text(f'Bulk branding complete. Edited {n} messages.')
    except Exception as e: await u.effective_message.reply_text('Bulk branding failed: '+str(e)[:250])
