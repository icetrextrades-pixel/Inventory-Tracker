import json
import unittest
import sqlite3
from ledger import Ledger

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08');self.i=self.l.product('Bread','loaf')
        self.l.stock(self.p,self.i,10,5,0,0,'.50','1')
    def tearDown(self):self.l.db.close()
    def test_lock_reopen_and_history(self):
        self.l.set_lock(self.p,True,'Week checked')
        with self.assertRaises(sqlite3.IntegrityError):self.l.cash(self.p,'2026-10-01','5','0','0','0','0','')
        with self.assertRaises(sqlite3.IntegrityError):self.l.stock(self.p,self.i,10,4,0,0,'.50','1')
        self.l.set_lock(self.p,False,'Correcting count')
        self.l.stock(self.p,self.i,10,4,0,0,'.50','1')
        event=self.l.db.execute("SELECT * FROM audit_log WHERE entity='stock' AND action='UPDATE'").fetchone()
        self.assertEqual(json.loads(event['before_data'])['closing'],5)
        self.assertEqual(json.loads(event['after_data'])['closing'],4)
    def test_receipt_correction_updates_order_and_guards_stock(self):
        order=self.l.order(self.i,'Supplier','PO','2026-10-01',10,'5')
        self.l.receive_order(order,self.p,'2026-10-02',10,'5','0')
        rid=self.l.db.execute('SELECT id FROM receipts').fetchone()[0]
        self.l.correct_receipt(rid,4,'2','0','Received six fewer units')
        self.assertEqual(self.l.db.execute('SELECT units FROM deliveries').fetchone()[0],4)
        event=self.l.db.execute("SELECT * FROM audit_log WHERE entity='receipts' AND action='UPDATE'").fetchone()
        self.assertEqual(event['reason'],'Received six fewer units')
        self.l.stock(self.p,self.i,0,4,0,0,'0','1')
        with self.assertRaises(ValueError):self.l.correct_receipt(rid,0,'0','0','void')
        self.assertEqual(self.l.db.execute('SELECT units FROM receipts').fetchone()[0],4)
    def test_repayment_after_locked_sale_allowed(self):
        debt=self.l.debt('Customer',self.p,'2026-10-01','3','')
        self.l.set_lock(self.p,True,'Complete')
        with self.assertRaises(sqlite3.IntegrityError):self.l.repay(debt,'2026-10-02','1','Cash')
        self.l.repay(debt,'2026-10-09','1','Cash')
        self.assertEqual(self.l.customer_balances()[0]['paid'],100)
    def test_void_keeps_history(self):
        self.l.receipt(self.p,self.i,'2026-10-01','','',2,'1','0')
        rid=self.l.db.execute('SELECT id FROM receipts').fetchone()[0]
        self.l.correct_receipt(rid,0,'0','0','Duplicate receipt')
        self.assertEqual(self.l.db.execute('SELECT units FROM receipts').fetchone()[0],0)
        self.assertTrue(self.l.db.execute("SELECT 1 FROM audit_log WHERE reason='Duplicate receipt'").fetchone())

if __name__=='__main__':unittest.main()
