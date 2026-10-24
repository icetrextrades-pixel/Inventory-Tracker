import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from ledger import Ledger,stock_indicator,closing_indicator
from app import SHOP_COLOURS,SHOPS,visual_palette


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger(':memory:');self.addCleanup(self.ledger.db.close)
        self.product=self.ledger.product('Castle Quart','bottle','Crate',12,'FIFO')

    def period(self,start,end,opening=12,closing=6):
        p=self.ledger.period(start,end);self.ledger.stock(p,self.product,opening,closing,0,0,'1','2')
        return p

    def test_targets_have_explicit_boundaries_and_unknown_is_not_healthy(self):
        self.assertEqual(stock_indicator(None,5,20),('Not counted','neutral',0))
        self.assertEqual(stock_indicator(12)[1],'neutral')
        self.assertEqual(stock_indicator(5,5,20)[:2],('Low stock','warning'))
        self.assertEqual(stock_indicator(6,5,20)[1],'good')
        self.assertEqual(stock_indicator(20,5,20)[1],'good')
        self.assertEqual(stock_indicator(21,5,20)[:2],('Above target','warning'))
        self.assertEqual(stock_indicator(0,0,10)[1],'warning')

    def test_appearance_changes_never_change_accounting_or_cost_layers(self):
        p=self.period('2026-10-01','2026-10-01');before=self.ledger.report(p)
        self.ledger.product_appearance(self.product,'Beer','5','24')
        row=self.ledger.visual_stock(p)[0]
        self.assertEqual((row['category'],row['low'],row['high'],row['closing']),('Beer',5,24,6))
        self.assertEqual(self.ledger.report(p),before)
        self.ledger.set_lock(p,True,'Approved')
        self.ledger.product_appearance(self.product,'Beer','','')
        self.assertEqual(self.ledger.report(p),before)
        self.assertIsNone(self.ledger.visual_stock(p)[0]['low'])

    def test_invalid_limits_and_large_photo_rejected_before_changes(self):
        for low,high in [('5','4'),('5','5'),('-1','10'),('1.5','10'),('','10')]:
            with self.assertRaises(ValueError):self.ledger.product_appearance(self.product,'Beer',low,high)
        with self.assertRaises(ValueError):self.ledger.product_appearance(self.product,'Unknown','','')
        with self.assertRaises(ValueError):self.ledger.product_appearance(self.product,'Beer','','',b'\x89PNG\r\n\x1a\n'+b'x'*(256*1024))
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM product_visuals').fetchone()[0],0)

    def test_photos_and_settings_survive_backup(self):
        # Actual decoding is covered by the virtual-display smoke check.
        png=b'\x89PNG\r\n\x1a\nsmall-fixture'
        self.ledger.product_appearance(self.product,'Beer','2','20',png)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'backup.sqlite3';self.ledger.backup(target)
            restored=Ledger(target)
            try:self.assertEqual(restored.visual_stock()[0]['photo'],png)
            finally:restored.db.close()
        self.ledger.product_appearance(self.product,'Beer','2','20',None)
        self.assertIsNone(self.ledger.visual_stock()[0]['photo'])

    def test_daily_chart_does_not_split_weekly_stock_totals(self):
        self.period('2026-10-01','2026-10-01')
        self.period('2026-10-05','2026-10-11')
        daily,excluded=self.ledger.chart_series('Daily')
        self.assertEqual(len(daily),1);self.assertEqual(excluded,1)
        self.assertEqual(daily[0]['sales'],Decimal('12.00'))
        weekly,excluded=self.ledger.chart_series('Weekly')
        self.assertEqual(len(weekly),2);self.assertEqual(excluded,0)
        monthly,excluded=self.ledger.chart_series('Monthly')
        self.assertEqual(len(monthly),1);self.assertEqual(monthly[0]['sales'],Decimal('24.00'))
        self.assertEqual(monthly[0]['periods'],2)

    def test_week_and_month_boundaries_are_not_double_counted(self):
        self.period('2026-10-30','2026-11-03')
        self.assertEqual(self.ledger.chart_series('Daily'),([],1))
        self.assertEqual(self.ledger.chart_series('Weekly'),([],1))
        self.assertEqual(self.ledger.chart_series('Monthly'),([],1))

    def test_chart_keeps_negative_profit_and_excludes_empty_periods(self):
        p=self.period('2026-10-01','2026-10-01')
        self.ledger.cash(p,'2026-10-01','12','0','0','0','20','')
        self.ledger.period('2026-10-02','2026-10-02')
        data,excluded=self.ledger.chart_series('Daily')
        self.assertEqual(data[0]['profit'],Decimal('-14.00'));self.assertEqual(excluded,1)
        with self.assertRaises(ValueError):self.ledger.chart_series('Yearly')

    def test_closing_badges_do_not_call_an_empty_period_balanced(self):
        for value,expected in [('0.00','good'),('1.00','warning'),('-1.00','warning')]:
            totals={'Unreconciled difference (positive = short)':value}
            self.assertEqual(closing_indicator(totals,True)[1],expected)
            self.assertEqual(closing_indicator(totals,False)[1],'neutral')

    def test_shops_have_different_colours_and_dark_palette_has_contrast(self):
        self.assertEqual(set(SHOP_COLOURS),set(SHOPS))
        self.assertEqual(len({r[0] for r in SHOP_COLOURS.values()}),3)
        for dark in (False,True):
            p=visual_palette(dark)
            def luminance(color):
                rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
                rgb=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
                return sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))
            for background in ('bg','panel'):
                for foreground in ('text','muted','good','warning'):
                    a,b=sorted((luminance(p[background]),luminance(p[foreground])))
                    self.assertGreaterEqual((b+.05)/(a+.05),4.5,(dark,background,foreground))


if __name__=='__main__':unittest.main()
