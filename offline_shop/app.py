"""Family Shop — local desktop application, Python standard library only."""
import csv
import os
from pathlib import Path
from datetime import date
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ledger import Ledger

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'FamilyShop'
DATA.mkdir(parents=True, exist_ok=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Family Shop | Offline stock & accounts')
        self.geometry('1180x760')
        self.ledger = Ledger(DATA / 'shop.sqlite3')
        ttk.Label(self, text='FAMILY SHOP', font=('Segoe UI', 24, 'bold')).pack(anchor='w', padx=24, pady=(20,4))
        ttk.Label(self, text='Stock • Receivings • Cash balance • Income statement | All records stay on this computer').pack(anchor='w',padx=24)
        bar=ttk.Frame(self); bar.pack(fill='x',padx=24,pady=14)
        ttk.Label(bar,text='Reporting period:').pack(side='left')
        self.period=ttk.Combobox(bar,state='readonly',width=34); self.period.pack(side='left',padx=8)
        self.period.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(bar,text='New period',command=self.new_period).pack(side='left')
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
        self.logtext=tk.Text(self.log,wrap='none',font=('Consolas',10));self.logtext.pack(fill='both',expand=True)
        ttk.Label(self,text=f'Data: {DATA} | Back up regularly. No cloud sync or internet connection required.').pack(anchor='w',padx=24,pady=8)
        self.reload_periods()

    def reload_periods(self):
        self.periods={f"{r['start']} to {r['end']}":r['id'] for r in self.ledger.db.execute('SELECT * FROM periods ORDER BY start DESC')}
        self.period['values']=list(self.periods)
        if self.periods:self.period.current(0)
        self.refresh()

    def pid(self):
        if self.period.get() not in self.periods:raise ValueError('Create and select a reporting period first.')
        return self.periods[self.period.get()]

    def form(self,title,fields,save):
        win=tk.Toplevel(self);win.title(title);win.transient(self);win.grab_set()
        values={}
        for i,(label,default,choices) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky='w',padx=16,pady=6)
            v=tk.StringVar(value=default); values[label]=v
            widget=ttk.Combobox(win,textvariable=v,values=choices,state='readonly',width=42) if choices is not None else ttk.Entry(win,textvariable=v,width=45)
            widget.grid(row=i,column=1,padx=16,pady=6)
        def submit():
            try:save({k:v.get() for k,v in values.items()});win.destroy();self.refresh()
            except Exception as e:messagebox.showerror('Please check',str(e),parent=win)
        ttk.Button(win,text='Save record',command=submit).grid(row=len(fields),column=1,sticky='e',padx=16,pady=16)

    def product(self):
        self.form('Add product',[('Product name','',None),('Unit','each',None)],lambda v:self.ledger.product(v['Product name'],v['Unit']))

    def product_form(self,title,fields,save):
        try:
            p=self.pid()
            products={r['name']:r['id'] for r in self.ledger.db.execute('SELECT * FROM products ORDER BY name')}
            if not products:raise ValueError('Add a product first.')
            self.form(title,[('Product',next(iter(products)),list(products))]+[(x,d,None) for x,d in fields],lambda v:save(p,products[v.pop('Product')],list(v.values())))
        except Exception as e:messagebox.showerror('Please check',str(e))

    def new_period(self):
        today=date.today().isoformat()
        self.form('Create reporting period',[('Start date YYYY-MM-DD',today,None),('End date YYYY-MM-DD',today,None)],lambda v:(self.ledger.period(*v.values()),self.reload_periods()))

    def receipt(self):
        self.product_form('Goods received (one order line)', [('Date YYYY-MM-DD',date.today().isoformat()),('Supplier',''),('Invoice / order reference',''),('Individual units received','0'),('Total goods cost','0'),('Delivery cost for this line','0')],lambda p,i,v:self.ledger.receipt(p,i,*v))

    def stock(self):
        self.product_form('Save complete stock count (replaces existing count)', [('Opening units','0'),('Closing units','0'),('Drawings units','0'),('Broken units','0'),('Opening cost per unit','0'),('Selling price per unit','0')],lambda p,i,v:self.ledger.stock(p,i,*v))

    def cash(self):
        try:p=self.pid()
        except ValueError as e:messagebox.showerror('Please check',str(e));return
        self.form('Daily money (replaces existing date)',[(x,d,None) for x,d in [('Date YYYY-MM-DD',date.today().isoformat()),('Cash handed over','0'),('EcoCash sales receipts','0'),('Unpaid credit sales','0'),('Cash paid out from sales','0'),('Operating expenses','0'),('Notes / prepared by','')]],lambda v:self.ledger.cash(p,*v.values()))

    def refresh(self):
        if not hasattr(self,'tree'):return
        self.tree.delete(*self.tree.get_children())
        try:
            p=self.pid();rows,totals=self.ledger.report(p)
            for row in rows:self.tree.insert('','end',values=row)
            text='\n'.join(f'{k:<48} $ {v:>12}' for k,v in totals.items())
            text+='\n\nProfit uses periodic weighted-average cost, including delivery. Drawings are excluded from sales.\nStock-implied profit is provisional: investigate the cash difference; it is not automatically an expense.\nPrepared by: __________________  Checked by: __________________  Signature: __________________'
            self.logtext.delete('1.0','end')
            for table in ['receipts','cash']:
                self.logtext.insert('end',table.upper()+'\n')
                for r in self.ledger.db.execute(f'SELECT * FROM {table} WHERE period=? ORDER BY day,id',(p,)):
                    self.logtext.insert('end',str(dict(r))+'\n')
                self.logtext.insert('end','\nAmounts in this register are stored as cents. Product IDs refer to the product list.\n\n')
        except ValueError as e:text=str(e)
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

    def backup(self):
        target=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile=f'shop-backup-{date.today()}.sqlite3')
        if target:
            try:
                if Path(target).resolve()==(DATA/'shop.sqlite3').resolve():raise ValueError('Choose a different file from the live database.')
                self.ledger.backup(target);messagebox.showinfo('Backup saved','Keep the backup on a separate drive. Restore with the app closed by copying it over the data file shown below.')
            except Exception as e:messagebox.showerror('Backup failed',str(e))


if __name__=='__main__':
    App().mainloop()
