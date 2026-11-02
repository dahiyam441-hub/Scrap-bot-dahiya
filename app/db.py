"""Async SQLite persistence for Dahiya Auto Forwarder."""
import os, sqlite3, asyncio
from pathlib import Path
DB_PATH=Path(os.getenv('DB_PATH','data/bot.sqlite3'))
_db_lock=asyncio.Lock()
def _connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB_PATH,timeout=30); c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=30000'); return c
async def _run(fn,*a):
    async with _db_lock: return await asyncio.to_thread(fn,*a)
def _init():
    with _connect() as d:
        d.executescript('''
        CREATE TABLE IF NOT EXISTS routes(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL,dest_id TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,UNIQUE(source_id,dest_id));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admins(user_id TEXT PRIMARY KEY,added_by TEXT NOT NULL DEFAULT 'owner');
        CREATE TABLE IF NOT EXISTS branding(id INTEGER PRIMARY KEY,old_text TEXT NOT NULL,new_text TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sync_jobs(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL,dest_id TEXT NOT NULL,last_message_id INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'pending',processed INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS delivery_log(id INTEGER PRIMARY KEY,source_id TEXT,source_message_id INTEGER,dest_id TEXT,status TEXT,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(source_id,source_message_id,dest_id));
        ''')
        cols={r['name'] for r in d.execute('PRAGMA table_info(delivery_log)')}
        if 'dest_message_id' not in cols: d.execute('ALTER TABLE delivery_log ADD COLUMN dest_message_id INTEGER')
def _query(sql,args=(),one=False):
    with _connect() as d:
        cur=d.execute(sql,args); rows=cur.fetchall(); return (dict(rows[0]) if rows else None) if one else [dict(r) for r in rows]
def _exec(sql,args=()):
    with _connect() as d: cur=d.execute(sql,args); return cur.rowcount,cur.lastrowid
async def init_db(): await _run(_init)
async def add_route(s,d): return (await _run(_exec,'INSERT OR IGNORE INTO routes(source_id,dest_id) VALUES(?,?)',(str(s),str(d))))[0]==1
async def get_routes(): return await _run(_query,'SELECT * FROM routes ORDER BY id')
async def set_route(i,on): return (await _run(_exec,'UPDATE routes SET enabled=? WHERE id=?',(int(on),int(i))))[0]
async def delete_route(i): return (await _run(_exec,'DELETE FROM routes WHERE id=?',(int(i),)))[0]
async def get_setting(k,default=''): 
    r=await _run(_query,'SELECT value FROM settings WHERE key=?',(k,),True); return r['value'] if r else default
async def set_setting(k,v): await _run(_exec,'INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
async def list_admins(): return await _run(_query,'SELECT user_id,added_by FROM admins ORDER BY user_id')
async def add_admin(uid,by): return (await _run(_exec,'INSERT OR IGNORE INTO admins(user_id,added_by) VALUES(?,?)',(str(uid),str(by))))[0]==1
async def remove_admin(uid): return (await _run(_exec,'DELETE FROM admins WHERE user_id=?',(str(uid),)))[0]
async def add_branding(old,new): return (await _run(_exec,'INSERT INTO branding(old_text,new_text) VALUES(?,?)',(old,new)))[1]
async def list_branding(): return await _run(_query,'SELECT * FROM branding ORDER BY id')
async def get_branding_rules(): return [(r['old_text'],r['new_text']) for r in await _run(_query,'SELECT old_text,new_text FROM branding WHERE enabled=1 ORDER BY id')]
async def toggle_branding(i,on): return (await _run(_exec,'UPDATE branding SET enabled=? WHERE id=?',(int(on),int(i))))[0]
async def delete_branding(i): return (await _run(_exec,'DELETE FROM branding WHERE id=?',(int(i),)))[0]
def _create_job(s,d):
    with _connect() as x:
        r=x.execute("SELECT id FROM sync_jobs WHERE source_id=? AND dest_id=? AND status IN ('running','paused') ORDER BY id DESC LIMIT 1",(str(s),str(d))).fetchone()
        if r: x.execute("UPDATE sync_jobs SET status='running',updated_at=CURRENT_TIMESTAMP WHERE id=?",(r['id'],)); return r['id']
        return x.execute("INSERT INTO sync_jobs(source_id,dest_id,status) VALUES(?,?,'running')",(str(s),str(d))).lastrowid
async def create_sync_job(s,d): return await _run(_create_job,s,d)
async def get_sync_job(i): return await _run(_query,'SELECT * FROM sync_jobs WHERE id=?',(int(i),),True)
async def list_sync_jobs(): return await _run(_query,'SELECT * FROM sync_jobs ORDER BY id DESC LIMIT 20')
async def save_checkpoint(i,mid,status=None,processed_delta=0,failed_delta=0):
    await _run(_exec,'UPDATE sync_jobs SET last_message_id=?,status=COALESCE(?,status),processed=processed+?,failed=failed+?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(int(mid),status,int(processed_delta),int(failed_delta),int(i)))
async def set_job_status(i,status): await _run(_exec,'UPDATE sync_jobs SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,int(i)))
async def log_delivery(s,mid,d,status,error='',dest_message_id=None):
    await _run(_exec,'INSERT INTO delivery_log(source_id,source_message_id,dest_id,status,error,dest_message_id) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,source_message_id,dest_id) DO UPDATE SET status=excluded.status,error=excluded.error,dest_message_id=COALESCE(excluded.dest_message_id,delivery_log.dest_message_id),created_at=CURRENT_TIMESTAMP',(str(s),int(mid),str(d),status,str(error)[:1000],dest_message_id))
async def was_delivered(s,mid,d): return bool(await _run(_query,"SELECT 1 AS yes FROM delivery_log WHERE source_id=? AND source_message_id=? AND dest_id=? AND status='success'",(str(s),int(mid),str(d)),True))
async def delivery_stats(): return {r['status']:r['n'] for r in await _run(_query,'SELECT status,COUNT(*) n FROM delivery_log GROUP BY status')}
async def delivered_rows(): return await _run(_query,"SELECT * FROM delivery_log WHERE status='success' AND dest_message_id IS NOT NULL ORDER BY id")
