# Mutowei Investments v0.16 — three-shop desktop app

**WhatKind?**

Mutowei Investments contains three independent shop sections: **Mutowei Bottle Store**, **Bizzy Tuckshop (grocery & beer)** and **Chikofa Tuckshop (grocery & beer)**. Choose a shop using the three section buttons above the reporting-period controls. Records, products, stock, costs, orders, customer balances, reports and change history belong only to that shop. This is separate local storage, not staff authorization; there are no per-shop passwords or roles.

The app and desktop shortcut use a mint soup bowl with a spoon resting inside it. Earlier release notes below use the former name Family Shop. The repository folder and updater branch retain their original technical names so installed updates keep working.


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

## v0.5 — refreshed desktop layout

Use **Update App** to install. No new dependencies or database changes.

The new layout includes a dark teal navigation sidebar, a light workspace, summary cards for stock-implied sales, provisional profit and unexplained differences, a two-column grid of daily actions, more consistent typography, roomier tables and styled entry forms. Navigate with Overview, Stock & reports, Daily registers and Orders & credit. The minimum window size is 1060 × 720; the default is 1280 × 850. Large Windows display scaling can reduce available space; maximize the window if needed. Figures retain the existing accounting rules and remain provisional. All 13 calculation/report/updater tests pass; the refreshed desktop appearance still needs a Windows screen check.

## v0.6 — record corrections, history and period controls

Install with **Update App**. Existing records are preserved; the database gains history and control tables/triggers. History begins at this upgrade and does not reconstruct earlier edits.

Open **History & controls** in the sidebar:

- **Correct / void receipt:** select a received line in the chosen period. Correct individual units, total goods cost and delivery cost, giving a reason. For a duplicate receipt enter zero units and zero costs. The receipt stays in the register at zero and the previous values remain in history. Linked purchase-order received quantities adjust in the same transaction. Corrections that exceed ordered units or make stock counts impossible are rejected. Dates, products and references cannot be changed here; void the wrong line and record a replacement if needed. Customer debt/repayment correction workflows are not yet included.
- **Lock / reopen period:** lock a completed period with a reason. A backup is created before changing the lock. Locked periods reject new entries, edits and deletions for stock, receipts, daily money and customer credit sales. Repayments are guarded by payment date, so customers can repay an older debt in a later open period. Locking does not certify figures as correct or require a zero reconciliation difference; check the report and warnings first. Purchase orders and product creation remain available.
- **History:** shows the newest 500 changes across all periods. Click a row to see before/after values. Money in these technical details is stored as cents; timestamps are UTC. Reasons are recorded for receipt corrections and period lock/reopen actions. Ordinary saved entries use `Record saved`. The full history remains in SQLite beyond the 500 displayed rows.

This is a local operational history using the computer username, not authenticated user roles, accounting sign-off or tamper-proof security. Reopening an earlier period does not automatically revise opening balances already copied to later periods; review those separately. All 17 tests pass, including blocked locked-period edits, reopening/history snapshots, receipt/order synchronization, impossible-count rejection and later repayments of locked-period debts. New desktop controls still need a Windows interaction check.

## v0.7 — optional online backup and restore

Install through **Update App**. Online features use Supabase; normal accounting stays local and works without internet. No new Python packages are required.

### One-time cloud setup

1. Use a dedicated Supabase project for the shop. In the app select **Online backup → Save Supabase setup SQL**. Run that file in your project's SQL editor. It is also available as `offline_shop/cloud_setup.sql` on GitHub. The app embeds the script, so existing updaters do not need to download extra files.
2. In Supabase Authentication create and confirm an email/password user for your shop. Account creation, password resets and verification are managed in Supabase for this version.
3. In the app choose **Configure project and sign in**. Enter the HTTPS project URL, public publishable or legacy anon key, and that user's email/password. Never use a secret or service-role key. Only `https://<project>.supabase.co` project URLs are supported.
4. Choose **Upload this PC to cloud** to transfer your current database. This sends all shop records and history to the configured project/account; nothing uploads merely by signing in.
5. On another PC, install/update Family Shop, sign in to the same shop account, and choose **Download cloud copy to this PC**. This replaces its local records after saving a dated local backup. Close other Family Shop windows first.

### Transfer rules and limits

This is **manual snapshot backup/restore, not live synchronization or record merging**. One authenticated account owns one complete shop snapshot. Separate accounts have separate snapshots; staff membership and cross-account collaboration are not implemented. Use one active PC at a time: upload before switching, then download on the next PC before entering new data.

The backend uses owner-based row-level access rules and an atomic expected-version upload function. A PC with an older cloud version cannot silently overwrite a newer copy. An existing cloud backup also blocks a first-time PC from uploading until it downloads the current copy. Back up any unsent local changes separately before downloading; they are not merged. Only the latest snapshot is stored in the cloud. Keep separate local backups for historical recovery.

Passwords and session tokens are held in memory only. Project URL, public key, email and per-account version markers are saved locally outside the database. Signing out clears the local session. Sessions can expire; sign in again if a request reports an authentication failure. Requests use HTTPS; copies are **not end-to-end encrypted** and project administrators can access records. The shop database remains unencrypted on your PC as before.

Cloud snapshots are limited to 10 MiB in this initial version. Downloads are checked for format, SHA-256 integrity, SQLite integrity, required shop tables and foreign-key validity before replacing local records. A dated local backup is made before restore. Downloads and uploads run in the background while a modal window prevents editing. Online access requires network access to your Supabase project. Pricing, quotas and service availability depend on your Supabase account; no plan or unlimited free storage is assumed.

Validation: **21 tests pass**, including snapshot round-trip, version payload, conflict handling, error redaction, hostile URL/privileged key rejection and tampered/invalid database checks. HTTP responses are mocked for cloud tests. SQL deployment, cross-account RLS and real sign-in/upload/restore still require integration testing against your configured Supabase project. No project credentials were supplied and no live backend was provisioned.

References: [Supabase password authentication](https://supabase.com/docs/guides/auth/passwords), [row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security), [database functions](https://supabase.com/docs/guides/database/functions).

## v0.8 — image scanning and reviewed record import

Update in the app, then open **Scan records**. This initial OCR integration uses Windows 10/11's local OCR engine and Windows PowerShell; no paid API key, Python OCR package or cloud upload is required. Images are read locally and never sent for recognition to Supabase or another service. Windows must have an OCR-capable language such as English installed. Printed, straight, sharp text works best; handwriting is not reliably recognized and must be checked manually. PDF/HEIC, direct camera capture, multiple-image batches and cloud AI handwriting recognition are not included.

1. Select the reporting period first. Choose **Choose image & scan** for a PNG/JPG/BMP photo (under 30 MiB), or paste transcribed text into the editable source box. Oversized pixel dimensions are rejected with instructions to resize.
2. Choose Stock counts, Goods received or Daily money, then **Arrange draft**. Correct the source and CSV draft against the photo. Stock-sheet rows in `Product Opening Receivings Total Closing Sold Price Amount` order can be arranged if their printed arithmetic agrees. Drawings, breakages and opening cost remain blank because the scanner cannot infer them. The unit defaults to `each` and must be checked. Receipts must be entered before dependent stock counts. Other layouts may need manual comma-separated transcription.
3. For daily money/receivings use the exact CSV headings shown by the app. Commas or vertical bars or tab-separated source lines can be arranged when the column counts match. Lines that cannot be arranged are counted in the notice and remain in the source text; add their rows yourself if relevant. Dates must be YYYY-MM-DD. Monetary amounts must omit currency symbols/commas and use decimal points. Quote text containing commas using ordinary CSV quoting.
4. Fill unknown numbers explicitly after checking the record; blanks do not become zero. Select **Save reviewed rows** and confirm you checked the draft. A local backup is made first. All rows are validated on a temporary in-memory database, and the resulting state is copied back only when the whole batch succeeds. Nothing saves automatically after OCR.

New product names are created with the reviewed units. Existing product units must match. Existing stock counts and daily-money dates cannot be overwritten by import; edit them through their normal forms. Exact repeated batches are blocked; altered/retyped batches may still duplicate receipts, so check before importing. Period locks and normal stock validations still apply. Accepted record changes appear in history with the source filename. Raw image files and extracted text are not saved in the shop database; keep your originals separately. Scans are drafts and contain no confidence scores or accounting certification. Cloud upload remains a separate action.

If PowerShell is disabled by your Windows policy, the app reports the error and you can paste text manually; the app does not change execution policy. If no OCR language is available, install the relevant Windows language/OCR component. Scanning is performed in the background. The scanner does not automatically rotate, deskew or enhance images; prepare a clear upright photo first.

Validation: all 25 tests pass, covering conservative row arrangement, rejecting missing values, all-or-nothing batch failure, receipt/stock costing, existing-record protection, import history and locked periods. Windows OCR execution and the scan screen still require verification on a Windows PC. Microsoft reference: [Windows OCR engine](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine).

## v0.9 — Family Shop branding, taskbar icon and dashboard graphics

Install with **Update App** and let the app restart. Family Shop now has its own storefront mark: mint awning, amber stock bars and a navy tile. The same mark appears in the sidebar, dashboard, window/title bar and Windows desktop shortcut.

On Windows the process sets its own AppUserModelID before creating the Tk window and loads a multi-resolution ICO (16–256 pixels). Existing Family Shop desktop shortcuts are refreshed automatically when the app starts. The shortcut launches the current Python installation's `pythonw.exe` where available, so normal launch does not leave a command window open. Its icon is materialized in `%LOCALAPPDATA%\FamilyShop\assets`; the updater carries the icon embedded in `app.py`, so existing installations do not need another download or additional packages. A non-Windows Tk environment uses the PNG window icon instead.

If you need to create or refresh the shortcut manually, use **History & controls → Refresh desktop icon**. Close Family Shop and reopen from that shortcut. An old pinned Python icon can remain cached by Windows: unpin that old item and pin the refreshed Family Shop shortcut/running window. Windows taskbar grouping, pinning and desktop icon refresh still need checking on your PC. Python remains the runtime; this is not an EXE installer.

The dashboard adds an illustrated brand banner, pastel action symbols, accented summary cards, navigation hover states and a scrollable overview for smaller windows. It uses the same real period figures; the decorative illustration introduces no fictional business data. The accounting rules, local database, cloud setup and scan workflow are unchanged. No graphics package is required on users' computers.

Brand assets are included as `family-shop.svg`, `family-shop.png` and `family-shop.ico`. They are native geometric artwork, not photos. Validation: all 26 tests pass, including embedded asset decoding, multi-resolution icon structure, persistent icon materialization and the existing accounting/report/updater checks. Windows shell integration and visual layout have not been tested in this environment.

References: [Microsoft AppUserModelID](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid), [Tk window icons](https://www.tcl-lang.org/man/tcl8.7/TkCmd/wm.html).

## v0.10 — mouse wheel, trackpad and drag scrolling

Install with **Update App**. The old overview-only global wheel callback has been replaced with a routing tag that runs before Tk's normal widget/class bindings. Wheel events over labels and cards now reach the enclosing page; tables and text areas scroll first, then pass movement to the page when at their edge. Fractional wheel deltas accumulate for high-resolution trackpads. Shift + wheel scrolls horizontally where the target has horizontal content. Entries, dropdowns and scrollbars keep their native behaviour. Linux wheel button events and macOS wheel deltas are also handled, but have not been verified on those systems.

Every section now has a scrollable page, so smaller windows can reach content without relying solely on an inner table's scrollbar. The overview uses pixel-based movement. Vertical click/touch dragging starts after an 8-pixel threshold on page backgrounds, cards, labels, tables and disabled/read-only text areas. Buttons and editable fields keep normal click/edit/select behaviour. This supports touchscreen gestures delivered by Windows as pointer drag events; it is not a native multi-touch or momentum/inertia implementation. Mouse-wheel, trackpad and touchscreen hardware behaviour must still be checked on Windows.

All 30 tests pass, including wheel routing over child cards, nested table edge fallback, small trackpad delta accumulation, horizontal scrolling, drag thresholds and preserving button/entry interactions. No accounting data or calculation rules change.

## v0.11 — bulk packages and individual units

Use **Update App**. When adding a product, specify its **individual unit**, **package type** and **units per package**. Supported package types: Individual, Box, Case, Crate, Pack, Carton, Sack, Bag, Bundle, Tray, Pallet, Bale, Drum, Tub, Roll and Other. Counts must be positive whole numbers. An Individual package contains exactly one unit. Package sizes are entered by you, not guessed from the brand.

Examples:

- Castle Quart: individual unit `bottle`, package type `Crate`, units per package `12`.
- Sugar: individual unit `packet`, package type `Case`, units per package `10`.

In **Record delivery**, choose the product, enter full packages and any loose individual units. A live preview shows the conversion before saving: `2 crates × 12 + 3 loose = 27 bottles`. Enter the total goods purchase cost for the whole delivery and total delivery cost, not cost per package or bottle. Stock balances, cost calculations and selling prices continue to use individual units, preventing a crate from being counted as one bottle.

Use **Overview → Products → Edit packaging** to set a package size for existing products or change it for future deliveries. Products created before this update default to Individual/1 until you configure them; their saved stock and receipts are not converted retroactively. The Daily registers page includes a product packaging catalogue and package breakdowns for new deliveries. Each bulk receipt saves the package type and size used when received, so later edits do not rewrite history. Correcting a receipt in individual units clears its old package breakdown to avoid displaying a stale conversion; its prior details remain in the change history.

Stock-count entry, scanned/imported rows, purchase orders and order-delivery entry still accept **individual units**. Package conversion is currently provided in the main Record delivery form. For example, order 24 individual bottles for two crates of 12. Scanned product creation defaults to Individual/1; configure package sizes after import if needed. This version supports one configured package size per product, not nested cases of packs or fractional kg/litre quantities.

The update adds package metadata without changing existing stock amounts. All 35 tests pass, including crates plus loose bottles, sugar cases, per-unit costing, historical size retention, invalid sizes, locked periods and correcting package receipts. The new Windows forms still need an interaction check on your PC.

## v0.12 — visible automatic unit costs and sales amounts

Install with **Update App**. Purchase costs were already included in periodic weighted-average costing; this update also shows the calculations during entry.

- Main goods-received form: package quantities convert to individual units. **Purchase cost/unit = total goods cost ÷ individual units received**. **Including delivery/unit = (goods cost + delivery cost) ÷ individual units received**. Both are shown to four decimal places; enter costs for the entire delivery.
- Receive-order form: the same per-unit cost preview is shown for its individual-unit quantity.
- Daily registers: received goods have purchase cost/unit and cost including delivery/unit columns. Use horizontal scrolling for wide tables. Voided zero-unit receipts show zero cost/unit rather than dividing by zero.
- Stock entry: the preview shows units sold, weighted-average unit cost, selling price per unit and total sales. Units sold = opening + received − closing − drawings − broken units. Opening stock still needs its opening unit cost (or the carried-forward cost); newly received stock costs come from its receipts automatically.
- Choose **Selling price per unit** to calculate total sales as units sold × unit price. Or choose **Total sales amount** to derive average selling price = entered total ÷ units sold. Only the selected input method is used; the other amount field is ignored. All monetary inputs are dollar amounts, not cents.
- When using a total sales amount, the exact total is retained separately in cents. For example, three units sold for $10 show an average price of $3.3333 and retain $10.00 revenue, not $9.99. This is an average, not proof that every item had that price. Switching back to price-per-unit removes that total override. A nonzero sales total is rejected if units sold are zero. Updating stock/receipts later can change the derived average; the entered total remains until edited. Recheck it if you correct earlier data.

Entered total sales amounts belong to the selected product/period, not the day's overall cash collection. Do not enter all shop sales against each product. Manual daily-money reconciliation remains separate. Profit uses cost of goods sold, not all purchases as an immediate expense. Report sales totals include any entered product sales amounts; reports identify derived average selling prices in the explanatory note. Carry-forward uses the stored selling price rounded to cents for the next period; review your next-period price.

All 39 tests pass, including individual-unit conversion, delivery-inclusive cost, preview/report agreement, exact sales totals with repeating average prices, mode switching and rejection of sales with zero units sold. New Windows form previews still need an interaction check.

## v0.13 — FIFO and periodic weighted-average inventory costing

Install with **Update App**. Choose the default method when adding a product or through **Products → Packaging & costing**. Existing records retain weighted average unless you explicitly edit an open stock count and choose FIFO. The stock form now has a **Costing method** selector for that product/period. Changing only the default does not revalue an already saved period. Use a consistent cost formula for similar inventories; changing the selection is an explicit revaluation, not just a display filter. Locked periods still cannot be edited.

- **FIFO:** uses opening cost layers first, then purchases ordered by receipt date and receipt ID for same-day ties. Each receipt's per-unit cost includes its allocated delivery cost. Older and newer prices remain distinct. Inventory left at period end retains its unused cost layers.
- **Weighted average:** pools the opening inventory value and all purchases/delivery costs for the period, then divides by available units. The same average values sales, drawings, breakages and closing stock. This is periodic weighted average, not a moving average after each individual sale.
- **Carry-forward:** now preserves the actual remaining FIFO layers or the precise weighted-average value, including fractional cents per unit, instead of relying only on the rounded opening-cost display. Do not edit the carried opening quantity or unit cost unless it needs correcting; a change discards the inherited layers and uses your entered opening balance as one layer. Previously entered opening stock without a layer history is treated as one opening layer. Carry-forward remains a one-time copy: later edits to an earlier period do not automatically refresh later periods.
- **Cost layers:** on Stock & reports, shows each incoming layer, cost of goods sold, drawings, breakages, closing value and remaining layers. Printed reports include a per-product method and valuation summary. Sales amounts are unchanged by the cost method; cost of sales, inventory value and profit change.

Example: receive 10 units at $1, then 10 at $2, and sell 12. FIFO costs sales at $14 and values the remaining 8 at $16. Periodic weighted average costs sales at $18 and values closing stock at $12.

**Period-total limitation:** stock-implied sales, drawings and breakages are currently aggregate counts without individual movement dates. FIFO allocates the oldest costs to sales first, then drawings, then breakages. With drawings or breakages, this category allocation may differ from the actual dated sequence and is flagged as provisional in report checks. Closing FIFO layers account for all recorded outflows, but exact dated movement costing needs a future transaction-level stock register. This version does not implement LIFO, specific identification, moving-average/perpetual sales timing or lower-of-cost-and-net-realisable-value adjustments.

Stock drawings at cost are displayed separately and are not deducted as operating expenses. The cost method and opening layers appear in the local change history. Package conversion, exact sales totals, cash reconciliation and cloud snapshots continue to use the same recorded quantities.

All 45 tests pass, including rising/falling prices, receipt-date ordering, FIFO vs weighted-average values, cost-layer carry-forward, fractional-cost preservation, method-default stability and transparent non-sale allocation. The new Windows method controls and layer viewer still need an interaction check. Reference: [IFRS IAS 2 Inventories](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/) describes FIFO and weighted average for ordinarily interchangeable inventories. This app's costing features do not by themselves establish full financial-reporting compliance.

## v0.14 — lightweight interface animations

Install through **Update App**. Adds a short welcome heading reveal and storefront lift/pulse, an animated accent line and title colour transition when changing pages, smooth sidebar hover colours, highlighted action-card borders with small icon lifts, a pressed-button visual state and indeterminate loading bars during OCR/cloud operations. Financial values are not animated or replaced with demonstration numbers.

Animations use Tk's event loop, not blocking sleeps or extra UI threads. Short effects finish within 150–650 ms, and repeated hover/navigation cancels earlier callbacks instead of stacking them. No decorative animation loop runs continuously while idle; loading indicators run only while their operation is pending. This is page-header motion, not a cross-fade of the entire accounting workspace. Background data tasks keep their existing worker threads.

**History & controls → Reduce motion** applies effects instantly without movement and disables animated loading bars. The preference is stored locally in `motion-settings.json` outside the shop database. Enabling it also completes and cancels pending decorative animations. Disabling it restores effects on subsequent interactions. It is an app preference, not automatic detection of Windows accessibility settings.

All 49 tests pass, including cancellation of stale callbacks during rapid transitions, clean completion, reduced-motion behaviour and saved preference. The effects' appearance and responsiveness still need checking on Windows hardware. No database schema, accounting figures, cloud setup or updater settings change.


## v0.15 — Mutowei Investments, WhatKind? and three shop sections

Install with **Update App**. The window, sidebar, banner, reports, updater dialogs and desktop shortcut use **Mutowei Investments** and the motto **WhatKind?**. The bowl-and-spoon logo is embedded in the updater-compatible app and supplied as `mutowei.svg`, `mutowei.png` and `mutowei.ico`. Existing Family Shop desktop shortcuts are replaced with Mutowei Investments shortcuts after launch; Windows may require repinning the new shortcut if an older Python/Family Shop item was pinned.

### Shop separation

The three section buttons switch between:

1. **Mutowei Bottle Store** — bottle store.
2. **Bizzy Tuckshop** — grocery and beer.
3. **Chikofa Tuckshop** — grocery and beer.

Each has its own database under the existing application data root's `shops/<shop-id>/shop.sqlite3`. The data root retains its former `FamilyShop` name to preserve compatibility. Selected shop, report title and window title identify the active shop. The last selected shop is remembered. Periods are independent, so the same date range can exist in all three shops. Switching clears unsaved scan text/drafts (asking before discarding a nonempty CSV draft), closes nonmodal record viewers and refreshes products, periods, reports and customer history. These sections are not a consolidated group income statement and do not add inter-shop transfers.

### Records from before this update

If the former single-shop database has records, the app asks which shop they belong to. Choose the correct destination explicitly or close the dialog and decide later through **History & controls → Assign records from before the three-shop update**. Assignment copies the records to one shop only; it never duplicates them into all three. The original database and a dated backup are preserved. It refuses to overwrite a shop that already has records or repeat a completed assignment. Review the destination before saving. If your former database already mixes several shops, do not assign the mixed data to one shop as though it were correct; sorting those records requires a separate migration.

### Shop backups and online setup

Manual backup, scan-import backup, reports and restore now operate on the selected shop. Future app updates back up every shop before replacing shared program files. The first update to this version uses the prior updater to back up the original single-shop database, before the new sections are created.

**Cloud users must run the refreshed setup SQL once in the same Supabase project:** Online backup → Save Supabase setup SQL, then execute it in SQL Editor. The script keeps the old single-shop backup table and adds a shop-scoped backup table/RPC. No project or auth account change is required. Each account now has one separate latest snapshot per shop, with independent version checks. Shop identity is checked before upload and after download, preventing a Bizzy backup from being restored in Chikofa's section. A signed-in session can be reused when switching, but the shop namespace changes. The previous unassigned cloud snapshot remains preserved and is not automatically copied to any shop. Assign local records first, then upload the selected shop. New SQL/RLS live deployment remains unverified here.

All **53 tests pass**, including isolated reports/data for all three shops, explicit legacy assignment with source preservation/no overwrite, cloud namespace and wrong-shop rejection, and updater backups for every shop. The new shop-switching controls and renamed Windows shortcut still require a Windows interaction check. All costing, package, sales, scanning and period-control features remain available within each shop.

## v0.16 — native precision-touchpad event support

Install through **Update App**. Adds explicit `TouchpadScroll` and `Shift-TouchpadScroll` bindings for newer Tk runtimes. These use a different event from `MouseWheel`, so the former mouse-wheel-only route could leave page canvases unresponsive to two-finger touchpad gestures. Older runtimes that do not recognize the new event keep using the existing MouseWheel path.

The touchpad binding receives raw Tcl event substitutions, decodes the signed horizontal/vertical delta components, routes both axes to the correct viewport and accumulates small movements for line-based tables/text. Page canvases move at pixel resolution. Shift swaps touchpad axes for horizontal scrolling. Wheel events now use the live pointer position, rather than relying on wheel-event root coordinates or the focused widget. App-wide MouseWheel fallback bindings cover newly mapped widgets, while handled events stop before native handlers to avoid duplicate movement. Touchscreen drag handlers and manual scrollbar controls are unchanged.

All 57 tests pass, including signed packed-delta decoding, precision gestures independent of MouseWheel events, pointer-over-table while an entry has focus, small delta accumulation and Shift-horizontal routing. This is a compatibility fix; actual Windows touchpad-driver behaviour still needs testing on the user's hardware. Reference: [Tk TIP 684, Touchpad Scrolling](https://core.tcl-lang.org/tips/doc/main/tip/684.md).
