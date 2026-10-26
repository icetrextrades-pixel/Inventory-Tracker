import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from app import SHOPS,shop_database,assign_shop,migrate_legacy,database_has_records,printable
from ledger import Ledger,Cloud
from updater import run_update,FILES

class ShopTests(unittest.TestCase):
    def test_shops_keep_records_and_reports_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledgers=[]
            try:
                for index,shop in enumerate(SHOPS):
                    ledger=Ledger(shop_database(root,shop));assign_shop(ledger,shop);ledger.shop_id=shop;ledgers.append(ledger)
                    p=ledger.period('2026-10-01','2026-10-08');i=ledger.product('Sugar','packet')
                    ledger.stock(p,i,index+1,0,0,0,'1','2')
                    self.assertIn(SHOPS[shop][0],printable(ledger,p))
                    self.assertEqual(ledger.report(p)[1]['Stock-implied sales'],f'{(index+1)*2:.2f}')
                self.assertEqual([l.db.execute('SELECT opening FROM stock').fetchone()[0] for l in ledgers],[1,2,3])
                with self.assertRaises(ValueError):assign_shop(ledgers[0],'bizzy-tuckshop')
                with self.assertRaises(ValueError):shop_database(root,'../other')
            finally:
                for ledger in ledgers:ledger.db.close()
    def test_legacy_assignment_preserves_original_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);legacy=Ledger(root/'shop.sqlite3');legacy.product('Old stock','each');legacy.db.close()
            before=(root/'shop.sqlite3').read_bytes()
            existing=Ledger(shop_database(root,'mutowei-bottle-store'));existing.product('New stock','each');existing.db.close()
            with self.assertRaises(ValueError):migrate_legacy(root,'mutowei-bottle-store')
            destination=migrate_legacy(root,'bizzy-tuckshop')
            self.assertEqual((root/'shop.sqlite3').read_bytes(),before)
            with sqlite3.connect(destination) as copied:
                self.assertEqual(copied.execute('SELECT name FROM products').fetchone()[0],'Old stock')
                self.assertEqual(copied.execute('SELECT shop FROM shop_identity').fetchone()[0],'bizzy-tuckshop')
            self.assertFalse(database_has_records(shop_database(root,'chikofa-tuckshop')))
            with self.assertRaises(ValueError):migrate_legacy(root,'chikofa-tuckshop')
    def test_cloud_namespace_and_identity_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=shop_database(root,'bizzy-tuckshop');ledger=Ledger(path);assign_shop(ledger,'bizzy-tuckshop');ledger.db.close()
            client=Cloud('https://example.supabase.co','sb_publishable_test',shop='bizzy-tuckshop');client.owner='00000000-0000-0000-0000-000000000001'
            captured={}
            def upload(api,payload):captured.update({'api':api,**payload});return 1
            client.request=upload;client.upload(path,0)
            self.assertEqual(captured['target_shop'],'bizzy-tuckshop');self.assertTrue(captured['api'].endswith('family_shop_upload_shop'))
            requests=[]
            def download(api):requests.append(api);return [{'version':1,'payload':captured['snapshot']}]
            client.request=download;client.download(root/'restored.sqlite3')
            self.assertIn('&shop=eq.bizzy-tuckshop',requests[0])
            other=Cloud(client.url,client.key,shop='chikofa-tuckshop');other.owner=client.owner;other.request=download
            with self.assertRaises(ValueError):other.download(root/'wrong.sqlite3')
            with self.assertRaises(ValueError):other.upload(path,0)
    def test_updater_backs_up_every_shop(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'program';root.mkdir();data=base/'data';data.mkdir()
            for shop in SHOPS:
                ledger=Ledger(shop_database(data,shop));ledger.product(shop,'each');ledger.db.close()
            def stage(destination,sha):
                for name in (*FILES,'installed-version.txt'):(destination/name).write_text('new')
            with patch('updater.stage_update',side_effect=stage):run_update(root,'a'*40,data/'before-update.sqlite3')
            backups=list(data.glob('before-update-*.sqlite3'))
            self.assertEqual(len(backups),3)
            for backup in backups:
                with sqlite3.connect(backup) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0],1)

if __name__=='__main__':unittest.main()
