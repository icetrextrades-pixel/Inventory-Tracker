import unittest
from ledger import Ledger, money

class Tests(unittest.TestCase):
    def setUp(self):
        self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08');self.i=self.l.product('Bread','loaf')
    def test_weighted_cost_drawings_breakage_and_expenses(self):
        self.l.receipt(self.p,self.i,'2026-10-02','Bakery','1',10,'6','2')
        self.l.stock(self.p,self.i,10,5,2,1,'.60','1')
        self.l.cash(self.p,'2026-10-02','8','1','2','1','2','')
        rows,t=self.l.report(self.p)
        self.assertEqual(rows[0][8],12)
        self.assertEqual(t['Cost of goods sold'],'8.40')
        self.assertEqual(t['Gross profit'],'3.60')
        self.assertEqual(t['Net profit before tax (stock-implied)'],'0.90')
        self.assertEqual(t['Unreconciled difference (positive = short)'],'0.00')
    def test_reference_difference(self):
        self.l.stock(self.p,self.i,77465,0,0,0,'0','.01')
        self.l.cash(self.p,'2026-10-01','531','49.15','17.25','10','0','')
        self.assertEqual(self.l.report(self.p)[1]['Unreconciled difference (positive = short)'],'167.25')
    def test_daily_update_not_double_counted(self):
        for cash in ['10','20']:self.l.cash(self.p,'2026-10-01',cash,'0','0','0','0','')
        self.assertEqual(self.l.report(self.p)[1]['Cash handed over'],'20.00')
    def test_validation(self):
        with self.assertRaises(ValueError):self.l.stock(self.p,self.i,0,1,0,0,'0','1')
        with self.assertRaises(ValueError):self.l.receipt(self.p,self.i,'2026-11-01','','',1,'1','0')
        with self.assertRaises(ValueError):money('NaN')
        with self.assertRaises(ValueError):self.l.period('2026-10-05','2026-10-10')
    def test_incomplete_receipt_blocks_report(self):
        self.l.receipt(self.p,self.i,'2026-10-01','','',1,'1','0')
        with self.assertRaises(ValueError):self.l.report(self.p)
    def test_partial_order(self):
        order=self.l.order(self.i,'Bakery','PO-1','2026-10-01',10,'8')
        self.l.receive_order(order,self.p,'2026-10-02',4,'3','1')
        with self.assertRaises(ValueError):self.l.receive_order(order,self.p,'2026-10-03',7,'4','0')
        self.l.receive_order(order,self.p,'2026-10-03',6,'4','0')
        self.assertEqual(self.l.db.execute('SELECT SUM(units) FROM receipts').fetchone()[0],10)
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],2)
    def test_debt_repayment_does_not_inflate_sales(self):
        debt=self.l.debt('Customer',self.p,'2026-10-01','10','')
        self.l.repay(debt,'2026-10-02','4','Cash')
        with self.assertRaises(ValueError):self.l.repay(debt,'2026-10-03','7','Cash')
        self.assertEqual(self.l.report(self.p)[1]['Cash handed over'],'0.00')
        self.assertEqual(self.l.db.execute('SELECT SUM(amount) FROM repayments').fetchone()[0],400)
    def test_carry_forward_keeps_existing_records(self):
        self.l.receipt(self.p,self.i,'2026-10-02','','',10,'8','0')
        self.l.stock(self.p,self.i,10,5,0,0,'.60','1')
        nxt=self.l.period('2026-10-09','2026-10-10')
        self.l.carry_forward(nxt)
        row=self.l.db.execute('SELECT * FROM stock WHERE period=?',(nxt,)).fetchone()
        self.assertEqual((row['opening'],row['closing'],row['opening_cost']),(5,5,70))
        with self.assertRaises(ValueError):self.l.carry_forward(nxt)
        self.assertEqual(self.l.report(self.p)[1]['Stock-implied sales'],'15.00')
    def test_database_upgrade_preserves_v1(self):
        import tempfile,sqlite3
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.sqlite3'
            old=sqlite3.connect(path)
            old.execute('CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, unit TEXT NOT NULL)')
            old.execute("INSERT INTO products VALUES (1,'Existing product','each')")
            old.commit();old.close()
            upgraded=Ledger(path)
            self.assertEqual(upgraded.db.execute('SELECT name FROM products').fetchone()[0],'Existing product')
            upgraded.backup(Path(folder)/'backup.sqlite3')
            upgraded.db.close()
    def tearDown(self):self.l.db.close()

if __name__=='__main__':unittest.main()
