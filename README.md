# PES Command Center - Sit Rate Control

Internal local app for Power Energy Solutions LLC to improve appointment sit rate, reduce wasted rep dispatch, and produce a daily appointment action report from a Zoho CSV/XLSX export.

This V1 is local-first and does not connect to Zoho login or APIs.

## Features

- Upload CSV, XLSX, or XLS appointment exports. The app starts blank and waits for an upload.
- Normalize common Zoho/export column names into appointment fields.
- Detect appointment date, time, customer name, phone, address, city, state, status, lead source, rep/OSR, confirmer, and notes when available.
- Group appointments into Today, Tomorrow, Future, and Past / needs cleanup.
- Assign risk levels: Green, Yellow, Red, Gray.
- Recommend daily actions for confirmation, dispatch readiness, final save, do-not-dispatch review, and CRM cleanup.
- Generate copy/paste customer text messages.
- Filter the appointment table and export a filtered CSV action report.
- Compact table view for laptop screens, with the most important action columns first.
- Risk, action, and confirmation cells are color coded in the appointment table.
- V1.1 Column Mapping Debug Mode shows raw upload columns, the first five raw rows, detected header row, and the field mapping used by the normalizer.

## Business Rules

- Confirmed appointments are Green only when status, notes, or `A1 Confirm Status` contain clear confirmed language such as confirmed, appointment confirmed, confirmed by phone/text, replied yes, or show confirmed.
- Status New never becomes Green by default. Tomorrow and future New appointments are Yellow with Send confirmation text; today New appointments are Red with Final save text unless another field contains clear confirmed language.
- The 24-hour reminder action only applies to confirmed appointments scheduled for tomorrow. Route-ready only applies to confirmed appointments scheduled for future dates.
- Unconfirmed appointments are Yellow unless status or notes suggest no answer, previous no-show, cancellation, or failed confirmation. Today appointments with failed-contact risk receive Final save text; cancellation/no-show statuses require do-not-dispatch review or cleanup.
- Canceled, no-show, cancel at door, and pre-appointment cancel statuses are Red or cleanup depending on date.
- Missing or invalid phone, address, city, appointment date, or customer name is Gray and marked Needs CRM cleanup. For the Zoho A1 report, a missing separate appointment time is allowed when `A1 Date` contains only a date. Blank values plus string placeholders such as nan, None, N/A, NA, null, and whitespace are treated as missing.
- Anything other than Website or Employee Self Gen is treated as a call center appointment.
- Payable sit outcomes include Sale, No Sale, and DQ In Home.
- Customer No Show, Pre-App Cancel, and Cancel at Door are not payable sits.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal, usually http://localhost:8501.

## Password Protection

The app requires `APP_PASSWORD` from Streamlit secrets before it shows upload controls, dashboards, debug data, or customer information. The password is not hardcoded in `app.py`.

For local development:

```powershell
mkdir .streamlit
copy .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Then edit `.streamlit\secrets.toml`:

```toml
APP_PASSWORD = "your-local-password"
```

`.streamlit/secrets.toml` is listed in `.gitignore` and should not be committed.

For deployment, add this secret in the hosting provider's Streamlit secrets settings:

```toml
APP_PASSWORD = "your-deployment-password"
```

If `APP_PASSWORD` is missing, the app shows a safe warning that deployment secrets are not configured.

## Expected Export Columns

The app tries to normalize likely variants of these fields:

- appointment date
- appointment time
- customer name
- phone
- address
- city
- state
- status
- lead source
- rep / OSR / consultant
- confirmer
- notes

If a field is missing from the uploaded report, the app adds it as blank and flags missing key dispatch fields as CRM cleanup.

## Zoho Appointment Report Mapping

The current Zoho appointment export maps fields this way:

- `customer_name` = `Full Name`
- `phone` = `Phone`
- `address` = `Mailing Street`
- `city` = `Mailing City`
- `zip` = `Mailing Zip`
- `appointment_date` = `A1 Date`
- `appointment_datetime` = `A1 Date`
- `appointment_date` = date portion of `A1 Date`
- `appointment_time` = time portion of `A1 Date`, only when `A1 Date` includes a time
- `status` / `current_contact_status` = `Current Contact Status`
- `confirmation_status` = `A1 Confirm Status`
- `confirmer` = `A1 Confirmer`
- `lead_source` = `Lead Source`
- `rep` = `A1 OSR`, falling back to a cleaner duplicate `A1 OSR.1` when needed. Grouped count values like `Name ( 2 )` are skipped when a cleaner rep name exists.
- `inside_sales_rep` = `A1 Inside Sales Rep`
- `qualification_status` = `Qualifications Status`
- `vetter_grade` = `Vetter Grade`
- `a1_status` = `A1 Status`

For this Zoho format, `A1 Date` may contain only a date. A missing separate appointment time does not make the row Gray. Missing `Full Name`, `Phone`, `Mailing Street`, `Mailing City`, or `A1 Date` still marks the row Gray with Needs CRM cleanup.

Workflow logic uses `Current Contact Status` as the main appointment status and `A1 Confirm Status` as confirmation support. Scheduled appointments only become Green when `A1 Confirm Status` is Confirmed. Scheduled + Unconfirmed is Red with Final save text today, and Yellow with Send confirmation text tomorrow or in the future. Awaiting Confirm and Awaiting Scheduling are Yellow with Send confirmation text. No Show, Cancel, Pre-App Cancel, Cancel at Door, and DQ before appointment in either `Current Contact Status` or `A1 Status` are Red unless they are past cleanup rows.

The app scans the first 15 rows of Zoho report exports to find the real header row when report name, generated-by, or record-count rows appear above the column headers.

## Dashboard Metrics

Ready for Dispatch Today counts only appointments where the appointment date equals the selected report date, the current contact status is Scheduled, the confirmation status is Confirmed, the risk level is Green, and required fields are complete. This card is intended to show appointments that are safe to send a rep to today.

## Risk Colors

- Green = Confirmed / ready
- Yellow = Needs confirmation
- Red = High risk / final save / do not dispatch
- Gray = Missing data / CRM cleanup

## Column Mapping Debug Mode

Use the sidebar expander after uploading a Zoho export to inspect:

- raw columns detected from the uploaded file
- first five raw rows before normalization
- detected header row when exports contain title/header text above the real column names; the scanner checks the first 15 rows
- mapping result for appointment date, time, customer, phone, address, city, state, status, lead source, rep, confirmer, and notes

If no recognizable mappings are found, the app shows a warning so the export format can be reviewed and new aliases can be added.

## Developer Testing

`sample_data.csv` remains in the project for local checks, but sample data is not loaded automatically. Use the sidebar's Developer testing only expander to enable it.

