# Family Shop — offline desktop edition

A first working desktop version for a family tuckshop. No subscriptions, server, browser, API keys or pip packages. Requires Python 3 with Tkinter (included in the standard Windows installer). This folder runs independently of the existing Streamlit app.

## Windows: start the app

1. Download this branch as ZIP and extract it.
2. Open `offline_shop` and double-click `start_shop.bat`.
3. If Python is missing, install Python 3 with the Python launcher and Tcl/Tk options enabled. Then run the launcher again.

From a terminal: `python app.py` in this folder.

## First shop period

1. Create a non-overlapping reporting period using YYYY-MM-DD dates. Use one day for daily balancing, or a week for weekly balancing.
2. Add products with clear individual units (bottle, packet, loaf). Convert cases to individual units before entry.
3. Record each received order line: date, supplier, invoice reference, units, total goods cost and delivery allocated to that line. Never enter the whole order's delivery cost on every line.
4. Save each product's complete opening/closing count, drawings, breakages, opening unit cost and selling price. Saving again replaces the entire stock count; re-enter all its values.
5. Enter daily money. Saving the same date replaces that date's entire entry; re-enter all its values.
6. Refresh reports, investigate differences, export CSV and back up the database to another drive.

Reports follow the earlier stock sheet: Details, Unit, Opening, Receivings, Total stock, Closing, Drawings, Broken, Sold, Unit price, Total amount. The statement includes signature spaces when exported as text from the on-screen statement (CSV contains financial rows).

## Calculation rules

- Available units = opening + receipts.
- Stock-implied sold = available − closing − drawings − broken units.
- Stock-implied sales = sold × selling price.
- Accounted for = cash handed over + EcoCash sales receipts + unpaid credit sales + cash paid out from sales.
- Unreconciled difference = stock-implied sales − accounted for. Positive means a shortfall; negative means excess.
- Periodic weighted-average unit cost = (opening units × opening unit cost + goods purchases + delivery) ÷ available units.
- Cost of goods sold = sold units × average unit cost.
- Gross profit = stock-implied sales − cost of goods sold.
- Net profit before tax = gross profit − breakages at cost − operating expenses.
- Drawings reduce inventory and owner equity; they are not sales or operating expenses.

Cash paid out is a reconciliation category, not automatically an expense. For example, rent paid from sales cash goes in cash paid out AND operating expenses; a stock purchase paid from sales cash goes in cash paid out AND goods received, not operating expenses. Do not enter opening float, owner capital, transfers or debt repayments as sales. Credit means unpaid sales of this period, not old debts collected. EcoCash means sales receipts, not customer cash-out service transactions.

The historical check is $774.65 stock-implied sales less $531 cash, $49.15 EcoCash, $17.25 credit and $10 cash paid out = **$167.25 unexplained**. Tests use synthetic quantities to reproduce that arithmetic; no historic shop records or customer data are included in the repository.

## Scope of this first version

This is a stock-count and period reconciliation tool, not yet a full double-entry accounting package. Profit is provisional and assumes complete counts, accurate costs and one selling price per product per period. Missing costs entered as zero overstate profit. Use shorter periods when selling prices change. Count all products, including those with no receipts; the app can only flag missing counts for products with recorded receipts. Opening stock must be entered manually for each period, using the previous closing stock and its cost.

Received orders are recorded; pending orders, partial-delivery tracking, supplier balances, debtors ledgers, transaction-level sales, returns, taxes, multiple currencies, passwords/roles, encryption, automatic stock carry-forward and an EXE installer are future work. Records are local to one computer and are not synced across devices. The computer's account/file permissions protect the unencrypted database. The entry register currently shows product IDs and monetary cents; exported financial reports show currency amounts.

## Backups and recovery

On Windows the database is `%LOCALAPPDATA%\FamilyShop\shop.sqlite3`. The precise path is shown in the app. Use **Backup database** regularly. To restore, close the app, keep a copy of the current database, then copy a known good backup to that path and name it `shop.sqlite3`. Never commit real databases to GitHub.

## Verification

Run `python -m unittest -v` from this folder. Tests cover weighted costs, delivery, drawings, breakages, operating expenses, the $167.25 difference, repeated daily updates, dates, overlapping periods, impossible counts, invalid money and receipts missing stock counts. Desktop window verification on Windows is still required.
