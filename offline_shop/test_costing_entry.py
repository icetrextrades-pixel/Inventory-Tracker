import unittest
from decimal import Decimal
from ledger import Ledger,purchase_unit_cost

class EntryCostTests(unittest.TestCase):
    def setUp(self):
        self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08');self.i=self.l.product('Castle Quart','bottle','Crate',12)
    def tearDown(self):self.l.db.close()
    def test_purchase_cost_uses_individual_units_and_delivery(self):
        self.assertEqual(purchase_unit_cost(12,'12','3'),(Decimal('1'),Decimal('1.25')))
        with self.assertRaises(ValueError):purchase_unit_cost(0,'12','0')
    def test_price_mode_preview_matches_saved_totals(self):
        self.l.receipt_bulk(self.p,self.i,'2026-10-01','','',1,0,'12','3')
        preview=self.l.stock_preview(self.p,self.i,0,5,1,0,'0','2')
        self.assertEqual((preview['sold'],preview['unit_cost'],preview['sales']),(6,Decimal('1.25'),Decimal('12')))
        self.l.stock(self.p,self.i,0,5,1,0,'0','2')
        self.assertEqual(self.l.report(self.p)[1]['Stock-implied sales'],'12.00')
        self.assertEqual(self.l.report(self.p)[1]['Cost of goods sold'],'7.50')
    def test_total_mode_preserves_exact_revenue_and_switching_clears_override(self):
        self.l.stock(self.p,self.i,3,0,0,0,'1','999',sales_total='10')
        rows,totals=self.l.report(self.p)
        self.assertEqual(rows[0][-2:],[ '3.3333','10.00'])
        self.assertEqual(totals['Gross profit'],'7.00')
        preview=self.l.stock_preview(self.p,self.i,3,0,0,0,'1','999',sales_total='10')
        self.assertEqual(preview['sales'],Decimal('10'))
        self.l.stock(self.p,self.i,3,0,0,0,'1','3.50')
        self.assertEqual(self.l.report(self.p)[1]['Stock-implied sales'],'10.50')
        self.assertIsNone(self.l.db.execute('SELECT 1 FROM stock_sales').fetchone())
    def test_nonzero_sales_for_zero_sold_rejected_without_overwriting(self):
        self.l.stock(self.p,self.i,3,0,0,0,'1','2')
        with self.assertRaises(ValueError):self.l.stock(self.p,self.i,3,3,0,0,'1','2',sales_total='10')
        self.assertEqual(self.l.report(self.p)[1]['Stock-implied sales'],'6.00')

if __name__=='__main__':unittest.main()
