import unittest
from decimal import Decimal
from ledger import Ledger

class MethodTests(unittest.TestCase):
    def setUp(self):
        self.l=Ledger(':memory:');self.p=self.l.period('2026-10-01','2026-10-08');self.i=self.l.product('Sugar','packet','Case',10,cost_method='FIFO')
    def tearDown(self):self.l.db.close()
    def receipts(self,first='10',second='20'):
        # Insert out of chronological order; FIFO must use purchase dates.
        self.l.receipt(self.p,self.i,'2026-10-03','S','Second',10,second,'0')
        self.l.receipt(self.p,self.i,'2026-10-01','S','First',10,first,'0')
    def test_fifo_vs_weighted_average_rising_prices(self):
        self.receipts()
        self.l.stock(self.p,self.i,0,8,0,0,'0','3')
        totals=self.l.report(self.p)[1]
        self.assertEqual((totals['Cost of goods sold'],totals['Closing inventory at cost']),('14.00','16.00'))
        self.l.stock(self.p,self.i,0,8,0,0,'0','3',cost_method='Weighted average')
        totals=self.l.report(self.p)[1]
        self.assertEqual((totals['Cost of goods sold'],totals['Closing inventory at cost']),('18.00','12.00'))
    def test_fifo_falling_prices(self):
        self.receipts('20','10');self.l.stock(self.p,self.i,0,8,0,0,'0','3')
        totals=self.l.report(self.p)[1]
        self.assertEqual((totals['Cost of goods sold'],totals['Closing inventory at cost']),('22.00','8.00'))
    def test_fifo_layers_survive_carry_forward(self):
        self.receipts();self.l.stock(self.p,self.i,0,8,0,0,'0','3')
        nxt=self.l.period('2026-10-09','2026-10-10');self.l.carry_forward(nxt)
        self.l.receipt(nxt,self.i,'2026-10-09','S','Third',4,'12','0')
        # Update the inherited count but keep its opening quantity/cost.
        row=self.l.db.execute('SELECT * FROM stock WHERE period=?',(nxt,)).fetchone()
        self.l.stock(nxt,self.i,row['opening'],2,0,0,str(row['opening_cost']/100),'4')
        totals=self.l.report(nxt)[1]
        self.assertEqual((totals['Cost of goods sold'],totals['Closing inventory at cost']),('22.00','6.00'))
        self.assertTrue(self.l.inventory_valuation(nxt,self.i)['carried'])
    def test_non_sale_allocation_conserves_value_and_warns(self):
        self.l.receipt(self.p,self.i,'2026-10-01','','',4,'8','0')
        self.l.stock(self.p,self.i,4,3,1,1,'1','3')
        valuation=self.l.inventory_valuation(self.p,self.i)
        self.assertEqual([valuation[k] for k in ['cogs','drawings','breakage','closing_value']],[Decimal(300),Decimal(100),Decimal(200),Decimal(600)])
        self.assertEqual(sum(valuation[k] for k in ['cogs','drawings','breakage','closing_value']),valuation['available_value'])
        self.assertTrue(any('sales first' in text for text in self.l.checks(self.p)))
    def test_default_changes_do_not_revalue_saved_periods(self):
        self.receipts();self.l.stock(self.p,self.i,0,8,0,0,'0','3',cost_method='Weighted average')
        self.l.set_product_cost_method(self.i,'FIFO')
        self.assertEqual(self.l.period_cost_method(self.p,self.i),'Weighted average')
        self.assertEqual(self.l.report(self.p)[1]['Cost of goods sold'],'18.00')
    def test_fractional_delivery_cost_carries_without_cent_rounding_loss(self):
        self.l.receipt(self.p,self.i,'2026-10-01','','',3,'1','0')
        self.l.stock(self.p,self.i,0,2,0,0,'0','1',cost_method='Weighted average')
        nxt=self.l.period('2026-10-09','2026-10-10');self.l.carry_forward(nxt)
        self.assertEqual(self.l.report(nxt)[1]['Closing inventory at cost'],'0.67')
        row=self.l.db.execute('SELECT * FROM stock WHERE period=?',(nxt,)).fetchone()
        self.l.stock(nxt,self.i,2,0,0,0,str(row['opening_cost']/100),'1')
        self.assertEqual(self.l.report(nxt)[1]['Cost of goods sold'],'0.67')
        preview=self.l.stock_preview(nxt,self.i,2,0,0,0,str(row['opening_cost']/100),'1')
        self.assertAlmostEqual(preview['cogs'],Decimal(2)/3)

if __name__=='__main__':unittest.main()
