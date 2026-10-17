import unittest
from ledger import Ledger,arrange_scan,import_reviewed

class ScannerTests(unittest.TestCase):
    def setUp(self):self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08')
    def tearDown(self):self.l.db.close()
    def test_sort_stock_leaves_unknowns_blank(self):
        text,unparsed=arrange_scan('Bread 10 20 30 4 26 1.00 26.00\nUnreadable line','Stock counts')
        self.assertIn('Bread,each,10,4,,,,1.00',text)
        self.assertEqual(unparsed,['Unreadable line'])
        with self.assertRaises(ValueError):import_reviewed(self.l,self.p,'Stock counts',text,'photo.jpg')
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM products').fetchone()[0],0)
    def test_batch_rolls_back_if_any_row_bad(self):
        text='Product,Unit,Opening,Closing,Drawings,Broken,OpeningCost,SellingPrice\nBread,loaf,10,2,0,0,.50,1\nMilk,bottle,0,4,0,0,.60,1\n'
        with self.assertRaisesRegex(ValueError,'CSV row 3'):import_reviewed(self.l,self.p,'Stock counts',text,'scan')
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM products').fetchone()[0],0)
    def test_import_records_history_and_prevents_overwrite(self):
        text='Date,Cash,EcoCash,Credit,CashOut,Expenses,Notes\n2026-10-01,10,2,1,0,0,Checked\n'
        self.assertEqual(import_reviewed(self.l,self.p,'Daily money',text,'sheet.png'),1)
        self.assertEqual(self.l.report(self.p)[1]['Cash handed over'],'10.00')
        self.assertTrue(self.l.db.execute("SELECT 1 FROM audit_log WHERE reason LIKE '%sheet.png%'").fetchone())
        with self.assertRaises(ValueError):import_reviewed(self.l,self.p,'Daily money',text,'sheet.png')
    def test_receipts_then_stock_and_locked_period(self):
        receipts='Date,Product,Unit,Supplier,Reference,Units,GoodsCost,DeliveryCost\n2026-10-01,Bread,loaf,Bakery,INV-1,10,5,1\n'
        stock='Product,Unit,Opening,Closing,Drawings,Broken,OpeningCost,SellingPrice\nBread,loaf,0,2,0,0,0,1\n'
        import_reviewed(self.l,self.p,'Goods received',receipts,'invoice.png')
        import_reviewed(self.l,self.p,'Stock counts',stock,'count.png')
        self.assertEqual(self.l.report(self.p)[1]['Cost of goods sold'],'4.80')
        self.l.set_lock(self.p,True,'Checked')
        with self.assertRaisesRegex(ValueError,'locked'):import_reviewed(self.l,self.p,'Goods received',receipts,'invoice.png')

if __name__=='__main__':unittest.main()
