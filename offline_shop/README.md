# Family Shop v0.4 — offline desktop edition

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

This is a stock-count and period reconciliation tool, not yet a full double-entry accounting package. Profit is provisional and assumes complete counts, accurate costs and one selling price per product per period. Missing costs entered as zero overstate profit. Use shorter periods when selling prices change. Count all products, including those with no receipts; the app can only flag missing counts for products with recorded receipts. Opening stock can be brought forward from the latest earlier period, then actual closing counts must be updated.

Received orders are recorded; supplier balances, transaction-level sales, returns, taxes, multiple currencies, passwords/roles, encryption, an EXE installer are future work. Records are local to one computer and are not synced across devices. The computer's account/file permissions protect the unencrypted database. The entry register shows product names and monetary amounts in dollars.

## Backups and recovery

On Windows the database is `%LOCALAPPDATA%\FamilyShop\shop.sqlite3`. The precise path is shown in the app. Use **Backup database** regularly. To restore, close the app, keep a copy of the current database, then copy a known good backup to that path and name it `shop.sqlite3`. Never commit real databases to GitHub.

## Verification

Run `python -m unittest -v` from this folder. Tests cover weighted costs, delivery, drawings, breakages, operating expenses, the $167.25 difference, repeated daily updates, dates, overlapping periods, impossible counts, invalid money and receipts missing stock counts. Desktop window verification on Windows is still required.


## v0.2 upgrade and new workflows

**Before updating:** use Backup database in the old app and close it. Extract the new ZIP into a fresh folder and run `offline_shop/start_shop.bat`. It uses the same data path as v0.1 and adds tables automatically, preserving your saved records. Keep your backup in case you need to return to v0.1.

- **Purchase orders:** select a reporting period, then open Orders & customer credit. Create a purchase order with supplier, reference, product, units and estimated total cost. An order has no effect on stock or profit until received. Receive order records each partial delivery in the selected period with its actual goods cost and allocated delivery charge. Outstanding units reduce automatically; excessive deliveries are rejected. Do not also enter that delivery through Goods received, or you will duplicate it. Estimates are informational, not supplier balances or actual purchase costs.
- **Customer credit:** record individual customer credit sales and repayments. Each repayment is allocated to one debt and cannot exceed its remaining balance. The screen shows original amount, paid amount and balance. This is a supporting register: daily-money credit totals still need manual entry/reconciliation. Do not count a debt-register entry twice as a daily sale, and exclude collections of old debts from sales receipts. This version does not automatically reconcile the credit register to daily money. Multiple debts for one customer are displayed separately.
- **Carry-forward:** select a new period with no stock-count rows and choose Bring forward previous closing stock. It copies the latest earlier period's closing units, weighted-average cost (rounded to cents per unit) and selling price. A safety backup is saved first. Closing units initially equal opening units, meaning zero implied sales until you enter actual closing counts. This is a one-time copy, not a live link: later edits to the previous period do not change it. Confirm the previous period is complete first. Rounding cost per unit can create small inventory valuation differences.
- **Editing:** stock forms preload the selected product's saved count. Daily-money forms preload when you enter the date. Check all fields before saving. Receipts, purchase orders, deliveries and debt entries are append-only in this version; corrections/reversals and audit history are planned.

Validation now includes nine tests: partial deliveries and overdelivery rejection, debt overpayment prevention and separation from sales, carry-forward/no overwrite, and upgrading an existing database with backup, in addition to the original reconciliation and costing checks. Desktop interaction for v0.2 still needs a check on Windows.

## v0.3 — desktop shortcut and in-app updates

One final manual installation is needed because older versions have no updater:

1. Back up your database and close Family Shop.
2. Download the `family-shop-offline` branch once and extract it into a permanent folder, for example `Documents\FamilyShopApp`. Keep that folder in place.
3. Open `offline_shop` and double-click `setup_shortcut.vbs`. This creates a **Family Shop** desktop shortcut pointing to this folder. If Windows blocks scripts, manually create a desktop shortcut to `start_shop.bat` instead.
4. Launch Family Shop from that shortcut. Your existing database is reused.
5. For future versions, connect to the internet and click **Update App**. The app checks GitHub in the background. Confirm the update, then let it finish and reopen. Close other copies of the app first. Downloading ZIPs is no longer needed for normal updates.

The updater follows this repository's `family-shop-offline` branch. Only run updates from the trusted project. Each update pins a commit, verifies Git blob hashes and Python syntax, downloads the complete allowlisted program files, creates a timestamped SQLite backup in the data folder and replaces program files. If file replacement raises an error, old program files are restored. Copies of previous program files are kept in `offline_shop/update-recovery`; record backups are in the data folder. A failure after an interrupted process or power outage may require manually restoring these copies. Updates require a writable app folder and internet access to api.github.com and raw.githubusercontent.com. Normal shop work remains offline.

The app closes during installation and reopens afterward. Your database is stored separately and is never overwritten by the downloaded code files. The first update check after the manual setup may reinstall the current version once to establish the installed commit marker. Later checks identify an already installed version. The updater does not install Python or new third-party dependencies. Future versions requiring such changes will need separate instructions.

Verification: all 11 tests pass, including download pinning/hash validation, update rollback and preserving database bytes. Windows shortcut creation and the live download/restart flow require validation on your PC.


## v0.4 — readable registers and printable reports

Click **Update App** in your installed app; no ZIP download is needed. This update stays compatible with the v0.3 updater and adds no dependencies.

- Goods received and daily money now use scrollable tables with product names and dollar amounts instead of raw database rows.
- Orders & customer credit shows a customer summary of total credit sales, repayments and outstanding balances, across all recorded dates.
- **Print / Save PDF** on the stock/income tab opens an offline HTML report in your default browser. Click its Print / Save as PDF button, then choose your printer or Save as PDF. The report contains the selected period's stock sheet, reconciliation and income statement, all-time customer balances, explanatory notes and signature spaces. Suggested paper layout is A4 landscape. Printing uses your browser; the app does not create a PDF directly.
- Report checks flag opening stock with zero cost, receipts with zero goods cost, no stock counts, and differences between customer credit sales and daily-money credit. Credit differences are informational: repayments within a period can explain them, and nothing is adjusted automatically.
- Generated reports remain in the data folder's `reports` subfolder. They contain business information; remove old reports manually when no longer needed.

Validation: 13 tests pass. The Windows tables and browser print layout still require checking on your PC.
