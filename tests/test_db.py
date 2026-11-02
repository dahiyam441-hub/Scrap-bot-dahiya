import asyncio, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from app import db

class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.patch=patch.object(db,'DB_PATH',Path(self.tmp.name)/'test.sqlite3'); self.patch.start(); await db.init_db()
    async def asyncTearDown(self): self.patch.stop(); self.tmp.cleanup()
    async def test_route_crud_and_duplicate(self):
        self.assertTrue(await db.add_route('-1001','-1002'))
        self.assertFalse(await db.add_route('-1001','-1002'))
        rows=await db.get_routes(); self.assertEqual(len(rows),1)
        self.assertEqual(await db.set_route(rows[0]['id'],False),1)
        self.assertEqual((await db.get_routes())[0]['enabled'],0)
        self.assertEqual(await db.delete_route(rows[0]['id']),1)
    async def test_settings_and_branding(self):
        self.assertEqual(await db.get_setting('auto_approve','off'),'off')
        await db.set_setting('auto_approve','on'); self.assertEqual(await db.get_setting('auto_approve'),'on')
        await db.add_branding('@old','@new'); self.assertEqual(await db.get_branding_rules(),[('@old','@new')])
    async def test_sync_resume_checkpoint(self):
        jid=await db.create_sync_job('-1001','-1002')
        await db.save_checkpoint(jid,55,processed_delta=4)
        await db.save_checkpoint(jid,55,'paused')
        jid2=await db.create_sync_job('-1001','-1002')
        self.assertEqual(jid,jid2)
        job=await db.get_sync_job(jid); self.assertEqual(job['last_message_id'],55); self.assertEqual(job['status'],'running'); self.assertEqual(job['processed'],4)
    async def test_delivery_upsert_and_dedup(self):
        await db.log_delivery('-1001',9,'-1002','failed','temporary')
        self.assertFalse(await db.was_delivered('-1001',9,'-1002'))
        await db.log_delivery('-1001',9,'-1002','success','')
        self.assertTrue(await db.was_delivered('-1001',9,'-1002'))
        self.assertEqual(await db.delivery_stats(),{'success':1})
        await db.log_delivery('-1001',10,'-1002','success','',dest_message_id=77)
        rows=await db.delivered_rows(); self.assertEqual(rows[0]['dest_message_id'],77)

if __name__=='__main__': unittest.main()
