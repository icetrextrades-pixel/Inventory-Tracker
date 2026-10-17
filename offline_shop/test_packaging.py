import sqlite3
import unittest
from ledger import Ledger

class PackageTests(unittest.TestCase):
    def setUp(self):self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08')
    def tearDown(self):self.l.db.close()
    def test_crates_and_loose_convert_for_stock_and_costing(self):
        product=self.l.product('Castle Quart','bottle','Crate',12)
        self.assertEqual(self.l.receipt_bulk(self.p,product,'2026-10-01','Supplier','INV',2,3,'24','3'),27)
        self.l.stock(self.p,product,0,18,0,0,'0','2')
        rows,totals=self.l.report(self.p)
        self.assertEqual((rows[0][3],rows[0][8]),(27,9))
        self.assertEqual(totals['Cost of goods sold'],'9.00')
        self.assertEqual(totals['Stock-implied sales'],'18.00')
    def test_case_size_changes_do_not_rewrite_history(self):
        product=self.l.product('Sugar','packet','Case',10)
        self.l.receipt_bulk(self.p,product,'2026-10-01','','',3,0,'30','0')
        self.l.set_packaging(product,'Case',12)
        receipt=self.l.db.execute('SELECT * FROM receipts').fetchone()
        history=self.l.db.execute('SELECT * FROM receipt_packages').fetchone()
        self.assertEqual((receipt['units'],history['per_package']),(30,10))
        self.assertEqual(self.l.package_units(product,2,1),25)
    def test_old_products_default_to_individual_and_bad_sizes_rejected(self):
        with self.l.db:pid=self.l.db.execute("INSERT INTO products(name,unit) VALUES ('Legacy','each')").lastrowid
        self.assertEqual(self.l.package_units(pid,1,2),3)
        for kind,size in [('Crate',0),('Case','1.5'),('Individual',12),('Invalid',1)]:
            with self.assertRaises(ValueError):self.l.set_packaging(pid,kind,size)
    def test_failed_bulk_receipt_and_locked_period_leave_no_partial_rows(self):
        pid=self.l.product('Bread','loaf','Tray',10)
        with self.assertRaises(ValueError):self.l.receipt_bulk(self.p,pid,'2026-10-01','','',0,0,'0','0')
        with self.assertRaises(ValueError):self.l.receipt_bulk(self.p,pid,'2026-10-01','','',1,0,'-1','0')
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],0)
        self.l.stock(self.p,pid,0,0,0,0,'0','1');self.l.set_lock(self.p,True,'Closed')
        with self.assertRaises(sqlite3.IntegrityError):self.l.receipt_bulk(self.p,pid,'2026-10-01','','',1,0,'5','0')
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM receipt_packages').fetchone()[0],0)
    def test_receipt_correction_does_not_keep_stale_package_description(self):
        pid=self.l.product('Castle','bottle','Crate',12)
        self.l.receipt_bulk(self.p,pid,'2026-10-01','','',1,0,'6','0')
        rid=self.l.db.execute('SELECT id FROM receipts').fetchone()[0]
        self.l.correct_receipt(rid,11,'5.5','0','One fewer received')
        self.assertIsNone(self.l.db.execute('SELECT 1 FROM receipt_packages').fetchone())
        self.assertTrue(self.l.db.execute("SELECT 1 FROM audit_log WHERE entity='receipt_packages' AND action='DELETE'").fetchone())

if __name__=='__main__':unittest.main()
