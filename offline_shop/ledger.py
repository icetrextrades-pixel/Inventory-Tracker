"""Offline shop records. Monetary inputs use decimal strings, stored as cents."""
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date


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

    def stock(self, period, product, opening, closing, drawings, broken, opening_cost, price, sales_total=None, cost_method=None):
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
        with self.db:
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

    def cash(self, period, day, cash, ecocash, credit, cashout, expense, note):
        self.check_day(period,day)
        values = [money(x) for x in (cash,ecocash,credit,cashout,expense)]
        with self.db:
            self.db.execute('INSERT INTO cash(period,day,cash,ecocash,credit,cashout,expense,note) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(period,day) DO UPDATE SET cash=excluded.cash,ecocash=excluded.ecocash,credit=excluded.credit,cashout=excluded.cashout,expense=excluded.expense,note=excluded.note', (period,day,*values,note))

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
        CREATE TABLE IF NOT EXISTS receipt_packages(id INTEGER PRIMARY KEY, receipt INTEGER UNIQUE REFERENCES receipts(id), package TEXT NOT NULL, per_package INTEGER NOT NULL, packages INTEGER NOT NULL, loose INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS period_locks(period INTEGER PRIMARY KEY REFERENCES periods(id), reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS import_batches(id INTEGER PRIMARY KEY, period INTEGER REFERENCES periods(id), mode TEXT NOT NULL, digest TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(period,mode,digest));
        CREATE TABLE IF NOT EXISTS change_context(id INTEGER PRIMARY KEY CHECK(id=1), actor TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')), actor TEXT, reason TEXT, entity TEXT, action TEXT, record_id INTEGER, before_data TEXT, after_data TEXT);
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

    def __init__(self,url,key):
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
            raise ValueError(f'Cloud request failed (HTTP {error.code}). Check sign-in, project setup and access policies. Sign in again if your session expired.') from None

    def login(self,email,password):
        result=self.request('/auth/v1/token?grant_type=password',{'email':email,'password':password})
        self.token=result['access_token'];self.owner=result['user']['id']

    def upload(self,path,expected):
        import base64,json,hashlib
        from pathlib import Path
        data=Path(path).read_bytes()
        if len(data)>self.MAX_DB:raise ValueError('Cloud backup supports databases up to 10 MiB in this version.')
        snapshot=json.dumps({'format':1,'sha256':hashlib.sha256(data).hexdigest(),'database':base64.b64encode(data).decode()})
        return self.request('/rest/v1/rpc/family_shop_upload',{'expected_version':expected,'snapshot':snapshot})

    def download(self,path):
        import base64,json,hashlib
        from pathlib import Path
        if not self.owner:raise ValueError('Sign in first.')
        rows=self.request('/rest/v1/family_shop_backups?select=version,payload,updated_at&owner=eq.'+self.owner)
        if not rows:raise ValueError('No cloud backup found for this account.')
        snapshot=json.loads(rows[0]['payload'])
        if snapshot.get('format')!=1:raise ValueError('Unsupported cloud backup format.')
        data=base64.b64decode(snapshot['database'],validate=True)
        if len(data)>self.MAX_DB or hashlib.sha256(data).hexdigest()!=snapshot['sha256']:raise ValueError('Backup integrity check failed.')
        Path(path).write_bytes(data)
        db=None
        try:
            db=sqlite3.connect(path)
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Cloud database is damaged.')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'products','periods','stock','receipts','cash'}.issubset(tables):raise ValueError('Not a Family Shop database.')
            if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Cloud database contains invalid references.')
        except sqlite3.DatabaseError:raise ValueError('Invalid cloud database.') from None
        finally:
            if db:db.close()
        return int(rows[0]['version'])


CLOUD_SETUP_SQL = "-- Run once in your dedicated Supabase project's SQL editor.\ncreate table if not exists public.family_shop_backups (\n  owner uuid primary key references auth.users(id) on delete cascade,\n  version bigint not null check (version > 0),\n  payload text not null check (octet_length(payload) <= 16000000),\n  updated_at timestamptz not null default now()\n);\nalter table public.family_shop_backups enable row level security;\nrevoke all on public.family_shop_backups from anon;\ngrant select, insert, update on public.family_shop_backups to authenticated;\ndrop policy if exists family_shop_owner on public.family_shop_backups;\ncreate policy family_shop_owner on public.family_shop_backups for all to authenticated\nusing ((select auth.uid()) = owner) with check ((select auth.uid()) = owner);\n\ncreate or replace function public.family_shop_upload(expected_version bigint, snapshot text)\nreturns bigint language plpgsql security invoker set search_path = '' as $$\ndeclare next_version bigint;\nbegin\n  if auth.uid() is null then raise exception 'Sign in required'; end if;\n  if expected_version < 0 or octet_length(snapshot)>16000000 then raise exception 'Invalid snapshot'; end if;\n  if expected_version = 0 then\n    insert into public.family_shop_backups(owner,version,payload)\n      values(auth.uid(),1,snapshot) on conflict do nothing returning version into next_version;\n  else\n    update public.family_shop_backups set version=version+1,payload=snapshot,updated_at=now()\n      where owner=auth.uid() and version=expected_version returning version into next_version;\n  end if;\n  if next_version is null then raise exception 'CLOUD_CONFLICT: Download the newer cloud copy before uploading'; end if;\n  return next_version;\nend $$;\nrevoke execute on function public.family_shop_upload(bigint,text) from public, anon;\ngrant execute on function public.family_shop_upload(bigint,text) to authenticated;\n"


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
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(script),'-ImagePath',str(source),'-OutputPath',str(output)],capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
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
