import unittest
from ledger import Ledger
from app import printable

class ReportsTests(unittest.TestCase):
    def test_escaped_printout_cost_and_credit_checks(self):
        ledger=Ledger(':memory:')
        p=ledger.period('2026-10-01','2026-10-08')
        product=ledger.product('<script>alert(1)</script>','each')
        ledger.stock(p,product,10,2,0,0,'0','1')
        ledger.debt('<img src=x>',p,'2026-10-01','2','')
        text=printable(ledger,p)
        self.assertNotIn('<script>alert(1)</script>',text)
        self.assertIn('&lt;script&gt;',text)
        self.assertIn('&lt;img src=x&gt;',text)
        self.assertIn('Missing opening cost',text)
        self.assertIn('Credit register differs',text)
        self.assertIn('Signature:',text)
        ledger.db.close()
    def test_balances_and_matched_credit(self):
        ledger=Ledger(':memory:');p=ledger.period('2026-10-01','2026-10-08')
        i=ledger.product('Bread','loaf');ledger.stock(p,i,10,2,0,0,'.50','1')
        d=ledger.debt('A',p,'2026-10-01','2','');ledger.repay(d,'2026-10-02','1','Cash')
        ledger.cash(p,'2026-10-01','6','0','2','0','0','')
        self.assertEqual(ledger.checks(p),[])
        r=ledger.customer_balances()[0]
        self.assertEqual((r['credit'],r['paid']),(200,100))
        ledger.db.close()

if __name__=='__main__':unittest.main()
