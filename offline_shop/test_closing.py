import sqlite3
import unittest
from ledger import Ledger


class ClosingTests(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger(':memory:')
        self.addCleanup(self.ledger.db.close)
        self.p=self.ledger.period('2026-10-20','2026-10-21')
        self.i=self.ledger.product('Castle Quart','bottle','Crate',12,'FIFO')
        self.j=self.ledger.product('Sugar','packet')
        self.ledger.stock(self.p,self.i,12,12,0,0,'1','2')
        self.ledger.stock(self.p,self.j,10,10,0,0,'.50','1')
        self.ledger.receipt(self.p,self.i,'2026-10-20','Supplier','A',12,'18','0')
        self.stocks,self.days=self.ledger.closing_draft(self.p)
        for row in self.stocks:row['confirmed']=True
        for row in self.days:row['confirmed']=True
        self.stocks[0].update(closing='10',drawings='1',broken='1')  # 12 sold = $24
        self.stocks[1].update(closing='8')  # 2 sold = $2
        self.days[0].update(cash='16',ecocash='5',cashout='2',expense='2')
        self.days[1].update(cash='3')

    def test_preview_is_read_only_even_audit_log(self):
        before=list(self.ledger.db.iterdump())
        rows,totals,warnings=self.ledger.preview_closing(self.p,self.stocks,self.days)
        self.assertEqual(totals['Stock-implied sales'],'26.00')
        self.assertEqual(totals['Unreconciled difference (positive = short)'],'0.00')
        self.assertEqual(totals['Net profit before tax (stock-implied)'],'9.50')
        self.assertEqual(list(self.ledger.db.iterdump()),before)
        self.assertTrue(any('FIFO uses period totals' in w for w in warnings))

    def test_save_replaces_existing_cash_without_double_count_and_logs_owner(self):
        self.ledger.cash(self.p,'2026-10-20','99','0','0','0','0','Old')
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')
        first=self.ledger.report(self.p)
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')
        self.assertEqual(first,self.ledger.report(self.p))
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM cash').fetchone()[0],2)
        row=self.ledger.db.execute("SELECT * FROM audit_log WHERE reason='Guided closing reviewed and saved' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row['actor'],'Owner')
        self.assertEqual(self.ledger.db.execute('SELECT reason FROM change_context').fetchone()[0],'Record saved')

    def test_invalid_later_money_rolls_back_all_stock_cash_and_audit(self):
        self.days[1]['cash']='-1'
        before=list(self.ledger.db.iterdump())
        for operation in (self.ledger.preview_closing,lambda *a:self.ledger.save_closing(*a,'Owner',True)):
            with self.assertRaises(ValueError):operation(self.p,self.stocks,self.days)
            self.assertEqual(list(self.ledger.db.iterdump()),before)

    def test_count_confirmation_and_complete_dates_are_required(self):
        for stocks,days in [(self.stocks[:-1],self.days),(self.stocks,self.days[:-1]),([self.stocks[0]]*2,self.days),(self.stocks,[self.days[0]]*2)]:
            with self.assertRaises(ValueError):self.ledger.preview_closing(self.p,stocks,days)
        self.stocks[0]['confirmed']=False
        with self.assertRaisesRegex(ValueError,'physical count'):self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')
        self.stocks[0]['confirmed']=True;self.days[1]['confirmed']=False
        with self.assertRaisesRegex(ValueError,'money entries'):self.ledger.preview_closing(self.p,self.stocks,self.days)

    def test_lock_blocks_later_edits_and_reopen_allows_correction(self):
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner',lock=True)
        self.assertTrue(self.ledger.period_locked(self.p))
        with self.assertRaises(ValueError):self.ledger.closing_draft(self.p)
        with self.assertRaises(sqlite3.IntegrityError):self.ledger.cash(self.p,'2026-10-20','0','0','0','0','0','')
        self.ledger.set_lock(self.p,False,'Correct a counted quantity')
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')

    def test_shortage_surplus_and_exact_sales(self):
        self.stocks[0]['sales_total']='24.50'
        totals=self.ledger.preview_closing(self.p,self.stocks,self.days)[1]
        self.assertEqual(totals['Unreconciled difference (positive = short)'],'0.50')
        self.days[1]['cash']='5'
        totals=self.ledger.preview_closing(self.p,self.stocks,self.days)[1]
        self.assertEqual(totals['Unreconciled difference (positive = short)'],'-1.50')
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')
        draft,_=self.ledger.closing_draft(self.p)
        self.assertEqual(draft[0]['sales_total'],'24.50')
        self.assertFalse(draft[0]['confirmed'])

    def test_carried_fifo_layers_preserved(self):
        self.ledger.save_closing(self.p,self.stocks,self.days,'Owner')
        new=self.ledger.period('2026-10-22','2026-10-22');self.ledger.carry_forward(new)
        layers=[tuple(r) for r in self.ledger.db.execute('SELECT * FROM opening_layers WHERE period=?',(new,))]
        stocks,days=self.ledger.closing_draft(new)
        for row in stocks:row['confirmed']=True
        for row in days:row['confirmed']=True
        stocks[0]['closing']='8';days[0]['cash']='4'
        expected=self.ledger.preview_closing(new,stocks,days)[1]
        self.ledger.save_closing(new,stocks,days,'Owner')
        self.assertEqual(expected,self.ledger.report(new)[1])
        self.assertEqual(layers,[tuple(r) for r in self.ledger.db.execute('SELECT * FROM opening_layers WHERE period=?',(new,))])

    def test_no_credit_purchases_and_old_debts_not_counted(self):
        debt=self.ledger.debt('Customer',self.p,'2026-10-20','2','')
        self.ledger.repay(debt,'2026-10-21','1','Cash')
        self.days[0].update(cash='14',credit='2')
        totals=self.ledger.preview_closing(self.p,self.stocks,self.days)[1]
        self.assertEqual(totals['Total accounted for'],'26.00')
        self.assertEqual(totals['Unreconciled difference (positive = short)'],'0.00')


if __name__=='__main__':unittest.main()
