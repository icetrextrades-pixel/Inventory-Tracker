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
        self.geometry('1280x850')
        self.minsize(1060,720)
        self.apply_theme()
        self.ledger = Ledger(DATA / 'shop.sqlite3')
        sidebar=tk.Frame(self,bg='#142d32',width=196)
        sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        tk.Label(sidebar,text='FAMILY\nSHOP',font=('Segoe UI',24,'bold'),bg='#142d32',fg='#ffffff',justify='left').pack(anchor='w',padx=24,pady=(30,4))
        tk.Label(sidebar,text='YOUR DAILY BUSINESS',font=('Segoe UI',8,'bold'),bg='#142d32',fg='#8cb9b6').pack(anchor='w',padx=24,pady=(0,32))
        self.nav_buttons=[]
        for index,label in enumerate(['Overview','Stock & reports','Daily registers','Orders & credit','History & controls','Online backup']):
            button=tk.Button(sidebar,text=label,anchor='w',font=('Segoe UI',11),bg='#142d32',fg='#c9dcdd',activebackground='#23545a',activeforeground='white',relief='flat',borderwidth=0,padx=22,pady=14,cursor='hand2',command=lambda i=index:self.navigate(i))
            button.pack(fill='x',padx=10,pady=3);self.nav_buttons.append(button)
        tk.Label(sidebar,text='●  OFFLINE READY\nv0.7  •  Local records',font=('Segoe UI',10),bg='#142d32',fg='#9fdac5',justify='left').pack(side='bottom',anchor='w',padx=24,pady=26)
        workspace=ttk.Frame(self,padding=(24,20));workspace.pack(side='left',fill='both',expand=True)
        header=ttk.Frame(workspace);header.pack(fill='x',pady=(0,16))
        self.page_title=ttk.Label(header,text='Your shop, at a glance',style='Title.TLabel');self.page_title.pack(anchor='w')
        ttk.Label(header,text='A clear view of your stock, money and customers.',style='Muted.TLabel').pack(anchor='w',pady=(4,0))
        bar=ttk.Frame(workspace); bar.pack(fill='x',pady=(0,18))
        ttk.Label(bar,text='Reporting period:').pack(side='left')
        self.period=ttk.Combobox(bar,state='readonly',width=34); self.period.pack(side='left',padx=8)
        self.period.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(bar,text='New period',command=self.new_period).pack(side='left')
        self.update_button=ttk.Button(bar,text='Update App',command=self.check_update)
        self.update_button.pack(side='right',padx=8)
        ttk.Button(bar,text='Backup database',command=self.backup).pack(side='right')
        self.tabs=ttk.Notebook(workspace,style='Workspace.TNotebook'); self.tabs.pack(expand=True,fill='both')
        actions=ttk.Frame(self.tabs); self.tabs.add(actions,text='Overview')
        metrics=ttk.Frame(actions);metrics.pack(fill='x',pady=(0,18))
        self.metric_values={}
        for column,(key,label) in enumerate([('Stock-implied sales','ESTIMATED SALES'),('Net profit before tax (stock-implied)','PROVISIONAL PROFIT'),('Unreconciled difference (positive = short)','UNEXPLAINED DIFFERENCE')]):
            card=ttk.Frame(metrics,style='Card.TFrame',padding=16);card.grid(row=0,column=column,sticky='nsew',padx=(0,10 if column<2 else 0));metrics.columnconfigure(column,weight=1)
            ttk.Label(card,text=label,style='CardCaption.TLabel').pack(anchor='w')
            value=ttk.Label(card,text='—',style='Metric.TLabel');value.pack(anchor='w',pady=(8,0));self.metric_values[key]=value
        ttk.Label(actions,text='Daily essentials',style='Section.TLabel').pack(anchor='w',pady=(4,12))
        cards=ttk.Frame(actions);cards.pack(fill='x')
        for i,(title,detail,button,command) in enumerate([
            ('Products','Set up products and the units you count.','Add product',self.product),
            ('Goods received','Record supplier deliveries and purchase costs.','Record delivery',self.receipt),
            ('Stock counts','Enter opening, closing, drawings and breakages.','Update stock',self.stock),
            ('Daily money','Balance cash, EcoCash, credit and cash paid out.','Enter daily money',self.cash)]):
            card=ttk.Frame(cards,style='Card.TFrame',padding=20);card.grid(row=i//2,column=i%2,sticky='nsew',padx=(0,12 if i%2==0 else 0),pady=(0,12));cards.columnconfigure(i%2,weight=1)
            ttk.Label(card,text=title,style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(card,text=detail,style='CardBody.TLabel',wraplength=310).pack(anchor='w',pady=(8,18))
            ttk.Button(card,text=button,command=command,style='Accent.TButton').pack(anchor='w')
        ttk.Label(actions,text='Keep your numbers reliable',style='Section.TLabel').pack(anchor='w',pady=(10,8))
        ttk.Label(actions,text='Count individual units and include purchase costs. Profit stays provisional until stock and money agree.\nKeep old debt collections separate from new sales. Back up your records regularly.',style='Muted.TLabel',wraplength=780).pack(anchor='w')
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
        self.summary=tk.Text(report,height=12,font=('Consolas',10),state='disabled',bg='#ffffff',fg='#244047',relief='flat',padx=16,pady=14,highlightthickness=1,highlightbackground='#dde6e6');self.summary.pack(fill='both',expand=True,pady=8)
        self.log=ttk.Frame(self.tabs); self.tabs.add(self.log,text='Received orders & daily money')
        ttk.Label(self.log,text='Goods received — selected period').pack(anchor='w',pady=6)
        self.receipt_table=self.register_table(self.log,['Date','Product','Supplier','Invoice','Units','Goods USD','Delivery USD'])
        ttk.Label(self.log,text='Daily money — selected period').pack(anchor='w',pady=6)
        self.cash_table=self.register_table(self.log,['Date','Cash USD','EcoCash USD','Credit USD','Paid out USD','Expenses USD','Notes'])
        ttk.Label(workspace,text='Saved on this computer  •  USD  •  Back up regularly',style='Muted.TLabel').pack(anchor='w',pady=(12,0))
        self.build_operations()
        self.build_controls()
        self.build_cloud()
        self.reload_periods()
        self.navigate(0)

    def apply_theme(self):
        self.configure(bg='#f2f6f6')
        self.option_add('*Font',('Segoe UI',10))
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background='#f2f6f6',foreground='#193b41')
        style.configure('TFrame',background='#f2f6f6')
        style.configure('TLabel',background='#f2f6f6',foreground='#193b41')
        style.configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        style.configure('Section.TLabel',font=('Segoe UI',13,'bold'))
        style.configure('Muted.TLabel',foreground='#627c80',font=('Segoe UI',10))
        style.configure('Card.TFrame',background='white',relief='flat')
        for name,font,color in [('CardCaption.TLabel',('Segoe UI',8,'bold'),'#627c80'),('Metric.TLabel',('Segoe UI',21,'bold'),'#176c60'),('CardTitle.TLabel',('Segoe UI',14,'bold'),'#193b41'),('CardBody.TLabel',('Segoe UI',10),'#627c80')]:
            style.configure(name,background='white',font=font,foreground=color)
        style.configure('TButton',padding=(12,9),background='#e2eeee',foreground='#23494c',borderwidth=0)
        style.map('TButton',background=[('active','#d0e5e1'),('disabled','#edf1f1')])
        style.configure('Accent.TButton',background='#167565',foreground='white',padding=(16,10))
        style.map('Accent.TButton',background=[('active','#105f52')],foreground=[('active','white')])
        style.configure('TEntry',fieldbackground='white',padding=7)
        style.configure('TCombobox',fieldbackground='white',padding=7)
        style.configure('Treeview',background='white',fieldbackground='white',foreground='#25464b',rowheight=32,borderwidth=0)
        style.configure('Treeview.Heading',background='#e4eeee',foreground='#385c61',padding=(8,10),font=('Segoe UI',9,'bold'),relief='flat')
        style.map('Treeview',background=[('selected','#d0eae2')],foreground=[('selected','#124b40')])
        style.configure('Workspace.TNotebook',background='#f2f6f6',borderwidth=0,tabmargins=0)
        style.layout('Workspace.TNotebook.Tab',[])

    def navigate(self,index):
        self.tabs.select(index)
        self.page_title.configure(text=['Your shop, at a glance','Stock & financial reports','Daily registers','Orders & customer credit','History & period controls','Online backup & restore'][index])
        for i,button in enumerate(self.nav_buttons):
            button.configure(bg='#23545a' if i==index else '#142d32',fg='white' if i==index else '#c9dcdd')

    def reload_periods(self):
        self.periods={f"{r['start']} to {r['end']}":r['id'] for r in self.ledger.db.execute('SELECT * FROM periods ORDER BY start DESC')}
        self.period['values']=list(self.periods)
        if self.periods:self.period.current(0)
        self.refresh()

    def pid(self):
        if self.period.get() not in self.periods:raise ValueError('Create and select a reporting period first.')
        return self.periods[self.period.get()]

    def form(self,title,fields,save,loader=None):
        win=tk.Toplevel(self);win.title(title);win.transient(self);win.grab_set();win.configure(bg='#f2f6f6')
        win.resizable(False,False)
        win.geometry(f'+{self.winfo_rootx()+220}+{self.winfo_rooty()+100}')
        values={}
        for i,(label,default,choices) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky='w',padx=16,pady=6)
            v=tk.StringVar(value=default); values[label]=v
            widget=ttk.Combobox(win,textvariable=v,values=choices,state='readonly',width=42) if choices is not None else ttk.Entry(win,textvariable=v,width=45)
            if 'password' in label.lower():widget.configure(show='•')
            widget.grid(row=i,column=1,padx=16,pady=6)
        if loader:
            def load_existing(*_):
                for key,value in loader({k:v.get() for k,v in values.items()}).items():
                    values[key].set(value)
            for key in ('Product','Date YYYY-MM-DD','Receipt'):
                if key in values: values[key].trace_add('write',load_existing)
            load_existing()
        def submit():
            try:save({k:v.get() for k,v in values.items()});win.destroy();self.refresh()
            except Exception as e:messagebox.showerror('Please check',str(e),parent=win)
        ttk.Button(win,text='Save record',command=submit,style='Accent.TButton').grid(row=len(fields),column=1,sticky='e',padx=16,pady=16)

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
        try:
            _,metrics=self.ledger.report(self.pid())
            for key,label in self.metric_values.items():label.configure(text='$ '+metrics[key])
        except ValueError:
            for label in self.metric_values.values():label.configure(text='—')
        self.refresh_controls()
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
        toolbar=ttk.Frame(frame);toolbar.pack(fill='x',pady=(0,8))
        for i,(label,command) in enumerate([('Create purchase order',self.new_order),('Receive order / partial delivery',self.deliver),('Record customer credit sale',self.new_debt),('Record debt repayment',self.repayment),('Bring forward previous closing stock',self.carry)]):
            ttk.Button(toolbar,text=label,command=command).grid(row=i//3,column=i%3,sticky='w',padx=(0,8),pady=4)
        ttk.Label(frame,text='Customer credit is a separate supporting register: enter the period’s unpaid sales in Daily money too.\nRepayments reduce customer debt only; exclude old debt collections from daily sales cash/EcoCash.\nCarry-forward starts closing quantities equal to opening: update actual closing counts before reporting.',wraplength=950).pack(anchor='w',pady=12)
        self.operations=tk.Text(frame,height=7,font=('Consolas',10),wrap='none',bg='#ffffff',fg='#244047',relief='flat',padx=12,pady=12);self.operations.pack(expand=True,fill='both')
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

    def build_controls(self):
        frame=ttk.Frame(self.tabs,padding=12);self.tabs.add(frame,text='History & controls')
        self.lock_status=ttk.Label(frame,text='',style='Section.TLabel');self.lock_status.pack(anchor='w',pady=(0,12))
        toolbar=ttk.Frame(frame);toolbar.pack(fill='x')
        ttk.Button(toolbar,text='Lock / reopen period',command=self.toggle_lock).pack(side='left',padx=(0,8))
        ttk.Button(toolbar,text='Correct / void receipt',command=self.correct_delivery).pack(side='left')
        ttk.Label(frame,text='History covers changes from v0.7 onward, across all periods. Select a row to inspect before and after.\nLocking protects period records; reopening requires a reason. Repayments are protected by payment date.\nYour computer username identifies changes. This local history is not tamper-proof security.',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=14)
        self.history_table=self.register_table(frame,['Time UTC','User','Record','Action','Reason'])
        self.history_table.bind('<<TreeviewSelect>>',self.history_detail)
        self.history_text=tk.Text(frame,height=7,wrap='word',font=('Consolas',10),bg='white',fg='#244047',relief='flat',padx=12,pady=12)
        self.history_text.pack(fill='x',pady=(12,0));self.history_text.configure(state='disabled')

    def refresh_controls(self):
        if not hasattr(self,'history_table'):return
        self.history_table.delete(*self.history_table.get_children())
        try:self.lock_status.configure(text='Selected period: LOCKED' if self.ledger.period_locked(self.pid()) else 'Selected period: OPEN')
        except ValueError:self.lock_status.configure(text='Create a reporting period to begin.')
        for row in self.ledger.db.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 500'):
            self.history_table.insert('','end',iid=str(row['id']),values=[row['at'],row['actor'],f"{row['entity']} #{row['record_id']}",row['action'],row['reason']])

    def history_detail(self,event=None):
        selected=self.history_table.selection()
        if not selected:return
        import json
        row=self.ledger.db.execute('SELECT * FROM audit_log WHERE id=?',(int(selected[0]),)).fetchone()
        text='BEFORE\n'+json.dumps(json.loads(row['before_data']) if row['before_data'] else None,indent=2)+'\n\nAFTER\n'+json.dumps(json.loads(row['after_data']) if row['after_data'] else None,indent=2)+'\n\nStored monetary values are cents.'
        self.history_text.configure(state='normal');self.history_text.delete('1.0','end');self.history_text.insert('end',text);self.history_text.configure(state='disabled')

    def toggle_lock(self):
        try:
            p=self.pid();locked=self.ledger.period_locked(p)
            def save(v):
                from datetime import datetime
                self.ledger.backup(DATA/f"before-period-change-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3")
                self.ledger.set_lock(p,not locked,v['Reason'])
            self.form('Reopen period' if locked else 'Lock completed period',[('Reason','',None)],save)
        except Exception as exc:messagebox.showerror('Period control',str(exc))

    def correct_delivery(self):
        try:
            p=self.pid()
            rows={f"#{r['id']} {r['day']} | {r['name']} | {r['units']} units":dict(r) for r in self.ledger.db.execute('SELECT r.*,p.name FROM receipts r JOIN products p ON p.id=r.product WHERE period=? ORDER BY r.id DESC',(p,))}
            if not rows:raise ValueError('No receipts in this period.')
            def defaults(v):
                row=rows[v['Receipt']]
                return {'Units':row['units'],'Goods cost':f"{row['goods']/100:.2f}",'Delivery cost':f"{row['freight']/100:.2f}"}
            def save(v):self.ledger.correct_receipt(rows[v['Receipt']]['id'],v['Units'],v['Goods cost'],v['Delivery cost'],v['Reason'])
            self.form('Correct receipt (zero units and costs to void)',[('Receipt',next(iter(rows)),list(rows)),('Units','0',None),('Goods cost','0',None),('Delivery cost','0',None),('Reason','',None)],save,loader=defaults)
        except Exception as exc:messagebox.showerror('Receipt correction',str(exc))

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

    def build_cloud(self):
        self.cloud=None
        frame=ttk.Frame(self.tabs,padding=18);self.tabs.add(frame,text='Online backup')
        self.cloud_status=ttk.Label(frame,text='OFFLINE MODE — cloud not connected',style='Section.TLabel');self.cloud_status.pack(anchor='w',pady=(0,16))
        ttk.Label(frame,text='Keep working offline. Connect only when you want to upload a backup or restore it on another PC.\nThis is manual backup and restore, not live multi-user sync. One account holds one shop snapshot.\nUse one active PC at a time. Upload before switching PCs; download before entering records on the next PC.',style='Muted.TLabel',wraplength=790).pack(anchor='w',pady=(0,18))
        for label,command in [('1. Save Supabase setup SQL',self.save_cloud_sql),('2. Configure project and sign in',self.cloud_signin),('Upload this PC to cloud',self.cloud_upload),('Download cloud copy to this PC',self.cloud_restore),('Return to offline mode',self.cloud_disconnect)]:
            ttk.Button(frame,text=label,command=command).pack(anchor='w',pady=6)
        ttk.Label(frame,text='First setup: run the SQL in a dedicated Supabase project, then create/confirm an email/password user in Authentication.\nEnter the project URL and publishable/anon key here. Never enter a service-role/secret key.\nPasswords and session tokens are kept in memory only. Project settings and cloud version markers stay on this PC.\nCloud copies contain your shop records and change history. Only upload to a project/account you control.\nTransfers use HTTPS and owner-based database access rules; backups are not end-to-end encrypted.\nThe latest cloud snapshot is replaced by each successful upload. Keep local backups too.',style='Muted.TLabel',wraplength=790).pack(anchor='w',pady=24)

    def save_cloud_sql(self):
        from ledger import CLOUD_SETUP_SQL
        target=filedialog.asksaveasfilename(defaultextension='.sql',initialfile='family_shop_cloud_setup.sql')
        if target:
            try:Path(target).write_text(CLOUD_SETUP_SQL,encoding='utf-8');messagebox.showinfo('Setup script saved','Run this SQL in your Supabase project SQL editor, then create an email/password user in Authentication.')
            except OSError as exc:messagebox.showerror('Could not save SQL',str(exc))

    def cloud_job(self,title,work,done):
        popup=tk.Toplevel(self);popup.title(title);popup.transient(self);popup.grab_set();popup.resizable(False,False)
        ttk.Label(popup,text=title+'… Please wait.',padding=24).pack()
        popup.protocol('WM_DELETE_WINDOW',lambda:None)
        results=queue.Queue()
        def worker():
            try:results.put((True,work()))
            except Exception as exc:results.put((False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            try:ok,result=results.get_nowait()
            except queue.Empty:self.after(150,poll);return
            popup.destroy()
            if ok:
                try:done(result)
                except Exception as exc:messagebox.showerror(title,str(exc))
            else:messagebox.showerror(title,result)
        self.after(150,poll)

    def cloud_signin(self):
        import json
        try:config=json.loads((DATA/'cloud-settings.json').read_text())
        except (OSError,ValueError):config={}
        def save(v):
            from ledger import Cloud
            client=Cloud(v['Project URL'],v['Publishable / anon key'])
            email,password=v['Email'],v['Password']
            def done(_):
                self.cloud=client
                (DATA/'cloud-settings.json').write_text(json.dumps({'url':client.url,'key':client.key,'email':email}),encoding='utf-8')
                self.cloud_status.configure(text='ONLINE SESSION — signed in (manual transfers)')
                messagebox.showinfo('Connected','Signed in. Upload to create a cloud backup, or download an existing copy. Shop records remain local until you choose Upload.')
            self.after(100,lambda:self.cloud_job('Signing in',lambda:client.login(email,password),done))
        self.form('Connect online backup',[('Project URL',config.get('url',''),None),('Publishable / anon key',config.get('key',''),None),('Email',config.get('email',''),None),('Password','',None)],save)

    def cloud_disconnect(self):
        self.cloud=None;self.cloud_status.configure(text='OFFLINE MODE — cloud not connected')

    def cloud_marker(self,version=None):
        import hashlib,json
        key=hashlib.sha256((self.cloud.url+'|'+self.cloud.owner).encode()).hexdigest()
        path=DATA/('cloud-version-'+key+'.json')
        if version is not None:path.write_text(json.dumps({'version':version}),encoding='utf-8')
        try:return int(json.loads(path.read_text())['version'])
        except (OSError,ValueError,KeyError):return 0

    def cloud_upload(self):
        if not self.cloud:messagebox.showinfo('Online backup','Configure the project and sign in first.');return
        if not messagebox.askyesno('Upload shop records','Upload this PC’s complete shop database to your Supabase account? This replaces the previous cloud snapshot. Continue only if this is the current working copy.'):
            return
        try:
            import tempfile
            fd,name=tempfile.mkstemp(suffix='.sqlite3',dir=DATA);os.close(fd);snapshot=Path(name)
            self.ledger.backup(snapshot);client=self.cloud;expected=self.cloud_marker()
            def work():
                try:return client.upload(snapshot,expected)
                finally:snapshot.unlink(missing_ok=True)
            def done(version):
                self.cloud_marker(version)
                self.cloud_status.configure(text=f'ONLINE SESSION — uploaded cloud version {version}')
                messagebox.showinfo('Cloud backup saved',f'Uploaded version {version}. You can continue offline or download it on another PC.')
            self.cloud_job('Uploading cloud backup',work,done)
        except Exception as exc:messagebox.showerror('Upload failed',str(exc))

    def cloud_restore(self):
        if not self.cloud:messagebox.showinfo('Online backup','Configure the project and sign in first.');return
        if not messagebox.askyesno('Replace local records','Download the cloud snapshot and replace this PC’s shop records? Any unsent local changes will be replaced. A dated local backup will be saved first. Close other Family Shop windows before continuing.'):
            return
        import tempfile
        fd,name=tempfile.mkstemp(suffix='.sqlite3',dir=DATA);os.close(fd);snapshot=Path(name);client=self.cloud
        def work():
            try:return client.download(snapshot)
            except Exception:snapshot.unlink(missing_ok=True);raise
        def done(version):
            from datetime import datetime
            try:
                # Upgrade/validate downloaded data before replacing the working database.
                check=Ledger(snapshot);check.db.close()
                backup=DATA/('before-cloud-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
                self.ledger.backup(backup)
                self.ledger.db.close()
                try:os.replace(snapshot,DATA/'shop.sqlite3')
                finally:self.ledger=Ledger(DATA/'shop.sqlite3')
                self.cloud_marker(version);self.reload_periods()
                self.cloud_status.configure(text=f'ONLINE SESSION — downloaded cloud version {version}')
                messagebox.showinfo('Cloud copy restored',f'Downloaded version {version}. Previous local records were backed up to {backup.name}.')
            finally:snapshot.unlink(missing_ok=True)
        self.cloud_job('Downloading cloud backup',work,done)

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
