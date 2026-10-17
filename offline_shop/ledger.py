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
