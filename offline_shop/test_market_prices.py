import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from ledger import Ledger,MarketSearch,price_query,snippet_price,public_price_url


class MarketTests(unittest.TestCase):
    def row(self,**changes):
        row={'title':'Sugar 2kg special','source':'https://nrichards.co.zw/promotions/','excerpt':'Sugar 2kg US$2.10. Check the branch.','published':'','amount':210,'currency':'USD','retailer':'N. Richards','pack':'Unknown','units':None,'reviewed':False}
        row.update(changes);return row

    def test_optional_quantities_and_product_sizes(self):
        self.assertEqual(price_query(' 2 crates of Castle Quart '),'Castle Quart')
        self.assertEqual(price_query('Castle Quart 2 crates'),'Castle Quart')
        self.assertEqual(price_query('10 units sugar 2kg'),'sugar 2kg')
        self.assertEqual(price_query('7up 500ml'),'7up 500ml')
        for text in ('','12',' '*10,'a'*181):
            with self.assertRaises(ValueError):price_query(text)

    def test_currency_and_ambiguous_prices(self):
        self.assertEqual(snippet_price('Sugar USD 2.10 per pack'),(210,'USD'))
        self.assertEqual(snippet_price('US$1,200.50'),(120050,'USD'))
        self.assertEqual(snippet_price('ZiG 35.50'),(3550,'ZWG'))
        self.assertEqual(snippet_price('R25.99'),(2599,'ZAR'))
        self.assertEqual(snippet_price('$2.50'),(250,'Unknown ($)'))
        self.assertEqual(snippet_price('Sugar US$2.10 and rice US$1.90'),(None,'Unknown'))
        self.assertEqual(snippet_price('Call 0772123456; 12 x 2kg, 2026'),(None,'Unknown'))
        self.assertEqual(snippet_price('Was $3.00, now $2.00'),(None,'Unknown'))

    def test_filters_wrong_product_retailer_and_unsafe_urls(self):
        payload={'organic':[
            {'title':'Sugar 2kg N Richards','snippet':'US$2.10','link':'https://nrichards.co.zw/promotions/'},
            {'title':'Salt 2kg N Richards','snippet':'US$1.10','link':'https://nrichards.co.zw/salt/'},
            {'title':'Sugar 2kg foreign store','snippet':'US$1.00','link':'https://example.com/sugar/'},
            {'title':'Sugar 2kg Gain Cash','snippet':'US$2.30','link':'https://www.facebook.com/gaincashandcarry/posts/123'},
            {'title':'Sugar 2kg N Richards','snippet':'US$2.00','link':'javascript:alert(1)'},
            {'title':'Sugar 2kg N Richards','snippet':'US$2.10','link':'https://nrichards.co.zw/promotions/'},
            None]}
        rows=MarketSearch.parse(payload,'2 cases of Sugar 2kg','All retailers')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['amount'],210)
        self.assertFalse(rows[0]['reviewed']);self.assertEqual(rows[0]['published'],'')
        self.assertEqual(rows[0]['pack'],'Unknown');self.assertIsNone(rows[0]['units'])
        self.assertEqual(len(MarketSearch.parse(payload,'Sugar 2kg','Gain Cash & Carry')),1)
        self.assertEqual(MarketSearch.parse({'organic':[{'title':'Sugar price N Richards','snippet':'US$2.10','link':'https://nrichards.co.zw/'}]},'rice','All retailers'),[])

    def test_links_are_public_and_web_only(self):
        self.assertEqual(public_price_url('https://nrichards.co.zw/promotions/'),'https://nrichards.co.zw/promotions/')
        for url in ('file:///x','javascript:alert(1)','https://localhost/a','http://127.0.0.1/a','http://10.0.0.1/a','https://x:y@example.com','https://x.local','https://exam ple.com'):
            with self.assertRaises(ValueError,msg=url):public_price_url(url)

    def test_offline_cache_persists_in_backup_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'shop.sqlite3';backup=Path(folder)/'backup.sqlite3'
            ledger=Ledger(path)
            ledger.save_market_search('10 units sugar 2kg','N. Richards',[self.row()])
            ledger.save_market_search('sugar 2kg','N. Richards',[self.row(amount=225,published='2026-10-20')])
            ledger.backup(backup);ledger.db.close()
            for database in (path,backup):
                ledger=Ledger(database)
                rows=ledger.market_history('Sugar 2kg')
                self.assertEqual([r['amount'] for r in rows],[225,210])
                self.assertTrue(rows[0]['searched_at']);self.assertEqual(rows[1]['published'],'')
                self.assertEqual(ledger.market_history('rice'),[])
                ledger.db.close()

    def test_other_shop_is_separate_and_references_do_not_change_accounts(self):
        first=Ledger(':memory:');second=Ledger(':memory:')
        self.addCleanup(first.db.close);self.addCleanup(second.db.close)
        p=first.period('2026-10-22','2026-10-22');i=first.product('Sugar','packet')
        first.stock(p,i,10,5,0,0,'1.50','2.00');first.cash(p,'2026-10-22','10','0','0','0','0','')
        report=first.report(p);audit=first.db.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]
        first.save_market_search('Sugar 2kg','N. Richards',[self.row(amount=9000)])
        self.assertEqual(first.report(p),report)
        self.assertEqual(first.db.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0],audit)
        self.assertEqual(second.market_history(),[])

    def test_bad_quote_rolls_back_whole_search(self):
        ledger=Ledger(':memory:');self.addCleanup(ledger.db.close)
        for bad in (self.row(amount=-1),self.row(units=0),self.row(currency='BTC'),self.row(reviewed=True),self.row(source='file:///x')):
            with self.assertRaises(ValueError):ledger.save_market_search('Sugar','N. Richards',[self.row(),bad])
            self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM market_searches').fetchone()[0],0)
        ledger.save_market_search('Sugar','N. Richards',[self.row(reviewed=True,pack='case 10 x 2kg',units=10)])
        self.assertEqual(ledger.market_history()[0]['units'],10)

    def test_request_and_key_stay_out_of_url(self):
        response=io.BytesIO(json.dumps({'organic':[{'title':'Sugar 2kg N Richards','snippet':'US$2.10','link':'https://nrichards.co.zw/'}]}).encode())
        with patch('urllib.request.urlopen',return_value=response) as call:
            rows=MarketSearch.search('Sugar 2kg','N. Richards','test-key')
        request=call.call_args.args[0]
        self.assertEqual(request.full_url,'https://google.serper.dev/search')
        self.assertNotIn('test-key',request.full_url)
        self.assertEqual(request.get_header('X-api-key'),'test-key')
        self.assertEqual(json.loads(request.data)['gl'],'zw')
        self.assertEqual(len(rows),1)
        self.assertIn('google.com/search?',MarketSearch.google_url('Sugar 2kg','N. Richards'))

    def test_errors_do_not_need_network_and_explain_offline_fallback(self):
        with self.assertRaisesRegex(ValueError,'Connect a Serper'):MarketSearch.search('Sugar','N. Richards','')
        with patch('urllib.request.urlopen',side_effect=URLError('No connection')):
            with self.assertRaisesRegex(ValueError,'offline'):MarketSearch.search('Sugar','N. Richards','key')
        for code in (401,403,429,500):
            with patch('urllib.request.urlopen',side_effect=HTTPError(MarketSearch.ENDPOINT,code,'Fail',{},None)):
                with self.assertRaises(ValueError):MarketSearch.search('Sugar','N. Richards','key')

    def test_empty_results_do_not_erase_previous_prices(self):
        ledger=Ledger(':memory:');self.addCleanup(ledger.db.close)
        ledger.save_market_search('Sugar','N. Richards',[self.row()])
        ledger.save_market_search('Sugar','N. Richards',[])
        self.assertEqual(len(ledger.market_history('Sugar')),1)


if __name__=='__main__':unittest.main()
