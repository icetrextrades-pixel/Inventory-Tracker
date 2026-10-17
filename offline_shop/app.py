"""Family Shop — local desktop application, Python standard library only."""
import csv
import os
import subprocess
import sys
import threading
import queue
from pathlib import Path
from datetime import date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ledger import Ledger

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'FamilyShop'
DATA.mkdir(parents=True, exist_ok=True)


"""Offline printable HTML. All user text is escaped before rendering."""
from html import escape

COLUMNS=['Details','Unit','Opening','Receivings','Total stock','Closing','Drawings','Broken','Sold','Unit price','Total amount']


def table(headers,rows):
    def cell(value):return escape(str(value))
    return '<table><thead><tr>'+''.join('<th>'+cell(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def printable(ledger,period):
    rows,totals=ledger.report(period)
    dates=ledger.db.execute('SELECT start,end FROM periods WHERE id=?',(period,)).fetchone()
    if not dates:raise ValueError('Reporting period not found.')
    warnings=ledger.checks(period)
    balances=[[r['name'],f"{r['credit']/100:.2f}",f"{r['paid']/100:.2f}",f"{(r['credit']-r['paid'])/100:.2f}"] for r in ledger.customer_balances()]
    return '''<!doctype html><html><head><meta charset="utf-8"><title>Family Shop — stock and income report</title>
<style>body{font:14px Arial,sans-serif;color:#172b35;max-width:1300px;margin:30px auto;padding:0 18px}h1{color:#17685b}h2{margin-top:30px}table{border-collapse:collapse;width:100%;margin:15px 0}th,td{border:1px solid #cbd5da;padding:8px;text-align:right}th{background:#eaf4f0}td:first-child,th:first-child{text-align:left}.note{padding:12px;background:#fff4da}.sign{margin-top:40px;line-height:3}button{padding:10px 20px;cursor:pointer}@media print{button{display:none}body{font-size:10px;margin:0;max-width:none}th,td{padding:5px}thead{display:table-header-group}tr{break-inside:avoid}.sign{break-inside:avoid}@page{size:A4 landscape;margin:12mm}}</style></head><body>
<button onclick="window.print()">Print / Save as PDF</button><h1>FAMILY SHOP</h1>''' + f'<p>Stock and income report | {escape(dates[0])} to {escape(dates[1])} | USD</p>' + '<p class="note">Provisional report based on complete stock counts and supplied costs. Stock-implied sales may include unexplained losses; investigate the reconciliation difference. Customer balances below cover all recorded dates, not only this period.</p>'+ ('<h2>Checks requiring attention</h2><ul>'+''.join('<li>'+escape(w)+'</li>' for w in warnings)+'</ul>' if warnings else '')+'<h2>Stock sheet</h2>'+table(COLUMNS,rows)+'<h2>Reconciliation and income statement</h2>'+table(['Details','Amount USD'],totals.items())+'<p>Cost of goods sold uses periodic weighted-average cost, including allocated delivery costs. Drawings are excluded from sales and expenses. Unexplained cash differences are not automatically deducted from profit.</p><h2>Customer balances — all recorded dates</h2>'+table(['Customer','Credit sales USD','Repaid USD','Balance USD'],balances)+'<div class="sign">Prepared by: __________________________ &nbsp; Signature: __________________________<br>Checked by: __________________________ &nbsp; Signature: __________________________<br>Date: __________________________</div></body></html>'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Family Shop | Offline stock & accounts')
        self.geometry('1180x760')
        self.ledger = Ledger(DATA / 'shop.sqlite3')
        ttk.Label(self, text='FAMILY SHOP  •  v0.4', font=('Segoe UI', 24, 'bold')).pack(anchor='w', padx=24, pady=(20,4))
        ttk.Label(self, text='Stock • Receivings • Cash balance • Income statement | All records stay on this computer').pack(anchor='w',padx=24)
        bar=ttk.Frame(self); bar.pack(fill='x',padx=24,pady=14)
        ttk.Label(bar,text='Reporting period:').pack(side='left')
        self.period=ttk.Combobox(bar,state='readonly',width=34); self.period.pack(side='left',padx=8)
        self.period.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(bar,text='New period',command=self.new_period).pack(side='left')
        self.update_button=ttk.Button(bar,text='Update App',command=self.check_update)
        self.update_button.pack(side='right',padx=8)
        ttk.Button(bar,text='Backup database',command=self.backup).pack(side='right')
        self.tabs=ttk.Notebook(self); self.tabs.pack(expand=True,fill='both',padx=24,pady=8)
        actions=ttk.Frame(self.tabs,padding=20); self.tabs.add(actions,text='Enter records')
        for label,action,helptext in [
            ('1. Add product',self.product,'Give each product a name and unit, such as bottle, packet or individual sweet.'),
            ('2. Record goods received',self.receipt,'Enter supplier, invoice, individual units, goods cost and delivery cost. Each entry is a received order line.'),
            ('3. Enter / update stock count',self.stock,'Opening + receipts − closing − drawings − broken units = stock-implied units sold.'),
            ('4. Enter / update daily money',self.cash,'Cash handed over, EcoCash, unpaid credit and cash paid out from sales. A date is saved once and can be updated.')]:
            ttk.Button(actions,text=label,command=action,width=34).pack(anchor='w',pady=(14,4))
            ttk.Label(actions,text=helptext,wraplength=950).pack(anchor='w')
        ttk.Label(actions,text='One currency per database (default USD). Enter whole individual units. Complete every product count for a reliable report.\nCash paid out includes expenses/purchases paid from sales cash; record operating expenses separately for profit.\nCredit repayments, float, capital and transfers must not be entered as new sales receipts.',wraplength=950).pack(anchor='w',pady=30)
        report=ttk.Frame(self.tabs); self.tabs.add(report,text='Stock sheet & income statement')
        top=ttk.Frame(report);top.pack(fill='x',pady=8)
        ttk.Button(top,text='Refresh report',command=self.refresh).pack(side='left')
        ttk.Button(top,text='Print / Save PDF',command=self.print_report).pack(side='right')
        ttk.Button(top,text='Export stock CSV',command=lambda:self.export('stock')).pack(side='left',padx=8)
        ttk.Button(top,text='Export statement CSV',command=lambda:self.export('statement')).pack(side='left')
        self.columns=['Details','Unit','Opening','Receivings','Total stock','Closing','Drawings','Broken','Sold','Unit price','Total amount']
        self.tree=ttk.Treeview(report,columns=self.columns,show='headings',height=12)
        for col in self.columns:
            self.tree.heading(col,text=col);self.tree.column(col,width=90,minwidth=70,anchor='e' if col not in ['Details','Unit'] else 'w')
        self.tree.column('Details',width=150)
        scroll=ttk.Scrollbar(report,orient='horizontal',command=self.tree.xview);self.tree.configure(xscrollcommand=scroll.set)
        self.tree.pack(fill='both',expand=True);scroll.pack(fill='x')
        self.summary=tk.Text(report,height=15,font=('Consolas',11),state='disabled');self.summary.pack(fill='both',expand=True,pady=8)
        self.log=ttk.Frame(self.tabs); self.tabs.add(self.log,text='Received orders & daily money')
        ttk.Label(self.log,text='Goods received — selected period').pack(anchor='w',pady=6)
        self.receipt_table=self.register_table(self.log,['Date','Product','Supplier','Invoice','Units','Goods USD','Delivery USD'])
        ttk.Label(self.log,text='Daily money — selected period').pack(anchor='w',pady=6)
        self.cash_table=self.register_table(self.log,['Date','Cash USD','EcoCash USD','Credit USD','Paid out USD','Expenses USD','Notes'])
        ttk.Label(self,text=f'Data: {DATA} | Back up regularly. No cloud sync or internet connection required.').pack(anchor='w',padx=24,pady=8)
        self.build_operations()
        self.reload_periods()

    def reload_periods(self):
        self.periods={f"{r['start']} to {r['end']}":r['id'] for r in self.ledger.db.execute('SELECT * FROM periods ORDER BY start DESC')}
        self.period['values']=list(self.periods)
        if self.periods:self.period.current(0)
        self.refresh()

    def pid(self):
        if self.period.get() not in self.periods:raise ValueError('Create and select a reporting period first.')
        return self.periods[self.period.get()]

    def form(self,title,fields,save,loader=None):
        win=tk.Toplevel(self);win.title(title);win.transient(self);win.grab_set()
        values={}
        for i,(label,default,choices) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky='w',padx=16,pady=6)
            v=tk.StringVar(value=default); values[label]=v
            widget=ttk.Combobox(win,textvariable=v,values=choices,state='readonly',width=42) if choices is not None else ttk.Entry(win,textvariable=v,width=45)
            widget.grid(row=i,column=1,padx=16,pady=6)
        if loader:
            def load_existing(*_):
                for key,value in loader({k:v.get() for k,v in values.items()}).items():
                    values[key].set(value)
            for key in ('Product','Date YYYY-MM-DD'):
                if key in values: values[key].trace_add('write',load_existing)
            load_existing()
        def submit():
            try:save({k:v.get() for k,v in values.items()});win.destroy();self.refresh()
            except Exception as e:messagebox.showerror('Please check',str(e),parent=win)
        ttk.Button(win,text='Save record',command=submit).grid(row=len(fields),column=1,sticky='e',padx=16,pady=16)

    def product(self):
        self.form('Add product',[('Product name','',None),('Unit','each',None)],lambda v:self.ledger.product(v['Product name'],v['Unit']))

    def product_form(self,title,fields,save,loader=None):
        try:
            p=self.pid()
            products={r['name']:r['id'] for r in self.ledger.db.execute('SELECT * FROM products ORDER BY name')}
            if not products:raise ValueError('Add a product first.')
            self.form(title,[('Product',next(iter(products)),list(products))]+[(x,d,None) for x,d in fields],lambda v:save(p,products[v.pop('Product')],list(v.values())),loader=(lambda v:loader(p,products[v['Product']])) if loader else None)
        except Exception as e:messagebox.showerror('Please check',str(e))

    def new_period(self):
        today=date.today().isoformat()
        self.form('Create reporting period',[('Start date YYYY-MM-DD',today,None),('End date YYYY-MM-DD',today,None)],lambda v:(self.ledger.period(*v.values()),self.reload_periods()))

    def receipt(self):
        self.product_form('Goods received (one order line)', [('Date YYYY-MM-DD',date.today().isoformat()),('Supplier',''),('Invoice / order reference',''),('Individual units received','0'),('Total goods cost','0'),('Delivery cost for this line','0')],lambda p,i,v:self.ledger.receipt(p,i,*v))

    def stock(self):
        self.product_form('Save complete stock count (replaces existing count)', [('Opening units','0'),('Closing units','0'),('Drawings units','0'),('Broken units','0'),('Opening cost per unit','0'),('Selling price per unit','0')],lambda p,i,v:self.ledger.stock(p,i,*v),loader=self.stock_defaults)

    def cash(self):
        try:p=self.pid()
        except ValueError as e:messagebox.showerror('Please check',str(e));return
        self.form('Daily money (replaces existing date)',[(x,d,None) for x,d in [('Date YYYY-MM-DD',date.today().isoformat()),('Cash handed over','0'),('EcoCash sales receipts','0'),('Unpaid credit sales','0'),('Cash paid out from sales','0'),('Operating expenses','0'),('Notes / prepared by','')]],lambda v:self.ledger.cash(p,*v.values()),loader=lambda v:self.cash_defaults(p,v))

    def refresh(self):
        if not hasattr(self,'tree'):return
        self.tree.delete(*self.tree.get_children())
        try:
            p=self.pid();rows,totals=self.ledger.report(p)
            for row in rows:self.tree.insert('','end',values=row)
            text='\n'.join(f'{k:<48} $ {v:>12}' for k,v in totals.items())
            text+='\n\nProfit uses periodic weighted-average cost, including delivery. Drawings are excluded from sales.\nStock-implied profit is provisional: investigate the cash difference; it is not automatically an expense.\nPrepared by: __________________  Checked by: __________________  Signature: __________________'
            warnings=self.ledger.checks(p)
            if warnings:text+='\n\nCHECKS REQUIRING ATTENTION\n'+'\n'.join(warnings)
        except ValueError as e:text=str(e)
        self.refresh_registers()
        self.refresh_operations()
        self.summary.configure(state='normal');self.summary.delete('1.0','end');self.summary.insert('end',text);self.summary.configure(state='disabled')

    def export(self,kind):
        try:
            rows,totals=self.ledger.report(self.pid())
            target=filedialog.asksaveasfilename(defaultextension='.csv',initialfile=f'{kind}.csv')
            if target:
                with open(target,'w',newline='',encoding='utf-8-sig') as f:
                    writer=csv.writer(f)
                    def safe(row):return [('\''+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for v in row]
                    writer.writerow(self.columns if kind=='stock' else ['Details','Amount USD'])
                    writer.writerows(safe(r) for r in (rows if kind=='stock' else totals.items()))
        except Exception as e:messagebox.showerror('Export failed',str(e))

    def stock_defaults(self,p,i):
        row=self.ledger.db.execute('SELECT * FROM stock WHERE period=? AND product=?',(p,i)).fetchone()
        keys=['Opening units','Closing units','Drawings units','Broken units','Opening cost per unit','Selling price per unit']
        if not row:return dict.fromkeys(keys,'0')
        return dict(zip(keys,[row['opening'],row['closing'],row['drawings'],row['broken'],f"{row['opening_cost']/100:.2f}",f"{row['price']/100:.2f}"]))

    def cash_defaults(self,p,v):
        row=self.ledger.db.execute('SELECT * FROM cash WHERE period=? AND day=?',(p,v['Date YYYY-MM-DD'])).fetchone()
        keys=['Cash handed over','EcoCash sales receipts','Unpaid credit sales','Cash paid out from sales','Operating expenses','Notes / prepared by']
        return dict(zip(keys,([f"{row[k]/100:.2f}" for k in ['cash','ecocash','credit','cashout','expense']]+[row['note']]) if row else ['0']*5+['']))

    def build_operations(self):
        frame=ttk.Frame(self.tabs,padding=16);self.tabs.add(frame,text='Orders & customer credit')
        for label,command in [('Create purchase order',self.new_order),('Receive order / partial delivery',self.deliver),('Record customer credit sale',self.new_debt),('Record debt repayment',self.repayment),('Bring forward previous closing stock',self.carry)]:
            ttk.Button(frame,text=label,command=command).pack(anchor='w',pady=4)
        ttk.Label(frame,text='Customer credit is a separate supporting register: enter the period’s unpaid sales in Daily money too.\nRepayments reduce customer debt only; exclude old debt collections from daily sales cash/EcoCash.\nCarry-forward starts closing quantities equal to opening: update actual closing counts before reporting.',wraplength=950).pack(anchor='w',pady=12)
        self.operations=tk.Text(frame,height=9,font=('Consolas',10),wrap='none');self.operations.pack(expand=True,fill='both')
        ttk.Label(frame,text='Customer balances — all recorded dates').pack(anchor='w',pady=6)
        self.customer_table=self.register_table(frame,['Customer','Credit sales USD','Repaid USD','Balance USD'])

    def refresh_operations(self):
        if not hasattr(self,'operations'):return
        db=self.ledger.db
        self.orders={}
        text='PURCHASE ORDERS — all periods\n'
        for r in db.execute('SELECT o.*,p.name,COALESCE((SELECT SUM(units) FROM deliveries WHERE order_id=o.id),0) received FROM orders o JOIN products p ON p.id=o.product ORDER BY o.id DESC'):
            remaining=r['units']-r['received']
            label=f"#{r['id']} {r['reference']} | {r['name']} | outstanding {remaining}"
            if remaining:self.orders[label]=r['id']
            text+=f"{label} | {r['supplier']} | ordered {r['units']} | received {r['received']} | estimate ${r['estimated']/100:.2f}\n"
        self.debts={};text+='\nCUSTOMER DEBTS — all periods\n'
        for r in db.execute('SELECT d.*,c.name,COALESCE((SELECT SUM(amount) FROM repayments WHERE debt=d.id),0) paid FROM debts d JOIN customers c ON c.id=d.customer ORDER BY d.id DESC'):
            balance=r['amount']-r['paid'];label=f"#{r['id']} {r['name']} | {r['day']} | balance ${balance/100:.2f}"
            if balance:self.debts[label]=r['id']
            text+=f"{label} | original ${r['amount']/100:.2f} | paid ${r['paid']/100:.2f}\n"
        text+='\nREPAYMENTS\n'
        for r in db.execute('SELECT * FROM repayments ORDER BY day,id'):
            text+=f"{r['day']} | debt #{r['debt']} | {r['method']} | ${r['amount']/100:.2f}\n"
        self.operations.delete('1.0','end');self.operations.insert('end',text)
        self.customer_table.delete(*self.customer_table.get_children())
        for r in self.ledger.customer_balances():
            self.customer_table.insert('','end',values=[r['name'],f"{r['credit']/100:.2f}",f"{r['paid']/100:.2f}",f"{(r['credit']-r['paid'])/100:.2f}"])

    def new_order(self):
        self.product_form('Purchase order',[('Supplier',''),('Order reference',''),('Order date',date.today().isoformat()),('Units ordered','1'),('Estimated total cost','0')],lambda p,i,v:self.ledger.order(i,*v))

    def deliver(self):
        try:
            p=self.pid()
            if not self.orders:raise ValueError('No outstanding orders.')
            self.form('Receive an order',[('Order',next(iter(self.orders)),list(self.orders))]+[(k,d,None) for k,d in [('Delivery date',date.today().isoformat()),('Units received','1'),('Goods cost for this delivery','0'),('Delivery cost for this delivery','0')]],lambda v:self.ledger.receive_order(self.orders[v.pop('Order')],p,*v.values()))
        except ValueError as e:messagebox.showerror('Please check',str(e))

    def new_debt(self):
        try:p=self.pid()
        except ValueError as e:messagebox.showerror('Please check',str(e));return
        self.form('Customer credit sale',[(k,d,None) for k,d in [('Customer name',''),('Sale date',date.today().isoformat()),('Credit amount','0'),('Note / reference','')]],lambda v:self.ledger.debt(v['Customer name'],p,v['Sale date'],v['Credit amount'],v['Note / reference']))

    def repayment(self):
        if not self.debts:messagebox.showinfo('Customer credit','No unpaid debts.');return
        self.form('Debt repayment',[('Debt',next(iter(self.debts)),list(self.debts)),('Payment date',date.today().isoformat(),None),('Amount','0',None),('Method','Cash',['Cash','EcoCash'])],lambda v:self.ledger.repay(self.debts[v['Debt']],v['Payment date'],v['Amount'],v['Method']))

    def carry(self):
        try:
            p=self.pid()
            self.ledger.backup(DATA / f'before-carry-{p}.sqlite3')
            start,end=self.ledger.carry_forward(p);self.refresh()
            messagebox.showinfo('Stock brought forward',f'Copied closing stock from {start} to {end}. Update actual closing quantities before reporting.')
        except Exception as e:messagebox.showerror('Please check',str(e))

    def register_table(self,parent,columns):
        box=ttk.Frame(parent);box.pack(expand=True,fill='both')
        tree=ttk.Treeview(box,columns=columns,show='headings',height=6)
        for col in columns:
            tree.heading(col,text=col);tree.column(col,width=140,minwidth=80)
        vertical=ttk.Scrollbar(box,orient='vertical',command=tree.yview)
        horizontal=ttk.Scrollbar(box,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        box.rowconfigure(0,weight=1);box.columnconfigure(0,weight=1)
        return tree

    def refresh_registers(self):
        for tree in (self.receipt_table,self.cash_table):tree.delete(*tree.get_children())
        try:p=self.pid()
        except ValueError:return
        for r in self.ledger.db.execute('SELECT r.*,p.name FROM receipts r JOIN products p ON p.id=r.product WHERE period=? ORDER BY day,r.id',(p,)):
            self.receipt_table.insert('','end',values=[r['day'],r['name'],r['supplier'],r['reference'],r['units'],f"{r['goods']/100:.2f}",f"{r['freight']/100:.2f}"])
        for r in self.ledger.db.execute('SELECT * FROM cash WHERE period=? ORDER BY day',(p,)):
            self.cash_table.insert('','end',values=[r['day']]+[f"{r[k]/100:.2f}" for k in ['cash','ecocash','credit','cashout','expense']]+[r['note']])

    def print_report(self):
        try:
            import tempfile
            import webbrowser
            html=printable(self.ledger,self.pid())
            folder=DATA/'reports';folder.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',suffix='.html',prefix='shop-report-',dir=folder,encoding='utf-8',delete=False) as output:
                output.write(html);path=Path(output.name)
            if not webbrowser.open(path.as_uri()):
                messagebox.showinfo('Report saved',f'Open this report in your browser to print or save PDF:\n{path}')
        except Exception as exc:messagebox.showerror('Report could not be prepared',str(exc))

    def check_update(self):
        self.update_button.configure(state='disabled',text='Checking…')
        results=queue.Queue()
        def worker():
            try:
                from updater import remote_version
                results.put((True,remote_version()))
            except Exception as exc:results.put((False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            try:ok,result=results.get_nowait()
            except queue.Empty:self.after(150,poll);return
            self.update_button.configure(state='normal',text='Update App')
            if not ok:
                messagebox.showerror('Could not check updates',f'{result}\nConnect to the internet and try again.');return
            root=Path(__file__).resolve().parent
            version=root/'installed-version.txt'
            if version.exists() and version.read_text().strip()==result:
                messagebox.showinfo('Up to date','You already have the latest version.');return
            if not messagebox.askyesno('Install update','Download the latest Family Shop version? Your records will be backed up and the app will restart. Close other Family Shop windows first.'):
                return
            try:
                subprocess.Popen([sys.executable,str(root/'updater.py'),result],cwd=root)
                self.ledger.db.close();self.destroy()
            except Exception as exc:messagebox.showerror('Update could not start',str(exc))
        self.after(150,poll)

    def backup(self):
        target=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile=f'shop-backup-{date.today()}.sqlite3')
        if target:
            try:
                if Path(target).resolve()==(DATA/'shop.sqlite3').resolve():raise ValueError('Choose a different file from the live database.')
                self.ledger.backup(target);messagebox.showinfo('Backup saved','Keep the backup on a separate drive. Restore with the app closed by copying it over the data file shown below.')
            except Exception as e:messagebox.showerror('Backup failed',str(e))


if __name__=='__main__':
    App().mainloop()
