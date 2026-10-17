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

    def product(self, name, unit):
        if not name.strip() or not unit.strip():
            raise ValueError('Product name and unit are required.')
        with self.db:
            return self.db.execute('INSERT INTO products(name,unit) VALUES (?,?)', (name.strip(), unit.strip())).lastrowid

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

    def stock(self, period, product, opening, closing, drawings, broken, opening_cost, price):
        vals = [quantity(x) for x in (opening, closing, drawings, broken)]
        received = self.db.execute('SELECT COALESCE(SUM(units),0) FROM receipts WHERE period=? AND product=?', (period,product)).fetchone()[0]
        if vals[1]+vals[2]+vals[3] > vals[0]+received:
            raise ValueError('Closing stock, drawings and breakages exceed available units. Enter receipts first.')
        with self.db:
            self.db.execute('INSERT INTO stock(period,product,opening,closing,drawings,broken,opening_cost,price) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(period,product) DO UPDATE SET opening=excluded.opening,closing=excluded.closing,drawings=excluded.drawings,broken=excluded.broken,opening_cost=excluded.opening_cost,price=excluded.price', (period,product,*vals,money(opening_cost),money(price)))

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
        sales=cogs=loss=closing_value=Decimal(0)
        missing = self.db.execute('SELECT DISTINCT product FROM receipts WHERE period=? EXCEPT SELECT product FROM stock WHERE period=?', (period,period)).fetchall()
        if missing:
            raise ValueError('Complete stock counts for all products received before preparing reports.')
        for s in self.db.execute('SELECT s.*,p.name,p.unit FROM stock s JOIN products p ON p.id=s.product WHERE period=? ORDER BY p.name', (period,)):
            received, cost = self.db.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(goods+freight),0) FROM receipts WHERE period=? AND product=?', (period,s['product'])).fetchone()
            total=s['opening']+received
            sold=total-s['closing']-s['drawings']-s['broken']
            avg=Decimal(s['opening']*s['opening_cost']+cost)/total if total else Decimal(0)
            amount=sold*s['price']
            sales+=amount; cogs+=sold*avg; loss+=s['broken']*avg; closing_value+=s['closing']*avg
            rows.append([s['name'],s['unit'],s['opening'],received,total,s['closing'],s['drawings'],s['broken'],sold,f"{s['price']/100:.2f}",f'{amount/100:.2f}'])
        cash=self.db.execute('SELECT COALESCE(SUM(cash),0),COALESCE(SUM(ecocash),0),COALESCE(SUM(credit),0),COALESCE(SUM(cashout),0),COALESCE(SUM(expense),0) FROM cash WHERE period=?',(period,)).fetchone()
        accounted=sum(cash[:4])
        totals={'Stock-implied sales':sales,'Cash handed over':cash[0],'EcoCash sales receipts':cash[1],'Unpaid credit sales':cash[2],'Cash paid out from sales':cash[3],'Total accounted for':accounted,'Unreconciled difference (positive = short)':sales-accounted,'Cost of goods sold':cogs,'Gross profit':sales-cogs,'Breakage expense at cost':loss,'Operating expenses':cash[4],'Net profit before tax (stock-implied)':sales-cogs-loss-cash[4],'Closing inventory at cost':closing_value}
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
                units,cost=self.db.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(goods+freight),0) FROM receipts WHERE period=? AND product=?',(previous['id'],s['product'])).fetchone()
                available=s['opening']+units
                avg=Decimal(s['opening']*s['opening_cost']+cost)/available if available else Decimal(0)
                unit_cost=int(avg.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                self.db.execute('INSERT INTO stock(period,product,opening,closing,drawings,broken,opening_cost,price) VALUES (?,?,?,?,0,0,?,?)',(period,s['product'],s['closing'],s['closing'],unit_cost,s['price']))
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
        return warnings

    def install_controls(self):
        """Additive migration: log future changes and guard writes in locked periods."""
        import getpass
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS period_locks(period INTEGER PRIMARY KEY REFERENCES periods(id), reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS change_context(id INTEGER PRIMARY KEY CHECK(id=1), actor TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')), actor TEXT, reason TEXT, entity TEXT, action TEXT, record_id INTEGER, before_data TEXT, after_data TEXT);
        INSERT OR IGNORE INTO change_context VALUES (1,'Local user','Record saved');
        ''')
        self.db.execute('UPDATE change_context SET actor=? WHERE id=1',(getpass.getuser(),))
        for table in ['products','periods','stock','receipts','cash','orders','deliveries','customers','debts','repayments','period_locks']:
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
        for table in ['stock','receipts','cash','debts']:
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
            if delivery:self.db.execute('UPDATE deliveries SET units=? WHERE id=?',(units,delivery['id']))
            self.db.execute("UPDATE change_context SET reason='Record saved' WHERE id=1")


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
