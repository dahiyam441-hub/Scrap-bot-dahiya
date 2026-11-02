import asyncio,logging,os
from telethon import TelegramClient,events
from telethon.errors import FloodWaitError
from app import db
log=logging.getLogger(__name__)
class TelethonWorker:
    def __init__(self,bot_app=None): self.bot_app=bot_app; self.client=None; self.sync_tasks={}; self.sync_stop=set()
    async def start(self):
        aid=os.getenv('API_ID','').strip(); ah=os.getenv('API_HASH','').strip(); sess=os.getenv('TELETHON_SESSION','').strip()
        if not (aid and ah and sess): log.warning('Telethon disabled: credentials/session missing.'); return
        self.client=TelegramClient(sess,int(aid),ah); await self.client.start(); self.client.add_event_handler(self.on_new_message,events.NewMessage); log.info('Telethon connected.')
    async def stop(self):
        for t in list(self.sync_tasks.values()): t.cancel()
        if self.sync_tasks: await asyncio.gather(*self.sync_tasks.values(),return_exceptions=True)
        if self.client and self.client.is_connected(): await self.client.disconnect()
    async def transform_caption(self,caption):
        for old,new in await db.get_branding_rules():
            if old: caption=caption.replace(old,new)
        return caption
    async def _deliver(self,msg,dest,source):
        if await db.was_delivered(source,msg.id,dest): return 'duplicate'
        caption=await self.transform_caption(msg.message or '')
        if msg.media: sent=await self.client.send_file(int(dest),msg.media,caption=caption or None, formatting_entities=msg.entities)
        elif caption: sent=await self.client.send_message(int(dest),caption,formatting_entities=msg.entities)
        else: return 'skipped'
        sent_id=sent[0].id if isinstance(sent,list) and sent else getattr(sent,'id',None)
        await db.log_delivery(source,msg.id,dest,'success',dest_message_id=sent_id); return 'success'
    async def on_new_message(self,event):
        for r in await db.get_routes():
            if r['enabled'] and str(r['source_id'])==str(event.chat_id):
                try: await self._deliver(event.message,r['dest_id'],r['source_id'])
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    try: await self._deliver(event.message,r['dest_id'],r['source_id'])
                    except Exception as x: log.exception('Live retry failed'); await db.log_delivery(r['source_id'],event.message.id,r['dest_id'],'failed',repr(x))
                except Exception as e: log.exception('Live forward failed'); await db.log_delivery(r['source_id'],event.message.id,r['dest_id'],'failed',repr(e))
    async def historical_sync(self,source,dest,limit=None,job_id=None):
        if not self.client: raise RuntimeError('Telethon is not connected; configure API_ID, API_HASH and TELETHON_SESSION.')
        jid=job_id or await db.create_sync_job(source,dest); job=await db.get_sync_job(jid); last=job['last_message_id']
        try:
            async for msg in self.client.iter_messages(int(source),reverse=True,min_id=last,limit=limit):
                if jid in self.sync_stop: await db.save_checkpoint(jid,last,'paused'); break
                try:
                    outcome=await self._deliver(msg,dest,source)
                    await db.save_checkpoint(jid,msg.id,processed_delta=1 if outcome=='success' else 0)
                except FloodWaitError as e: await db.save_checkpoint(jid,last,'paused'); raise RuntimeError(f'Telegram FloodWait: retry after {e.seconds}s')
                except Exception as e: await db.log_delivery(source,msg.id,dest,'failed',repr(e)); await db.save_checkpoint(jid,msg.id,failed_delta=1)
                last=msg.id
            else: await db.set_job_status(jid,'completed')
        except Exception: await db.set_job_status(jid,'paused'); log.exception('Historical sync paused; checkpoint retained.'); raise
        job=await db.get_sync_job(jid); return {'job_id':jid,'processed':job['processed'],'failed':job['failed'],'status':job['status']}
    async def start_sync_task(self,source,dest,limit=None):
        jid=await db.create_sync_job(source,dest)
        if jid in self.sync_tasks and not self.sync_tasks[jid].done(): return jid
        self.sync_stop.discard(jid)
        async def run():
            try: await self.historical_sync(source,dest,limit,jid)
            except Exception: log.exception('Sync task %s stopped',jid)
            finally: self.sync_tasks.pop(jid,None)
        self.sync_tasks[jid]=asyncio.create_task(run()); return jid
    async def pause_sync(self,jid): self.sync_stop.add(int(jid)); return True
    async def retry_failed(self,limit=100):
        if not self.client: raise RuntimeError('Telethon is not connected.')
        rows=[r for r in await db.delivered_rows() if r['status']=='failed'][:limit]
        return len(rows)
    async def bulk_rebrand(self,limit=500):
        if not self.client: raise RuntimeError('Telethon is not connected.')
        rules=await db.get_branding_rules(); changed=0
        rows=await db.delivered_rows()
        for r in rows[:limit]:
            try:
                msg=await self.client.get_messages(int(r['dest_id']),ids=int(r['dest_message_id']))
                if not msg: continue
                caption=msg.message or ''
                for old,new in rules:
                    if old: caption=caption.replace(old,new)
                if caption!=(msg.message or ''): await self.client.edit_message(int(r['dest_id']),msg.id,caption,formatting_entities=msg.entities); changed+=1
            except Exception: log.exception('Bulk rebrand failed for delivery %s',r['id'])
        return changed
