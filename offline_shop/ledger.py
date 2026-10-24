"""Offline shop records. Monetary inputs use decimal strings, stored as cents."""
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, timedelta
from contextlib import nullcontext


def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise ValueError('Enter a non-negative amount.')
        return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError('Enter a valid amount.') from None


def quantity(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0 or n != int(n):
        raise ValueError('Units must be whole, non-negative numbers.')
    return int(n)


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, unit TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS periods(id INTEGER PRIMARY KEY, start TEXT NOT NULL, end TEXT NOT NULL, UNIQUE(start,end));
        CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), product INTEGER REFERENCES products(id), opening INTEGER, closing INTEGER, drawings INTEGER, broken INTEGER, opening_cost INTEGER, price INTEGER, UNIQUE(period,product));
        CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), product INTEGER REFERENCES products(id), day TEXT, supplier TEXT, reference TEXT, units INTEGER, goods INTEGER, freight INTEGER);
        CREATE TABLE IF NOT EXISTS cash(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), day TEXT, cash INTEGER, ecocash INTEGER, credit INTEGER, cashout INTEGER, expense INTEGER, note TEXT, UNIQUE(period,day));
        ''')

        self.upgrade()
        self.install_controls()

    def product(self, name, unit, package="Individual", per_package=1, cost_method="Weighted average"):
        if not name.strip() or not unit.strip():
            raise ValueError('Product name and unit are required.')
        per_package=validate_package(package,per_package)
        validate_cost_method(cost_method)
        with self.db:
            pid=self.db.execute('INSERT INTO products(name,unit) VALUES (?,?)', (name.strip(), unit.strip())).lastrowid
            self.db.execute('INSERT INTO product_packages(product,package,per_package) VALUES (?,?,?)',(pid,package,per_package))
            self.db.execute('INSERT INTO product_costing(product,method) VALUES (?,?)',(pid,cost_method))
            return pid

    def product_appearance(self, product, category, low, high, photo=None):
        if category not in PRODUCT_CATEGORIES:raise ValueError('Choose a product category.')
        low=quantity(low) if str(low).strip() else None
        high=quantity(high) if str(high).strip() else None
        if (low is None)!=(high is None) or (low is not None and high<=low):raise ValueError('Set both stock limits, with high greater than low, or leave both blank.')
        if photo is not None and (not isinstance(photo,bytes) or len(photo)>256*1024 or not photo.startswith(b'\x89PNG\r\n\x1a\n')):raise ValueError('Choose a small PNG product picture (up to 256 KB after resizing).')
        if not self.db.execute('SELECT 1 FROM products WHERE id=?',(product,)).fetchone():raise ValueError('Product not found.')
        with self.db:
            self.db.execute('''INSERT INTO product_visuals(product,category,low,high,photo) VALUES (?,?,?,?,?)
                ON CONFLICT(product) DO UPDATE SET category=excluded.category,low=excluded.low,high=excluded.high,photo=excluded.photo''',(product,category,low,high,photo))

    def visual_stock(self, period=None):
        return [dict(row) for row in self.db.execute('''SELECT p.id,p.name,p.unit,COALESCE(v.category,'Other') AS category,v.low,v.high,v.photo,
            s.closing,s.opening,COALESCE((SELECT SUM(r.units) FROM receipts r WHERE r.product=p.id AND r.period=?),0) AS received
            FROM products p LEFT JOIN product_visuals v ON v.product=p.id
            LEFT JOIN stock s ON s.product=p.id AND s.period=? ORDER BY p.name''',(period,period))]

    def chart_series(self, mode):
        """Aggregate only periods wholly inside a bucket. Never invent daily sales."""
        if mode not in ('Daily','Weekly','Monthly'):raise ValueError('Choose Daily, Weekly or Monthly.')
        buckets={};excluded=0
        for period in self.db.execute('SELECT * FROM periods ORDER BY start'):
            start=date.fromisoformat(period['start']);end=date.fromisoformat(period['end'])
            if mode=='Daily':fits=start==end;key=start.isoformat();label=start.strftime('%d %b')
            elif mode=='Weekly':
                fits=start.isocalendar()[:2]==end.isocalendar()[:2];year,week,_=start.isocalendar();key=f'{year}-W{week:02d}';label=f'W{week:02d} {year}'
            else:fits=(start.year,start.month)==(end.year,end.month);key=start.strftime('%Y-%m');label=start.strftime('%b %Y')
            if not fits:excluded+=1;continue
            try:rows,totals=self.report(period['id'])
            except ValueError:excluded+=1;continue
            if not rows:excluded+=1;continue
            bucket=buckets.setdefault(key,{'key':key,'label':label,'sales':Decimal(0),'profit':Decimal(0),'periods':0})
            bucket['sales']+=Decimal(totals['Stock-implied sales']);bucket['profit']+=Decimal(totals['Net profit before tax (stock-implied)']);bucket['periods']+=1
        return [buckets[k] for k in sorted(buckets)[-10:]],excluded

    def period(self, start, end):
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        if a > b:
            raise ValueError('End date must follow start date.')
        if self.db.execute('SELECT 1 FROM periods WHERE start<=? AND end>=?', (end, start)).fetchone():
            raise ValueError('This period overlaps an existing period. Select the existing period or use different dates.')
        with self.db:
            return self.db.execute('INSERT INTO periods(start,end) VALUES (?,?)', (start, end)).lastrowid

    def check_day(self, period, day):
        date.fromisoformat(day)
        p = self.db.execute('SELECT * FROM periods WHERE id=?', (period,)).fetchone()
        if not p or not p['start'] <= day <= p['end']:
            raise ValueError('Date must fall inside the selected period.')

    def stock(self, period, product, opening, closing, drawings, broken, opening_cost, price, sales_total=None, cost_method=None, *, commit=True):
        vals = [quantity(x) for x in (opening, closing, drawings, broken)]
        received = self.db.execute('SELECT COALESCE(SUM(units),0) FROM receipts WHERE period=? AND product=?', (period,product)).fetchone()[0]
        if vals[1]+vals[2]+vals[3] > vals[0]+received:
            raise ValueError('Closing stock, drawings and breakages exceed available units. Enter receipts first.')
        method=cost_method or self.period_cost_method(period,product)
        validate_cost_method(method)
        old=self.db.execute('SELECT opening,opening_cost FROM stock WHERE period=? AND product=?',(period,product)).fetchone()
        sold=vals[0]+received-vals[1]-vals[2]-vals[3]
        total=money(sales_total) if sales_total is not None else None
        if total is not None:
            if not sold and total:raise ValueError('Total sales must be zero when no units were sold.')
            price_cents=int((Decimal(total)/sold).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if sold else 0
        else:price_cents=money(price)
        with self.db if commit else nullcontext():
            self.db.execute('INSERT INTO stock(period,product,opening,closing,drawings,broken,opening_cost,price) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(period,product) DO UPDATE SET opening=excluded.opening,closing=excluded.closing,drawings=excluded.drawings,broken=excluded.broken,opening_cost=excluded.opening_cost,price=excluded.price', (period,product,*vals,money(opening_cost),price_cents))
            if old and (old['opening']!=vals[0] or old['opening_cost']!=money(opening_cost)):
                self.db.execute('DELETE FROM opening_layers WHERE period=? AND product=?',(period,product))
            self.db.execute('INSERT INTO stock_costing(period,product,method) VALUES (?,?,?) ON CONFLICT(period,product) DO UPDATE SET method=excluded.method',(period,product,method))
            self.db.execute('DELETE FROM stock_sales WHERE period=? AND product=?',(period,product))
            if total is not None:self.db.execute('INSERT INTO stock_sales(period,product,amount) VALUES (?,?,?)',(period,product,total))

    def receipt(self, period, product, day, supplier, reference, units, goods, freight):
        self.check_day(period, day)
        units = quantity(units)
        if units == 0:
            raise ValueError('Received units must be greater than zero.')
        with self.db:
            self.db.execute('INSERT INTO receipts(period,product,day,supplier,reference,units,goods,freight) VALUES (?,?,?,?,?,?,?,?)', (period,product,day,supplier,reference,units,money(goods),money(freight)))

    def cash(self, period, day, cash, ecocash, credit, cashout, expense, note, *, commit=True):
        self.check_day(period,day)
        values = [money(x) for x in (cash,ecocash,credit,cashout,expense)]
        with self.db if commit else nullcontext():
            self.db.execute('INSERT INTO cash(period,day,cash,ecocash,credit,cashout,expense,note) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(period,day) DO UPDATE SET cash=excluded.cash,ecocash=excluded.ecocash,credit=excluded.credit,cashout=excluded.cashout,expense=excluded.expense,note=excluded.note', (period,day,*values,note))

    def closing_draft(self, period):
        """Build an editable guide from saved records; no implicit stock movements."""
        p=self.db.execute('SELECT * FROM periods WHERE id=?',(period,)).fetchone()
        if not p:raise ValueError('Select a reporting period first.')
        if self.period_locked(period):raise ValueError('Reopen this period in History & controls before editing its closing.')
        stocks=[]
        for product in self.db.execute('SELECT * FROM products ORDER BY name'):
            item=product['id']
            saved=self.db.execute('SELECT * FROM stock WHERE period=? AND product=?',(period,item)).fetchone()
            total=self.db.execute('SELECT amount FROM stock_sales WHERE period=? AND product=?',(period,item)).fetchone()
            received=self.db.execute('SELECT COALESCE(SUM(units),0) FROM receipts WHERE period=? AND product=?',(period,item)).fetchone()[0]
            stocks.append({'product':item,'name':product['name'],'unit':product['unit'],'received':received,
                **{key:str(saved[key]) if saved else '0' for key in ('opening','closing','drawings','broken')},
                **{key:f"{saved[key]/100:.2f}" if saved else '0' for key in ('opening_cost','price')},
                'sales_total':f"{total['amount']/100:.2f}" if total else '',
                'confirmed':False})
        days=[];day=date.fromisoformat(p['start']);end=date.fromisoformat(p['end'])
        while day<=end:
            text=day.isoformat();saved=self.db.execute('SELECT * FROM cash WHERE period=? AND day=?',(period,text)).fetchone()
            days.append({'day':text,**{key:f"{saved[key]/100:.2f}" if saved else '0' for key in ('cash','ecocash','credit','cashout','expense')},
                         'note':saved['note'] if saved else '', 'confirmed':False})
            day+=timedelta(days=1)
        return stocks,days

    def save_market_search(self, query, retailer, results):
        """Append a dated reference snapshot; never writes purchase/stock values."""
        query=price_query(query)
        if retailer not in PRICE_RETAILERS:raise ValueError('Choose a retailer.')
        with self.db:
            search=self.db.execute('INSERT INTO market_searches(query,retailer) VALUES (?,?)',(query,retailer)).lastrowid
            for row in results[:30]:
                source=public_price_url(row['source'])
                amount=row.get('amount')
                if amount is not None and (type(amount) is not int or amount<=0):raise ValueError('Invalid reference price.')
                if row.get('currency','Unknown') not in ('USD','ZWG','ZAR','Unknown','Unknown ($)'):raise ValueError('Invalid reference currency.')
                units=row.get('units')
                if units is not None and (type(units) is not int or units<=0):raise ValueError('Pack units must be a positive whole number, or unknown.')
                if row.get('reviewed') and (amount is None or row.get('currency') not in ('USD','ZWG','ZAR') or not row.get('pack','').strip() or row.get('pack')=='Unknown'):
                    raise ValueError('Checked references require a price, currency and package description.')
                self.db.execute('''INSERT INTO market_prices(search,retailer,title,source,excerpt,published,amount,currency,pack,units,reviewed,note)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(search,row.get('retailer',retailer)[:100],row['title'][:300],source,row.get('excerpt','')[:1500],row.get('published','')[:80],amount,row.get('currency','Unknown'),row.get('pack','Unknown')[:100],row.get('units'),int(bool(row.get('reviewed'))),row.get('note','')[:1000]))
        return search

    def market_history(self, query='', retailer='All retailers'):
        import re
        tokens=re.findall(r'\w+',price_query(query,required=False).casefold())
        rows=self.db.execute('''SELECT m.*,s.query,s.searched_at FROM market_prices m JOIN market_searches s ON s.id=m.search
            ORDER BY m.id DESC''')
        result=[]
        for row in rows:
            if retailer!='All retailers' and row['retailer']!=retailer:continue
            haystack=(row['query']+' '+row['title']).casefold()
            if all(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',haystack) for t in tokens):result.append(dict(row))
            if len(result)==300:break
        return result

    def _apply_closing(self, period, stocks, days):
        if self.period_locked(period):raise ValueError('This reporting period is locked.')
        expected_stocks,expected_days=self.closing_draft(period)
        if not stocks:raise ValueError('Add at least one product before closing.')
        if len(stocks)!=len(expected_stocks) or {r['product'] for r in stocks}!={r['product'] for r in expected_stocks}:
            raise ValueError('Review every product exactly once before saving.')
        if len(days)!=len(expected_days) or {r['day'] for r in days}!={r['day'] for r in expected_days}:
            raise ValueError('Review every date in the period exactly once.')
        for row in stocks:
            if not row.get('confirmed'):raise ValueError('Confirm the physical count for every product, including zero stock.')
            self.stock(period,row['product'],*(row[k] for k in ('opening','closing','drawings','broken','opening_cost','price')),
                       sales_total=row.get('sales_total') or None,commit=False)
        for row in days:
            if not row.get('confirmed'):raise ValueError('Confirm the money entries for every date, including days with no sales.')
            self.cash(period,*(row[k] for k in ('day','cash','ecocash','credit','cashout','expense','note')),commit=False)
        return self.report(period)

    def preview_closing(self, period, stocks, days):
        """Use the real accounting engine, rolling back all writes and audit events."""
        self.db.execute('SAVEPOINT guided_closing')
        try:
            rows,totals=self._apply_closing(period,stocks,days)
            return rows,totals,self.checks(period)
        finally:
            self.db.execute('ROLLBACK TO guided_closing')
            self.db.execute('RELEASE guided_closing')

    def save_closing(self, period, stocks, days, actor, lock=False):
        if not actor.strip():raise ValueError('The owner name is required.')
        # One transaction: a failure cannot leave half a closing saved.
        with self.db:
            old=self.db.execute('SELECT actor,reason FROM change_context WHERE id=1').fetchone()
            self.db.execute('UPDATE change_context SET actor=?,reason=? WHERE id=1',(actor.strip(),'Guided closing reviewed and saved'))
            result=self._apply_closing(period,stocks,days)
            if lock:self.db.execute('INSERT INTO period_locks(period,reason) VALUES (?,?)',(period,'Guided closing approved by '+actor.strip()))
            self.db.execute('UPDATE change_context SET actor=?,reason=? WHERE id=1',tuple(old))
        return result

    def report(self, period):
        rows=[]
        sales=cogs=loss=closing_value=drawings_cost=Decimal(0)
        missing = self.db.execute('SELECT DISTINCT product FROM receipts WHERE period=? EXCEPT SELECT product FROM stock WHERE period=?', (period,period)).fetchall()
        if missing:
            raise ValueError('Complete stock counts for all products received before preparing reports.')
        for s in self.db.execute('SELECT s.*,p.name,p.unit FROM stock s JOIN products p ON p.id=s.product WHERE period=? ORDER BY p.name', (period,)):
            received, cost = self.db.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(goods+freight),0) FROM receipts WHERE period=? AND product=?', (period,s['product'])).fetchone()
            total=s['opening']+received
            sold=total-s['closing']-s['drawings']-s['broken']
            valuation=self.inventory_valuation(period,s['product'],s)

            override=self.db.execute('SELECT amount FROM stock_sales WHERE period=? AND product=?',(period,s['product'])).fetchone()
            amount=override['amount'] if override else sold*s['price']
            if override and not sold and amount:raise ValueError('Sales total exists for a product with zero units sold. Review its stock count.')
            price_label=f"{Decimal(amount)/sold/100:.4f}" if override and sold else f"{s['price']/100:.2f}"
            sales+=amount; cogs+=valuation['cogs']; loss+=valuation['breakage']; closing_value+=valuation['closing_value']; drawings_cost+=valuation['drawings']
            rows.append([s['name'],s['unit'],s['opening'],received,total,s['closing'],s['drawings'],s['broken'],sold,price_label,f'{amount/100:.2f}'])
        cash=self.db.execute('SELECT COALESCE(SUM(cash),0),COALESCE(SUM(ecocash),0),COALESCE(SUM(credit),0),COALESCE(SUM(cashout),0),COALESCE(SUM(expense),0) FROM cash WHERE period=?',(period,)).fetchone()
        accounted=sum(cash[:4])
        totals={'Stock-implied sales':sales,'Cash handed over':cash[0],'EcoCash sales receipts':cash[1],'Unpaid credit sales':cash[2],'Cash paid out from sales':cash[3],'Total accounted for':accounted,'Unreconciled difference (positive = short)':sales-accounted,'Cost of goods sold':cogs,'Gross profit':sales-cogs,'Breakage expense at cost':loss,'Operating expenses':cash[4],'Net profit before tax (stock-implied)':sales-cogs-loss-cash[4],'Closing inventory at cost':closing_value,'Stock drawings at cost (not expense)':drawings_cost}
        return rows,{k:f'{Decimal(v)/100:.2f}' for k,v in totals.items()}

    def backup(self, path):
        with sqlite3.connect(path) as target:
            self.db.backup(target)

    def upgrade(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, product INTEGER REFERENCES products(id), supplier TEXT NOT NULL, reference TEXT NOT NULL, day TEXT NOT NULL, units INTEGER NOT NULL, estimated INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), receipt_id INTEGER UNIQUE REFERENCES receipts(id), units INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS debts(id INTEGER PRIMARY KEY, customer INTEGER REFERENCES customers(id), period INTEGER REFERENCES periods(id), day TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT);
        CREATE TABLE IF NOT EXISTS repayments(id INTEGER PRIMARY KEY, debt INTEGER REFERENCES debts(id), day TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL);
        ''')

    def order(self, product, supplier, reference, day, units, estimated):
        date.fromisoformat(day); units=quantity(units)
        if not supplier.strip() or not reference.strip() or not units:
            raise ValueError('Supplier, order reference and positive units are required.')
        with self.db:
            return self.db.execute('INSERT INTO orders(product,supplier,reference,day,units,estimated) VALUES (?,?,?,?,?,?)',(product,supplier.strip(),reference.strip(),day,units,money(estimated))).lastrowid

    def receive_order(self, order_id, period, day, units, goods, freight):
        self.check_day(period,day); units=quantity(units)
        with self.db:
            order=self.db.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
            if not order:raise ValueError('Order not found.')
            received=self.db.execute('SELECT COALESCE(SUM(units),0) FROM deliveries WHERE order_id=?',(order_id,)).fetchone()[0]
            if not units or units>order['units']-received:raise ValueError('Delivery exceeds outstanding units, or is zero.')
            if day<order['day']:raise ValueError('Delivery date precedes the order date.')
            receipt=self.db.execute('INSERT INTO receipts(period,product,day,supplier,reference,units,goods,freight) VALUES (?,?,?,?,?,?,?,?)',(period,order['product'],day,order['supplier'],order['reference'],units,money(goods),money(freight))).lastrowid
            self.db.execute('INSERT INTO deliveries(order_id,receipt_id,units) VALUES (?,?,?)',(order_id,receipt,units))

    def debt(self, customer, period, day, amount, note):
        self.check_day(period,day); amount=money(amount)
        if not customer.strip() or not amount:raise ValueError('Customer name and positive amount required.')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO customers(name) VALUES (?)',(customer.strip(),))
            cid=self.db.execute('SELECT id FROM customers WHERE name=?',(customer.strip(),)).fetchone()[0]
            return self.db.execute('INSERT INTO debts(customer,period,day,amount,note) VALUES (?,?,?,?,?)',(cid,period,day,amount,note)).lastrowid

    def repay(self, debt, day, amount, method):
        date.fromisoformat(day); amount=money(amount)
        if method not in ('Cash','EcoCash'):raise ValueError('Choose Cash or EcoCash.')
        with self.db:
            d=self.db.execute('SELECT * FROM debts WHERE id=?',(debt,)).fetchone()
            paid=self.db.execute('SELECT COALESCE(SUM(amount),0) FROM repayments WHERE debt=?',(debt,)).fetchone()[0]
            if not d or day<d['day'] or not amount or amount>d['amount']-paid:raise ValueError('Invalid date or repayment exceeds balance.')
            self.db.execute('INSERT INTO repayments(debt,day,amount,method) VALUES (?,?,?,?)',(debt,day,amount,method))

    def carry_forward(self, period):
        current=self.db.execute('SELECT * FROM periods WHERE id=?',(period,)).fetchone()
        previous=self.db.execute('SELECT * FROM periods WHERE end<? ORDER BY end DESC LIMIT 1',(current['start'],)).fetchone()
        if not previous:raise ValueError('There is no earlier reporting period.')
        if self.db.execute('SELECT 1 FROM stock WHERE period=?',(period,)).fetchone():raise ValueError('This period already has stock counts. Carry-forward will not overwrite them.')
        self.report(previous['id'])
        with self.db:
            for s in self.db.execute('SELECT * FROM stock WHERE period=?',(previous['id'],)).fetchall():
                valuation=self.inventory_valuation(previous['id'],s['product'],s)
                avg=valuation['closing_value']/s['closing'] if s['closing'] else Decimal(0)
                unit_cost=int(avg.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                self.db.execute('INSERT INTO stock(period,product,opening,closing,drawings,broken,opening_cost,price) VALUES (?,?,?,?,0,0,?,?)',(period,s['product'],s['closing'],s['closing'],unit_cost,s['price']))
                self.db.execute('INSERT INTO stock_costing(period,product,method) VALUES (?,?,?)',(period,s['product'],valuation['method']))
                for seq,layer in enumerate(valuation['remaining']):
                    self.db.execute('INSERT INTO opening_layers(period,product,sequence,units,unit_cost,source) VALUES (?,?,?,?,?,?)',(period,s['product'],seq,layer['units'],str(layer['unit_cost']),layer['source']))
        return previous['start'],previous['end']

    def customer_balances(self):
        return self.db.execute('''SELECT c.name,
            COALESCE((SELECT SUM(amount) FROM debts WHERE customer=c.id),0) credit,
            COALESCE((SELECT SUM(r.amount) FROM repayments r JOIN debts d ON d.id=r.debt WHERE d.customer=c.id),0) paid
            FROM customers c ORDER BY c.name''').fetchall()

    def checks(self,period):
        warnings=[]
        for r in self.db.execute('SELECT p.name,s.opening,s.opening_cost FROM stock s JOIN products p ON p.id=s.product WHERE period=?',(period,)):
            if r['opening'] and not r['opening_cost']:
                warnings.append(f"Missing opening cost: {r['name']}. Profit may be overstated.")
        for r in self.db.execute('SELECT p.name,r.reference FROM receipts r JOIN products p ON p.id=r.product WHERE period=? AND r.goods=0',(period,)):
            warnings.append(f"Zero purchase cost: {r['name']} ({r['reference']}). Confirm whether goods were free.")
        credit=self.db.execute('SELECT COALESCE(SUM(credit),0) FROM cash WHERE period=?',(period,)).fetchone()[0]
        debts=self.db.execute('SELECT COALESCE(SUM(amount),0) FROM debts WHERE period=?',(period,)).fetchone()[0]
        if credit!=debts:
            warnings.append(f'Credit register differs from daily credit: customer sales ${debts/100:.2f}; daily credit ${credit/100:.2f}. Difference ${(debts-credit)/100:.2f}. Check entries and same-period repayments; no automatic adjustment made.')
        if not self.db.execute('SELECT 1 FROM stock WHERE period=?',(period,)).fetchone():
            warnings.append('No stock counts entered for this period.')
        for row in self.db.execute('SELECT s.*,p.name FROM stock s JOIN products p ON p.id=s.product WHERE period=?',(period,)):
            if self.period_cost_method(period,row['product'])=='FIFO' and (row['drawings'] or row['broken']):
                warnings.append(f"{row['name']}: FIFO uses period totals, allocated to sales first, drawings second, breakages last. Individual movement dates are not recorded; category costs are provisional.")
        return warnings

    def install_controls(self):
        """Additive migration: log future changes and guard writes in locked periods."""
        import getpass
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS product_costing(id INTEGER PRIMARY KEY,product INTEGER UNIQUE REFERENCES products(id),method TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stock_costing(id INTEGER PRIMARY KEY,period INTEGER REFERENCES periods(id),product INTEGER REFERENCES products(id),method TEXT NOT NULL,UNIQUE(period,product));
        CREATE TABLE IF NOT EXISTS opening_layers(id INTEGER PRIMARY KEY,period INTEGER REFERENCES periods(id),product INTEGER REFERENCES products(id),sequence INTEGER,units INTEGER,unit_cost TEXT,source TEXT);
        CREATE TABLE IF NOT EXISTS stock_sales(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), product INTEGER REFERENCES products(id), amount INTEGER NOT NULL, UNIQUE(period,product));
        CREATE TABLE IF NOT EXISTS product_packages(id INTEGER PRIMARY KEY, product INTEGER UNIQUE REFERENCES products(id), package TEXT NOT NULL, per_package INTEGER NOT NULL CHECK(per_package>0));
        CREATE TABLE IF NOT EXISTS product_visuals(product INTEGER PRIMARY KEY REFERENCES products(id),category TEXT NOT NULL,low INTEGER,high INTEGER,photo BLOB);
        CREATE TABLE IF NOT EXISTS receipt_packages(id INTEGER PRIMARY KEY, receipt INTEGER UNIQUE REFERENCES receipts(id), package TEXT NOT NULL, per_package INTEGER NOT NULL, packages INTEGER NOT NULL, loose INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS period_locks(period INTEGER PRIMARY KEY REFERENCES periods(id), reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS import_batches(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), mode TEXT NOT NULL, digest TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(period,mode,digest));
        CREATE TABLE IF NOT EXISTS change_context(id INTEGER PRIMARY KEY CHECK(id=1), actor TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')), actor TEXT, reason TEXT, entity TEXT, action TEXT, record_id INTEGER, before_data TEXT, after_data TEXT);
        CREATE TABLE IF NOT EXISTS market_searches(id INTEGER PRIMARY KEY,query TEXT NOT NULL,retailer TEXT NOT NULL,searched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')));
        CREATE TABLE IF NOT EXISTS market_prices(id INTEGER PRIMARY KEY,search INTEGER NOT NULL REFERENCES market_searches(id),retailer TEXT,title TEXT NOT NULL,source TEXT NOT NULL,excerpt TEXT,published TEXT,amount INTEGER,currency TEXT,pack TEXT,units INTEGER,reviewed INTEGER NOT NULL DEFAULT 0,note TEXT);
        INSERT OR IGNORE INTO change_context VALUES (1,'Local user','Record saved');
        ''')
        self.db.execute('UPDATE change_context SET actor=? WHERE id=1',(getpass.getuser(),))
        for table in ['products','periods','stock','receipts','cash','orders','deliveries','customers','debts','repayments','period_locks','product_packages','receipt_packages','stock_sales','product_costing','stock_costing','opening_layers']:
            columns=[r['name'] for r in self.db.execute(f'PRAGMA table_info({table})')]
            def jsonrow(prefix):
                return 'json_object('+','.join("'"+c+"',"+prefix+'.'+c for c in columns)+')'
            idcol='period' if table=='period_locks' else 'id'
            for action in ['INSERT','UPDATE','DELETE']:
                before=jsonrow('OLD') if action!='INSERT' else 'NULL'
                after=jsonrow('NEW') if action!='DELETE' else 'NULL'
                prefix='OLD' if action=='DELETE' else 'NEW'
                self.db.execute(f'''CREATE TRIGGER IF NOT EXISTS audit_{table}_{action} AFTER {action} ON {table} BEGIN
                    INSERT INTO audit_log(actor,reason,entity,action,record_id,before_data,after_data)
                    SELECT actor,reason,'{table}','{action}',{prefix}.{idcol},{before},{after} FROM change_context WHERE id=1; END''')
        for table in ['stock','receipts','cash','debts','stock_sales','stock_costing','opening_layers']:
            for action,prefixes in [('INSERT',['NEW']),('UPDATE',['OLD','NEW']),('DELETE',['OLD'])]:
                guard=' OR '.join(f'EXISTS(SELECT 1 FROM period_locks WHERE period={prefix}.period)' for prefix in prefixes)
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS guard_{table}_{action} BEFORE {action} ON {table} WHEN {guard} BEGIN SELECT RAISE(ABORT,'Reporting period is locked. Reopen it with a reason before making changes.'); END")
        for action,prefixes in [('INSERT',['NEW']),('UPDATE',['OLD','NEW']),('DELETE',['OLD'])]:
            guard=' OR '.join(f'EXISTS(SELECT 1 FROM periods p JOIN period_locks l ON l.period=p.id WHERE {prefix}.day BETWEEN p.start AND p.end)' for prefix in prefixes)
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS guard_repayments_{action} BEFORE {action} ON repayments WHEN {guard} BEGIN SELECT RAISE(ABORT,'Payment date falls in a locked period. Reopen that period first.'); END")
        self.db.commit()

    def period_locked(self,period):
        return bool(self.db.execute('SELECT 1 FROM period_locks WHERE period=?',(period,)).fetchone())

    def set_lock(self,period,locked,reason):
        if not reason.strip():raise ValueError('A reason is required.')
        if locked:
            self.report(period)
            if not self.db.execute('SELECT 1 FROM stock WHERE period=?',(period,)).fetchone():raise ValueError('Enter stock counts before locking the period.')
        with self.db:
            self.db.execute('UPDATE change_context SET reason=? WHERE id=1',(reason.strip(),))
            if locked:self.db.execute('INSERT INTO period_locks(period,reason) VALUES (?,?)',(period,reason.strip()))
            else:self.db.execute('DELETE FROM period_locks WHERE period=?',(period,))
            self.db.execute("UPDATE change_context SET reason='Record saved' WHERE id=1")

    def correct_receipt(self,receipt_id,units,goods,freight,reason):
        if not reason.strip():raise ValueError('Explain the correction.')
        units=quantity(units);goods=money(goods);freight=money(freight)
        if not units and (goods or freight):raise ValueError('A void receipt must have zero units and zero costs.')
        with self.db:
            receipt=self.db.execute('SELECT * FROM receipts WHERE id=?',(receipt_id,)).fetchone()
            if not receipt:raise ValueError('Receipt not found.')
            count=self.db.execute('SELECT * FROM stock WHERE period=? AND product=?',(receipt['period'],receipt['product'])).fetchone()
            others=self.db.execute('SELECT COALESCE(SUM(units),0) FROM receipts WHERE period=? AND product=? AND id<>?',(receipt['period'],receipt['product'],receipt_id)).fetchone()[0]
            if count and count['closing']+count['drawings']+count['broken']>count['opening']+others+units:
                raise ValueError('This correction would make stock counts impossible. Correct the stock count first.')
            delivery=self.db.execute('SELECT * FROM deliveries WHERE receipt_id=?',(receipt_id,)).fetchone()
            if delivery:
                ordered=self.db.execute('SELECT units FROM orders WHERE id=?',(delivery['order_id'],)).fetchone()[0]
                other=self.db.execute('SELECT COALESCE(SUM(units),0) FROM deliveries WHERE order_id=? AND id<>?',(delivery['order_id'],delivery['id'])).fetchone()[0]
                if units+other>ordered:raise ValueError('Corrected delivery exceeds the order quantity.')
            self.db.execute('UPDATE change_context SET reason=? WHERE id=1',(reason.strip(),))
            self.db.execute('UPDATE receipts SET units=?,goods=?,freight=? WHERE id=?',(units,goods,freight,receipt_id))
            self.db.execute('DELETE FROM receipt_packages WHERE receipt=?',(receipt_id,))
            if delivery:self.db.execute('UPDATE deliveries SET units=? WHERE id=?',(units,delivery['id']))
            self.db.execute("UPDATE change_context SET reason='Record saved' WHERE id=1")


    def packaging(self,product):
        row=self.db.execute('SELECT package,per_package FROM product_packages WHERE product=?',(product,)).fetchone()
        return dict(row) if row else {'package':'Individual','per_package':1}

    def set_packaging(self,product,package,per_package,cost_method=None):
        per_package=validate_package(package,per_package)
        if cost_method is not None:validate_cost_method(cost_method)
        with self.db:
            self.db.execute('INSERT INTO product_packages(product,package,per_package) VALUES (?,?,?) ON CONFLICT(product) DO UPDATE SET package=excluded.package,per_package=excluded.per_package',(product,package,per_package))
            if cost_method is not None:self.db.execute('INSERT INTO product_costing(product,method) VALUES (?,?) ON CONFLICT(product) DO UPDATE SET method=excluded.method',(product,cost_method))

    def package_units(self,product,packages,loose):
        info=self.packaging(product)
        return quantity(packages)*info['per_package']+quantity(loose)

    def receipt_bulk(self,period,product,day,supplier,reference,packages,loose,goods,freight):
        self.check_day(period,day)
        packages,loose=quantity(packages),quantity(loose)
        info=self.packaging(product);units=self.package_units(product,packages,loose)
        if not units:raise ValueError('Enter at least one package or individual unit.')
        with self.db:
            receipt=self.db.execute('INSERT INTO receipts(period,product,day,supplier,reference,units,goods,freight) VALUES (?,?,?,?,?,?,?,?)',(period,product,day,supplier,reference,units,money(goods),money(freight))).lastrowid
            self.db.execute('INSERT INTO receipt_packages(receipt,package,per_package,packages,loose) VALUES (?,?,?,?,?)',(receipt,info['package'],info['per_package'],packages,loose))
        return units


    def stock_preview(self,period,product,opening,closing,drawings,broken,opening_cost,price,sales_total=None,cost_method=None):
        opening,closing,drawings,broken=[quantity(x) for x in (opening,closing,drawings,broken)]
        received,cost=self.db.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(goods+freight),0) FROM receipts WHERE period=? AND product=?',(period,product)).fetchone()
        available=opening+received;sold=available-closing-drawings-broken
        if sold<0:raise ValueError('Closing, drawings and breakages exceed available units.')
        valuation=self.inventory_valuation(period,product,{'opening':opening,'closing':closing,'drawings':drawings,'broken':broken,'opening_cost':money(opening_cost)},cost_method)
        average=valuation['cogs']/sold/100 if sold else Decimal(0)
        if sales_total is not None:
            amount=Decimal(money(sales_total))/100
            if not sold and amount:raise ValueError('Sales total must be zero when no units were sold.')
            unit=amount/sold if sold else Decimal(0)
        else:
            unit=Decimal(money(price))/100;amount=sold*unit
        return {'sold':sold,'unit_cost':average,'unit_price':unit,'sales':amount,'method':valuation['method'],'cogs':valuation['cogs']/100,'closing_value':valuation['closing_value']/100}


    def product_cost_method(self,product):
        row=self.db.execute('SELECT method FROM product_costing WHERE product=?',(product,)).fetchone()
        return row['method'] if row else 'Weighted average'

    def set_product_cost_method(self,product,method):
        validate_cost_method(method)
        with self.db:
            self.db.execute('INSERT INTO product_costing(product,method) VALUES (?,?) ON CONFLICT(product) DO UPDATE SET method=excluded.method',(product,method))

    def period_cost_method(self,period,product):
        row=self.db.execute('SELECT method FROM stock_costing WHERE period=? AND product=?',(period,product)).fetchone()
        if row:return row['method']
        # Pre-upgrade reports retain their previous weighted-average valuation.
        if self.db.execute('SELECT 1 FROM stock WHERE period=? AND product=?',(period,product)).fetchone():return 'Weighted average'
        return self.product_cost_method(product)

    def inventory_valuation(self,period,product,state=None,method=None):
        s=state or self.db.execute('SELECT * FROM stock WHERE period=? AND product=?',(period,product)).fetchone()
        if s is None:raise ValueError('Save a stock count for this product first.')
        method=method or self.period_cost_method(period,product);validate_cost_method(method)
        original=self.db.execute('SELECT opening,opening_cost FROM stock WHERE period=? AND product=?',(period,product)).fetchone()
        carried=self.db.execute('SELECT * FROM opening_layers WHERE period=? AND product=? ORDER BY sequence,id',(period,product)).fetchall()
        use_carried=bool(carried) and sum(r['units'] for r in carried)==s['opening'] and original and original['opening']==s['opening'] and original['opening_cost']==s['opening_cost']
        if use_carried:
            layers=[{'units':r['units'],'unit_cost':Decimal(r['unit_cost']),'source':r['source']} for r in carried]
        else:
            layers=[{'units':s['opening'],'unit_cost':Decimal(s['opening_cost']),'source':'Opening stock'}] if s['opening'] else []
        for receipt in self.db.execute('SELECT * FROM receipts WHERE period=? AND product=? AND units>0 ORDER BY day,id',(period,product)):
            layers.append({'units':receipt['units'],'unit_cost':Decimal(receipt['goods']+receipt['freight'])/receipt['units'],'source':f"{receipt['day']} receipt #{receipt['id']} {receipt['reference']}"})
        inputs=[dict(layer) for layer in layers]
        available=sum(layer['units'] for layer in layers)
        total=sum((layer['units']*layer['unit_cost'] for layer in layers),Decimal(0))
        sold=available-s['closing']-s['drawings']-s['broken']
        if sold<0:raise ValueError('Stock outflows exceed available units.')
        if method=='Weighted average':
            avg=total/available if available else Decimal(0)
            cogs=sold*avg;drawings=s['drawings']*avg;breakage=s['broken']*avg
            remaining=[{'units':s['closing'],'unit_cost':avg,'source':'Weighted-average closing stock'}] if s['closing'] else []
        else:
            def consume(units):
                value=Decimal(0)
                for layer in layers:
                    take=min(units,layer['units']);value+=take*layer['unit_cost'];layer['units']-=take;units-=take
                    if not units:break
                if units:raise ValueError('Not enough cost layers for the stock movements.')
                return value
            # Period totals lack individual movement dates. This explicit allocation
            # order is disclosed whenever non-sale movements exist.
            cogs=consume(sold);drawings=consume(s['drawings']);breakage=consume(s['broken'])
            remaining=[layer for layer in layers if layer['units']]
        closing_value=sum((layer['units']*layer['unit_cost'] for layer in remaining),Decimal(0))
        return {'method':method,'inputs':inputs,'remaining':remaining,'cogs':cogs,'drawings':drawings,'breakage':breakage,'closing_value':closing_value,'available_value':total,'sold':sold,'carried':bool(use_carried)}


class Cloud:
    """Manual account-scoped snapshot transfer. Tokens live only in memory."""
    MAX_DB=10*1024*1024

    def __init__(self,url,key,shop=None):
        import re,base64,json
        url=url.strip().rstrip('/')
        if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',url):
            raise ValueError('Use the HTTPS project URL, such as https://project.supabase.co.')
        if key.startswith('sb_secret_'):raise ValueError('Use the publishable/anon key, never a secret/service-role key.')
        if key.startswith('eyJ'):
            try:
                part=key.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
                if claims.get('role')!='anon':raise ValueError('Use the anon key, not a privileged key.')
            except (IndexError,KeyError):raise ValueError('Invalid project key.') from None
        elif not key.startswith('sb_publishable_'):raise ValueError('Enter a publishable or legacy anon key.')
        if shop is not None and shop not in ('mutowei-bottle-store','bizzy-tuckshop','chikofa-tuckshop'):raise ValueError('Unknown shop.')
        self.shop=shop
        self.url=url;self.key=key.strip();self.token=None;self.owner=None

    def request(self,path,payload=None):
        import json,urllib.request,urllib.error
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        request=urllib.request.Request(self.url+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=45) as response:data=response.read(17000001)
            if len(data)>17000000:raise ValueError('Cloud response too large.')
            return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            body=error.read(4096).decode('utf-8',errors='replace')
            if 'CLOUD_CONFLICT' in body:raise ValueError('A newer cloud copy exists. Upload blocked. Back up this PC and download the cloud copy before continuing.') from None
            raise ValueError(f'Cloud request failed (HTTP {error.code}). Check sign-in and run the latest multi-shop setup SQL if needed. Sign in again if your session expired.') from None

    def login(self,email,password):
        result=self.request('/auth/v1/token?grant_type=password',{'email':email,'password':password})
        self.token=result['access_token'];self.owner=result['user']['id']

    def upload(self,path,expected):
        import base64,json,hashlib
        from pathlib import Path
        data=Path(path).read_bytes()
        if len(data)>self.MAX_DB:raise ValueError('Cloud backup supports databases up to 10 MiB in this version.')
        if self.shop:
            with sqlite3.connect(path) as check:
                row=check.execute('SELECT shop FROM shop_identity WHERE id=1').fetchone()
                if not row or row[0]!=self.shop:raise ValueError('Backup belongs to a different shop.')
        snapshot=json.dumps({'format':1,'shop':self.shop,'sha256':hashlib.sha256(data).hexdigest(),'database':base64.b64encode(data).decode()})
        if self.shop:return self.request('/rest/v1/rpc/family_shop_upload_shop',{'expected_version':expected,'snapshot':snapshot,'target_shop':self.shop})
        return self.request('/rest/v1/rpc/family_shop_upload',{'expected_version':expected,'snapshot':snapshot})

    def download(self,path):
        import base64,json,hashlib
        from pathlib import Path
        if not self.owner:raise ValueError('Sign in first.')
        table='family_shop_shop_backups' if self.shop else 'family_shop_backups'
        rows=self.request('/rest/v1/'+table+'?select=version,payload,updated_at&owner=eq.'+self.owner+('&shop=eq.'+self.shop if self.shop else ''))
        if not rows:raise ValueError('No cloud backup found for this account.')
        snapshot=json.loads(rows[0]['payload'])
        if snapshot.get('format')!=1:raise ValueError('Unsupported cloud backup format.')
        if self.shop and snapshot.get('shop')!=self.shop:raise ValueError('Cloud backup belongs to another shop.')
        data=base64.b64decode(snapshot['database'],validate=True)
        if len(data)>self.MAX_DB or hashlib.sha256(data).hexdigest()!=snapshot['sha256']:raise ValueError('Backup integrity check failed.')
        Path(path).write_bytes(data)
        db=None
        try:
            db=sqlite3.connect(path)
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Cloud database is damaged.')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'products','periods','stock','receipts','cash'}.issubset(tables):raise ValueError('Not a Family Shop database.')
            if self.shop:
                identity=db.execute('SELECT shop FROM shop_identity WHERE id=1').fetchone()
                if not identity or identity[0]!=self.shop:raise ValueError('Cloud database belongs to another shop.')
            if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Cloud database contains invalid references.')
        except sqlite3.DatabaseError:raise ValueError('Invalid cloud database.') from None
        finally:
            if db:db.close()
        return int(rows[0]['version'])


CLOUD_SETUP_SQL = "-- Run once in your dedicated Supabase project's SQL editor.\ncreate table if not exists public.family_shop_backups (\n  owner uuid primary key references auth.users(id) on delete cascade,\n  version bigint not null check (version > 0),\n  payload text not null check (octet_length(payload) <= 16000000),\n  updated_at timestamptz not null default now()\n);\nalter table public.family_shop_backups enable row level security;\nrevoke all on public.family_shop_backups from anon;\ngrant select, insert, update on public.family_shop_backups to authenticated;\ndrop policy if exists family_shop_owner on public.family_shop_backups;\ncreate policy family_shop_owner on public.family_shop_backups for all to authenticated\nusing ((select auth.uid()) = owner) with check ((select auth.uid()) = owner);\n\ncreate or replace function public.family_shop_upload(expected_version bigint, snapshot text)\nreturns bigint language plpgsql security invoker set search_path = '' as $$\ndeclare next_version bigint;\nbegin\n  if auth.uid() is null then raise exception 'Sign in required'; end if;\n  if expected_version < 0 or octet_length(snapshot)>16000000 then raise exception 'Invalid snapshot'; end if;\n  if expected_version = 0 then\n    insert into public.family_shop_backups(owner,version,payload)\n      values(auth.uid(),1,snapshot) on conflict do nothing returning version into next_version;\n  else\n    update public.family_shop_backups set version=version+1,payload=snapshot,updated_at=now()\n      where owner=auth.uid() and version=expected_version returning version into next_version;\n  end if;\n  if next_version is null then raise exception 'CLOUD_CONFLICT: Download the newer cloud copy before uploading'; end if;\n  return next_version;\nend $$;\nrevoke execute on function public.family_shop_upload(bigint,text) from public, anon;\ngrant execute on function public.family_shop_upload(bigint,text) to authenticated;\n\n-- Multi-shop upgrade: preserve the earlier single-shop backup table.\ncreate table if not exists public.family_shop_shop_backups (\n  owner uuid not null references auth.users(id) on delete cascade,\n  shop text not null check (shop in ('mutowei-bottle-store','bizzy-tuckshop','chikofa-tuckshop')),\n  version bigint not null check (version > 0),\n  payload text not null check (octet_length(payload) <= 16000000),\n  updated_at timestamptz not null default now(),\n  primary key(owner,shop)\n);\nalter table public.family_shop_shop_backups enable row level security;\nrevoke all on public.family_shop_shop_backups from anon;\ngrant select,insert,update on public.family_shop_shop_backups to authenticated;\ndrop policy if exists family_shop_shop_owner on public.family_shop_shop_backups;\ncreate policy family_shop_shop_owner on public.family_shop_shop_backups for all to authenticated\nusing ((select auth.uid())=owner) with check ((select auth.uid())=owner);\ncreate or replace function public.family_shop_upload_shop(expected_version bigint,snapshot text,target_shop text)\nreturns bigint language plpgsql security invoker set search_path='' as $$\ndeclare next_version bigint;\nbegin\n  if auth.uid() is null then raise exception 'Sign in required'; end if;\n  if expected_version<0 or octet_length(snapshot)>16000000 or target_shop not in ('mutowei-bottle-store','bizzy-tuckshop','chikofa-tuckshop') then raise exception 'Invalid snapshot or shop'; end if;\n  if expected_version=0 then\n    insert into public.family_shop_shop_backups(owner,shop,version,payload)\n    values(auth.uid(),target_shop,1,snapshot) on conflict do nothing returning version into next_version;\n  else\n    update public.family_shop_shop_backups set version=version+1,payload=snapshot,updated_at=now()\n    where owner=auth.uid() and shop=target_shop and version=expected_version returning version into next_version;\n  end if;\n  if next_version is null then raise exception 'CLOUD_CONFLICT: Download the newer cloud copy before uploading'; end if;\n  return next_version;\nend $$;\nrevoke execute on function public.family_shop_upload_shop(bigint,text,text) from public,anon;\ngrant execute on function public.family_shop_upload_shop(bigint,text,text) to authenticated;\n"


OCR_POWERSHELL = 'param([string]$ImagePath,[string]$OutputPath)\n$ErrorActionPreference=\'Stop\'\nAdd-Type -AssemblyName System.Runtime.WindowsRuntime\n$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]\n$null=[Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]\n$null=[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]\n$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]\n$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]\n$null=[Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]\n$null=[Windows.Media.Ocr.OcrResult,Windows.Media.Ocr,ContentType=WindowsRuntime]\n$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq \'AsTask\' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq \'IAsyncOperation`1\'})[0]\nfunction Await($operation,$type) {\n    $task=$asTask.MakeGenericMethod($type).Invoke($null,@($operation))\n    $task.Wait()\n    return $task.Result\n}\n$stream=$null\n$bitmap=$null\ntry {\n    $file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])\n    $stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])\n    $decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])\n    $bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])\n    $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()\n    if ($null -eq $engine) {throw \'No Windows OCR language is installed. Install English OCR in Windows language settings, then try again.\'}\n    if ($bitmap.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or $bitmap.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) {throw \'Image is too large for Windows OCR. Resize the longest side to 2000 pixels and try again.\'}\n    $result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])\n    $text=($result.Lines | ForEach-Object {$_.Text}) -join "`n"\n    [System.IO.File]::WriteAllText($OutputPath,$text,[System.Text.UTF8Encoding]::new($false))\n} finally {\n    if ($null -ne $bitmap) {$bitmap.Dispose()}\n    if ($null -ne $stream) {$stream.Dispose()}\n}\n'


def scan_image(path):
    """Offline Windows OCR; path is passed as an argument, never interpolated code."""
    import os,subprocess,tempfile
    from pathlib import Path
    if os.name!='nt':raise ValueError('Image scanning requires Windows 10/11. You can still paste text and review/import it.')
    source=Path(path).resolve()
    if source.suffix.lower() not in ('.png','.jpg','.jpeg','.bmp'):raise ValueError('Choose a PNG, JPG or BMP image.')
    if source.stat().st_size>30*1024*1024:raise ValueError('Choose an image smaller than 30 MiB.')
    with tempfile.TemporaryDirectory(prefix='family-shop-ocr-') as folder:
        script=Path(folder)/'scan.ps1';output=Path(folder)/'text.txt'
        script.write_text(OCR_POWERSHELL,encoding='utf-8-sig')
        # Apply only to this child process; do not change Windows/user policy.
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-ImagePath',str(source),'-OutputPath',str(output)],capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not output.exists():
            error=result.stderr.decode(errors='replace').strip()
            raise ValueError('Windows OCR could not read this image. Check that English OCR is installed and the image is clear. If Windows blocks the script, paste the text manually.\n'+error[:1000])
        text=output.read_text(encoding='utf-8-sig')
        if not text.strip():raise ValueError('No text was found. Try a sharper, straight photo with good lighting.')
        return text


IMPORT_COLUMNS={
    'Stock counts':['Product','Unit','Opening','Closing','Drawings','Broken','OpeningCost','SellingPrice'],
    'Daily money':['Date','Cash','EcoCash','Credit','CashOut','Expenses','Notes'],
    'Goods received':['Date','Product','Unit','Supplier','Reference','Units','GoodsCost','DeliveryCost']
}


def arrange_scan(text,mode):
    """Conservative draft: preserve unparsed lines and leave unknown fields blank."""
    import csv,io,re
    output=io.StringIO();writer=csv.writer(output);writer.writerow(IMPORT_COLUMNS[mode]);unparsed=[]
    for line in text.splitlines():
        if not line.strip():continue
        if ',' in line or '|' in line or '\t' in line:
            delimiter='|' if '|' in line else '\t' if '\t' in line else ','
            parts=next(csv.reader([line],delimiter=delimiter))
            parts=[x.strip() for x in parts]
            if parts==IMPORT_COLUMNS[mode]:continue
            if len(parts)==len(IMPORT_COLUMNS[mode]):writer.writerow(parts);continue
        if mode=='Stock counts':
            clean=re.sub(r'^\s*\d{1,4}[/-]\d{1,2}(?:[/-]\d{2,4})?\s+','',line.strip())
            match=re.fullmatch(r'(.+?)\s+((?:\$?\d+(?:\.\d+)?\s+){6}\$?\d+(?:\.\d+)?)',clean)
            if match:
                numbers=[x.lstrip('$') for x in match[2].split()]
                opening,received,total,closing,sold,price,amount=numbers
                if Decimal(opening)+Decimal(received)==Decimal(total) and Decimal(sold)*Decimal(price)==Decimal(amount):
                    writer.writerow([match[1],'each',opening,closing,'','','',price]);continue
        unparsed.append(line)
    return output.getvalue(),unparsed


def import_reviewed(ledger,period,mode,text,source):
    """Validate a full batch on a clone before copying its committed state back."""
    import csv,io,hashlib
    if mode not in IMPORT_COLUMNS:raise ValueError('Choose an import type.')
    reader=csv.DictReader(io.StringIO(text))
    if reader.fieldnames!=IMPORT_COLUMNS[mode]:raise ValueError('Keep the exact CSV column headings shown in the draft.')
    rows=list(reader)
    if not rows:raise ValueError('No rows to import.')
    if len(rows)>1000:raise ValueError('Import at most 1,000 rows at a time.')
    clone=Ledger(':memory:')
    try:
        ledger.db.backup(clone.db)
        if clone.period_locked(period):raise ValueError('The selected period is locked.')
        digest=hashlib.sha256(text.strip().encode()).hexdigest()
        if clone.db.execute('SELECT 1 FROM import_batches WHERE period=? AND mode=? AND digest=?',(period,mode,digest)).fetchone():raise ValueError('This exact reviewed batch has already been imported.')
        clone.db.execute('UPDATE change_context SET reason=? WHERE id=1',('Reviewed image/text import: '+source[:200],));clone.db.commit()
        for number,row in enumerate(rows,2):
            try:
                if None in row or any(v is None for v in row.values()):raise ValueError('Wrong number of columns.')
                row={k:v.strip() for k,v in row.items()}
                optional={'Notes','Supplier','Reference'}
                if any(not v for k,v in row.items() if k not in optional):raise ValueError('Fill in all quantities and costs explicitly, including zero where confirmed.')
                if mode=='Daily money':
                    if clone.db.execute('SELECT 1 FROM cash WHERE period=? AND day=?',(period,row['Date'])).fetchone():raise ValueError('Daily money already exists for this date; edit it in the app instead.')
                    clone.cash(period,row['Date'],row['Cash'],row['EcoCash'],row['Credit'],row['CashOut'],row['Expenses'],row['Notes'])
                else:
                    product=clone.db.execute('SELECT id,unit FROM products WHERE name=?',(row['Product'],)).fetchone()
                    if product and product['unit']!=row['Unit']:raise ValueError('Product unit differs from the existing product.')
                    pid=product['id'] if product else clone.product(row['Product'],row['Unit'])
                    if mode=='Stock counts':
                        if clone.db.execute('SELECT 1 FROM stock WHERE period=? AND product=?',(period,pid)).fetchone():raise ValueError('Stock count already exists for this product; edit it in the app instead.')
                        clone.stock(period,pid,row['Opening'],row['Closing'],row['Drawings'],row['Broken'],row['OpeningCost'],row['SellingPrice'])
                    else:
                        clone.receipt(period,pid,row['Date'],row['Supplier'],row['Reference'],row['Units'],row['GoodsCost'],row['DeliveryCost'])
            except Exception as exc:raise ValueError(f'CSV row {number}: {exc}') from None
        clone.db.execute('INSERT INTO import_batches(period,mode,digest,source) VALUES (?,?,?,?)',(period,mode,digest,source[:200]))
        clone.db.execute("UPDATE change_context SET reason='Record saved' WHERE id=1");clone.db.commit()
        clone.db.backup(ledger.db)
        return len(rows)
    finally:clone.db.close()


PACKAGE_TYPES=['Individual','Box','Case','Crate','Pack','Carton','Sack','Bag','Bundle','Tray','Pallet','Bale','Drum','Tub','Roll','Other']


def validate_package(package,per_package):
    if package not in PACKAGE_TYPES:raise ValueError('Choose a package type from the list.')
    per_package=quantity(per_package)
    if not per_package:raise ValueError('Units per package must be greater than zero.')
    if package=='Individual' and per_package!=1:raise ValueError('An individual contains one unit. Choose a bulk package type for more units.')
    return per_package



def purchase_unit_cost(units,goods,freight):
    units=quantity(units)
    if not units:raise ValueError('Enter received units first.')
    return Decimal(money(goods))/units/100,Decimal(money(goods)+money(freight))/units/100


COST_METHODS=['Weighted average','FIFO']


def validate_cost_method(method):
    if method not in COST_METHODS:raise ValueError('Choose FIFO or Weighted average.')


class AuthSession:
    def __init__(self,store,token,name):self.store=store;self.token=token;self.name=name
    def valid(self):
        import hmac
        return bool(self.store.active_token) and hmac.compare_digest(self.token,self.store.active_token)


class AuthStore:
    """Local owner gate. Hashes credentials; does not encrypt shop databases."""
    ROUNDS=600000
    LOCK_SECONDS=60
    def __init__(self,path):
        from pathlib import Path
        import os
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
        self.active_token=None;self._email_proof=None
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,password TEXT NOT NULL,recovery TEXT NOT NULL,question TEXT,answer TEXT,email TEXT,email_uid TEXT,email_url TEXT,email_key TEXT);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),name TEXT,kind TEXT,result TEXT,alert INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS throttle(kind TEXT,subject TEXT,failures INTEGER,started REAL,locked REAL,PRIMARY KEY(kind,subject));
        ''')
        try:
            os.chmod(self.path.parent,0o700);os.chmod(self.path,0o600)
        except OSError:pass
    @staticmethod
    def normalized(value):return ' '.join(str(value).strip().casefold().split())
    @staticmethod
    def safe_name(value):return ''.join(c for c in str(value) if c.isprintable()).strip()[:80] or '(blank)'
    @staticmethod
    def check_password(value):
        if not 12<=len(value)<=256 or not value.strip():raise ValueError('Choose a password or passphrase of 12–256 characters.')
    @staticmethod
    def new_key():
        import secrets
        raw=secrets.token_hex(16).upper()
        return 'MI-'+'-'.join(raw[i:i+4] for i in range(0,len(raw),4))
    @staticmethod
    def key_value(value):return ''.join(c for c in str(value).upper() if c.isalnum())
    @classmethod
    def hash_secret(cls,secret):
        import hashlib,secrets,json
        salt=secrets.token_bytes(16)
        return json.dumps({'salt':salt.hex(),'rounds':cls.ROUNDS,'hash':hashlib.pbkdf2_hmac('sha256',secret.encode(),salt,cls.ROUNDS).hex()})
    @staticmethod
    def matches(secret,stored):
        import hashlib,hmac,json
        try:
            data=json.loads(stored);rounds=int(data['rounds'])
            if not 100000<=rounds<=1000000:return False
            result=hashlib.pbkdf2_hmac('sha256',secret.encode(),bytes.fromhex(data['salt']),rounds).hex()
            return hmac.compare_digest(result,data['hash'])
        except (ValueError,KeyError,TypeError):return False
    def owner(self):return self.db.execute('SELECT * FROM owner WHERE id=1').fetchone()
    def setup(self,name,password,question='',answer=''):
        if self.owner():raise ValueError('The owner account is already configured.')
        raw=str(name).strip();name=self.safe_name(name)
        if name=='(blank)':raise ValueError('Enter the owner name.')
        if name!=raw or len(raw)>80:raise ValueError('Use an owner name of at most 80 printable characters.')
        self.check_password(password)
        if bool(question.strip())!=bool(answer.strip()):raise ValueError('Enter both a question and an answer, or leave both blank.')
        if answer.strip() and len(self.normalized(answer))<8:raise ValueError('Use a recovery answer of at least 8 characters that other people cannot guess.')
        key=self.new_key()
        with self.db:
            self.db.execute('INSERT INTO owner(id,name,password,recovery,question,answer) VALUES (1,?,?,?,?,?)',(name,self.hash_secret(password),self.hash_secret(self.key_value(key)),question.strip()[:300],self.hash_secret(self.normalized(answer)) if answer.strip() else None))
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'setup','Owner account created')",(name,))
        return key
    def remaining(self,kind):
        import time
        row=self.db.execute("SELECT locked FROM throttle WHERE kind=? AND subject='*'",(kind,)).fetchone()
        return max(0,int(row['locked']-time.time()+.999)) if row else 0
    def check_rate(self,kind):
        wait=self.remaining(kind)
        if wait:raise ValueError(f'Temporarily locked. Try again in {wait} seconds.')
    def failed(self,kind,name,result='Incorrect credentials'):
        import time
        now=time.time();name=self.safe_name(name);counts=[]
        with self.db:
            for subject in ('*','name:'+self.normalized(name)):
                old=self.db.execute('SELECT * FROM throttle WHERE kind=? AND subject=?',(kind,subject)).fetchone()
                count=old['failures'] if old and now-old['started']<900 and not (old['locked'] and old['locked']<=now) else 0
                count+=1;locked=now+self.LOCK_SECONDS if count>=3 else 0
                started=old['started'] if old and count>1 else now
                self.db.execute('INSERT INTO throttle VALUES (?,?,?,?,?) ON CONFLICT(kind,subject) DO UPDATE SET failures=excluded.failures,started=excluded.started,locked=excluded.locked',(kind,subject,count,started,locked));counts.append(count)
            self.db.execute('INSERT INTO attempts(name,kind,result,alert) VALUES (?,?,?,?)',(name,kind,result,1 if max(counts)>=3 else 0))
        return max(counts)>=3
    def login(self,name,password):
        import secrets
        self.check_rate('login');row=self.owner()
        if not row:raise ValueError('Create the owner account first.')
        valid=self.matches(password,row['password'])
        if not valid or self.normalized(name)!=self.normalized(row['name']):
            alerted=self.failed('login',name)
            raise ValueError('Name or password is incorrect.'+(' Three attempts failed; login is locked for 60 seconds.' if alerted else ''))
        self.active_token=secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("DELETE FROM throttle WHERE kind='login'")
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'login','Successful owner login')",(row['name'],))
        return AuthSession(self,self.active_token,row['name'])
    def require(self,session):
        if not session or session.store is not self or not session.valid():raise PermissionError('Owner login required.')
    def lock(self):self.active_token=None;self._email_proof=None
    def change_password(self,session,current,new):
        self.require(session);self.check_rate('admin');self.check_password(new)
        if not self.matches(current,self.owner()['password']):
            self.check_rate('admin');self.failed('admin',session.name);raise ValueError('Current password is incorrect.')
        with self.db:
            self.db.execute('UPDATE owner SET password=? WHERE id=1',(self.hash_secret(new),))
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'admin','Password changed')",(session.name,))
    def rotate_key(self,session,password):
        self.require(session);self.check_rate('admin')
        if not self.matches(password,self.owner()['password']):self.failed('admin',session.name);raise ValueError('Current password is incorrect.')
        key=self.new_key()
        with self.db:
            self.db.execute('UPDATE owner SET recovery=? WHERE id=1',(self.hash_secret(self.key_value(key)),))
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'admin','Recovery key rotated')",(session.name,))
        return key
    def bind_email(self,session,password,url,key,email,uid):
        self.require(session);self.check_rate('admin')
        if not self.matches(password,self.owner()['password']):self.failed('admin',session.name);raise ValueError('Current password is incorrect.')
        with self.db:
            self.db.execute('UPDATE owner SET email=?,email_uid=?,email_url=?,email_key=? WHERE id=1',(email.strip().casefold(),uid,url,key))
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'admin','Recovery email verified')",(session.name,))
    def email_proof(self,uid,email):
        import secrets
        row=self.owner()
        if not row or row['email_uid']!=uid or row['email']!=email.strip().casefold():raise ValueError('Recovery email verification did not match the owner.')
        import time
        token=secrets.token_urlsafe(32);self._email_proof=(token,time.time()+120);return token
    def recover(self,name,method,secret,new_password):
        import hmac
        self.check_rate('recovery');self.check_password(new_password);row=self.owner()
        valid=False
        if row and self.normalized(name)==self.normalized(row['name']):
            if method=='Backup key':valid=self.matches(self.key_value(secret),row['recovery'])
            elif method=='Security question' and row['answer']:valid=self.matches(self.normalized(secret),row['answer'])
            elif method=='Email code':
                import time
                valid=bool(self._email_proof) and time.time()<self._email_proof[1] and hmac.compare_digest(secret,self._email_proof[0])
        self._email_proof=None
        if not valid:
            alerted=self.failed('recovery',name,'Failed password recovery')
            raise ValueError('Recovery details are incorrect.'+(' Recovery is locked for 60 seconds.' if alerted else ''))
        key=self.new_key()
        with self.db:
            self.db.execute('UPDATE owner SET password=?,recovery=? WHERE id=1',(self.hash_secret(new_password),self.hash_secret(self.key_value(key))))
            self.db.execute('DELETE FROM throttle')
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'recovery','Password recovered; backup key rotated')",(row['name'],))
        self.lock();return key


    def set_question(self,session,password,question,answer):
        self.require(session);self.check_rate('admin')
        if not self.matches(password,self.owner()['password']):self.failed('admin',session.name);raise ValueError('Current password is incorrect.')
        if bool(question.strip())!=bool(answer.strip()):raise ValueError('Provide both question and answer, or leave both blank to disable it.')
        if answer.strip() and len(self.normalized(answer))<8:raise ValueError('Use an answer of at least 8 characters.')
        with self.db:
            self.db.execute('UPDATE owner SET question=?,answer=? WHERE id=1',(question.strip()[:300],self.hash_secret(self.normalized(answer)) if answer.strip() else None))
            self.db.execute("INSERT INTO attempts(name,kind,result) VALUES (?,'admin','Recovery question updated')",(session.name,))

    def email_settings(self,name):
        self.check_rate('email');row=self.owner()
        if not row or self.normalized(name)!=self.normalized(row['name']) or not row['email']:
            self.failed('email',name,'Email recovery unavailable or owner name did not match')
            raise ValueError('Email recovery is unavailable for those details. Use your backup key or configured question.')
        return dict(row)

    def email_sent(self):
        import time
        now=time.time()
        with self.db:self.db.execute("INSERT INTO throttle VALUES ('email','*',0,?,?) ON CONFLICT(kind,subject) DO UPDATE SET failures=0,started=excluded.started,locked=excluded.locked",(now,now+60))


class EmailRecovery:
    """Supabase OTP proves ownership without changing the Supabase password."""
    def __init__(self,url,key,email):self.client=Cloud(url,key);self.email=email.strip().casefold()
    def send(self):self.client.request('/auth/v1/otp',{'email':self.email,'create_user':False})
    def verify(self,code):
        result=self.client.request('/auth/v1/verify',{'email':self.email,'token':code.strip(),'type':'email'})
        user=result.get('user',{})
        if user.get('email','').casefold()!=self.email or not user.get('id'):raise ValueError('Email verification did not match.')
        return user['id']


# Price references are independent of the accounting engine.
PRICE_RETAILERS={
    'All retailers':'("N Richards" OR "Gain Cash" OR "Metro Hypermarket" OR "Metro Peech")',
    'N. Richards':'"N Richards"',
    'Gain Cash & Carry':'"Gain Cash"',
    'Metro / Peech':'("Metro Hypermarket" OR "Metro Peech")',
}


def price_query(text,required=True):
    import re
    text=' '.join(str(text).split())
    if len(text)>180:raise ValueError('Keep the product search under 180 characters.')
    # Quantities are optional; retain product sizes such as 2kg or 750ml.
    text=re.sub(r'^\d+\s+(?:(?:crates?|cases?|boxes?|packs?|units?|bottles?|bags?)\s+(?:of\s+)?)?', '',text,flags=re.I).strip()
    text=re.sub(r'\b\d+\s+(?:crates?|cases?|boxes?|packs?|units?|bottles?|bags?)\b', '',text,flags=re.I)
    text=' '.join(text.split())
    if required and (not text or not any(c.isalpha() for c in text)):raise ValueError('Enter a product name, for example Castle Quart or sugar 2kg.')
    return text


def public_price_url(value):
    from urllib.parse import urlsplit
    import ipaddress
    value=str(value).strip()
    try:
        parts=urlsplit(value)
        if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in value):raise ValueError()
        host=parts.hostname.casefold()
        if host=='localhost' or '.' not in host or host.endswith(('.local','.localhost','.internal')):raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:raise ValueError()
        except ValueError:
            # A hostname must not be a disguised numeric/private address.
            if ':' in host or all(c.isdigit() or c=='.' for c in host):raise ValueError()
        return value[:2000]
    except (ValueError,TypeError):raise ValueError('Enter a public http:// or https:// advert/source link.') from None


def snippet_price(text):
    """Only one explicit currency/amount is a candidate, never a verified cost."""
    import re
    matches=[]
    pattern=r'(?<![\w$])(?P<currency>US\$|USD\s*\$?|ZWG\s*\$?|ZiG\s*\$?|ZAR\s*|R\s*|\$)\s*(?P<amount>\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d.])'
    for match in re.finditer(pattern,text,re.I):
        prefix=match.group('currency').upper().replace(' ','')
        currency='USD' if prefix.startswith(('US$','USD')) else 'ZWG' if prefix.startswith(('ZWG','ZIG')) else 'ZAR' if prefix.startswith(('ZAR','R')) else 'Unknown ($)'
        amount=money(match.group('amount').replace(',',''))
        if amount:matches.append((amount,currency))
    unique=set(matches)
    return next(iter(unique)) if len(unique)==1 else (None,'Unknown')


class MarketSearch:
    """Google results via Serper; one explicit click uses one API request."""
    ENDPOINT='https://google.serper.dev/search'

    @staticmethod
    def query(product,retailer):
        if retailer not in PRICE_RETAILERS:raise ValueError('Choose a retailer.')
        # Quote user words so a product cannot inject search operators.
        import re
        terms=' '.join(re.findall(r'[\w.-]+',price_query(product),flags=re.UNICODE))
        return f'"{terms}" Zimbabwe {PRICE_RETAILERS[retailer]} price specials'

    @classmethod
    def google_url(cls,product,retailer):
        from urllib.parse import urlencode
        return 'https://www.google.com/search?'+urlencode({'q':cls.query(product,retailer)})

    @staticmethod
    def parse(payload,product,retailer):
        import re
        product=price_query(product)
        terms=re.findall(r'[\w]+',product.casefold())
        rows=[];seen=set()
        for item in payload.get('organic',[])[:30]:
            if not isinstance(item,dict):continue
            title=str(item.get('title',''));excerpt=str(item.get('snippet',''))
            text=title+' '+excerpt
            if not all(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',text.casefold()) for t in terms):continue
            try:source=public_price_url(item.get('link',''))
            except ValueError:continue
            identity=(text+' '+source).casefold()
            label=('N. Richards' if any(t in identity for t in ('nrichards','n richards','n. richards')) else
                   'Gain Cash & Carry' if any(t in identity for t in ('gaincash','gain cash','gain.co.zw')) else
                   'Metro / Peech' if any(t in identity for t in ('metrohypermarket','metro hypermarket','metropeech','metro peech')) else '')
            if not label or (retailer!='All retailers' and retailer!=label) or source in seen:continue
            seen.add(source)
            amount,currency=snippet_price(text)
            rows.append({'title':title,'source':source,'excerpt':excerpt,'published':str(item.get('date','')),
                         'amount':amount,'currency':currency,'retailer':label,'pack':'Unknown','units':None,'reviewed':False,
                         'note':'Google snippet via Serper. Product match, currency, package, branch and advert validity need checking. Search date is not the advert date.'})
        return rows

    @classmethod
    def search(cls,product,retailer,key):
        import json,urllib.request,urllib.error
        if not key.strip():raise ValueError('Connect a Serper API key for automatic Google results, or use Open Google and save a checked advert manually.')
        request=urllib.request.Request(cls.ENDPOINT,data=json.dumps({'q':cls.query(product,retailer),'gl':'zw','hl':'en','num':10}).encode(),headers={'X-API-KEY':key.strip(),'Content-Type':'application/json','User-Agent':'MutoweiInvestments/0.19'})
        try:
            with urllib.request.urlopen(request,timeout=20) as response:data=response.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('Search response is too large.')
            payload=json.loads(data)
            if not isinstance(payload,dict) or not isinstance(payload.get('organic',[]),list):raise ValueError('Search service returned an unexpected response.')
            if 'message' in payload and 'organic' not in payload:raise ValueError('Search service did not return results. Check your API account.')
            return cls.parse(payload,product,retailer)
        except urllib.error.HTTPError as exc:
            message={401:'API key was rejected.',403:'API access was denied; check the key and credits.',429:'Search limit reached. Use saved offline results or try later.'}.get(exc.code,f'Search service returned HTTP {exc.code}.')
            raise ValueError(message) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise ValueError('Online search could not connect. Your saved offline results remain available.') from None


PRODUCT_CATEGORIES=['Grocery','Beer','Cigarettes','Household','Other']


def stock_indicator(closing,low=None,high=None):
    if closing is None:return 'Not counted','neutral',0
    if low is None or high is None:return 'Set stock range','neutral',None
    if closing<=low:return 'Low stock','warning',min(1,closing/max(1,high))
    if closing>high:return 'Above target','warning',1
    return 'Healthy stock','good',min(1,closing/max(1,high))


def closing_indicator(totals,has_stock):
    if not has_stock:return 'No stock counts','neutral'
    value=Decimal(totals['Unreconciled difference (positive = short)'])
    if not value:return 'Balanced — recorded stock and money agree','good'
    return f"{'Shortage' if value>0 else 'Surplus'} ${abs(value):.2f} — review entries",'warning'
