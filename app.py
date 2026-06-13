import re
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st


st.set_page_config(page_title="PES Command Center", page_icon=":zap:", layout="wide")


def require_password() -> None:
    try:
        app_password = st.secrets["APP_PASSWORD"]
    except Exception:
        st.warning("Deployment secrets are not configured. Set APP_PASSWORD before using this app.")
        st.stop()

    if not app_password:
        st.warning("Deployment secrets are not configured. Set APP_PASSWORD before using this app.")
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.title("PES Command Center")
    entered_password = st.text_input("Password", type="password")
    if not entered_password:
        st.stop()
    if entered_password != app_password:
        st.error("Incorrect password.")
        st.stop()
    st.session_state["authenticated"] = True
    st.rerun()


require_password()

STATUS_CONFIRMED = {
    "confirmed",
    "appt confirmed",
    "appointment confirmed",
    "customer confirmed",
    "confirmed by phone",
    "confirmed by text",
    "replied yes",
    "reply yes",
    "said yes",
    "show confirmed",
    "yes",
}
STATUS_CANCEL_RISK = {
    "cancelled",
    "canceled",
    "cancel",
    "pre-app cancel",
    "pre app cancel",
    "pre appointment cancel",
    "customer no show",
    "no show",
    "cancel at door",
    "cad",
    "dq before appointment",
    "dq before appt",
    "dq pre appointment",
}
PAYABLE_SITS = {"sale", "no sale", "dq in home"}
NON_PAYABLE = {"customer no show", "pre-app cancel", "pre app cancel", "cancel at door"}
HIGH_RISK_WORDS = {
    "no answer",
    "na",
    "left voicemail",
    "lm",
    "lvm",
    "bad number",
    "wrong number",
    "reschedule",
    "cancel",
    "no show",
    "not confirmed",
    "failed confirmation",
    "could not confirm",
    "did not answer",
}
KEY_FIELDS = ["customer_name", "phone", "address", "city", "appointment_date"]
MISSING_FIELD_VALUES = {"", "nan", "none", "n/a", "na", "null", "nil", "-", "--"}
DEBUG_MAPPING_FIELDS = [
    ("appointment_datetime", "appointment_datetime"),
    ("appointment_date", "appointment_date"),
    ("appointment_time", "appointment_time"),
    ("customer_name", "customer_name"),
    ("phone", "phone"),
    ("address", "address"),
    ("city", "city"),
    ("zip", "zip"),
    ("state", "state"),
    ("status", "status"),
    ("current_contact_status", "current_contact_status"),
    ("confirmation_status", "confirmation_status"),
    ("lead_source", "lead_source"),
    ("rep_osr", "rep"),
    ("inside_sales_rep", "inside_sales_rep"),
    ("qualification_status", "qualification_status"),
    ("vetter_grade", "vetter_grade"),
    ("a1_status", "a1_status"),
    ("confirmer", "confirmer"),
    ("notes", "notes"),
]

COLUMN_ALIASES = {
    "appointment_datetime": [
        "a1 date",
        "appointment datetime",
        "appointment date time",
        "appt datetime",
    ],
    "appointment_date": [
        "appointment date",
        "appt date",
        "appointment day",
        "a1 date",
        "date",
        "scheduled date",
        "meeting date",
        "created time",
        "modified time",
        "start date",
        "install date",
    ],
    "appointment_time": [
        "appointment time",
        "a1 time",
        "appt time",
        "time",
        "scheduled time",
        "start time",
        "slot",
    ],
    "customer_name": [
        "full name",
        "contact name",
        "deal name",
        "customer name",
        "name",
        "client name",
        "lead name",
        "homeowner",
    ],
    "phone": ["phone", "mobile", "mobile phone", "phone number", "contact phone", "cell", "customer phone", "primary phone"],
    "address": ["address", "street", "street address", "mailing street", "service address", "installation address", "customer address", "home address"],
    "city": ["city", "mailing city", "service city", "town"],
    "zip": ["zip", "zip code", "postal code", "mailing zip", "mailing zip code", "service zip"],
    "state": ["state", "mailing state", "service state", "st"],
    "status": ["current contact status", "status", "appointment status", "appt status", "disposition", "stage", "outcome"],
    "current_contact_status": ["current contact status"],
    "confirmation_status": ["a1 confirm status", "confirm status", "confirmation status"],
    "lead_source": ["lead source", "source", "marketing source", "appointment source", "lead type"],
    "rep_osr": ["a1 osr", "rep", "osr", "sales rep", "energy advisor", "consultant", "owner", "deal owner", "advisor"],
    "inside_sales_rep": ["a1 inside sales rep", "inside sales rep", "isr"],
    "qualification_status": ["qualifications status", "qualification status"],
    "vetter_grade": ["vetter grade"],
    "a1_status": ["a1 status"],
    "confirmer": ["a1 confirmer", "confirmer", "confirmed by", "confirmation rep", "appointment setter", "setter", "sdr", "csr"],
    "notes": ["notes", "note", "comments", "description", "latest note", "call notes", "confirmation notes", "last note"],
}

DISPLAY_COLUMNS = [
    "customer_name",
    "appointment_date",
    "appointment_time",
    "risk_level",
    "recommended_action",
    "confirmation_status",
    "current_contact_status",
    "phone",
    "address",
    "city",
    "zip",
    "rep",
    "inside_sales_rep",
    "confirmer",
    "lead_source",
    "qualification_status",
    "vetter_grade",
    "a1_status",
    "text_message",
    "bucket",
    "lead_channel",
    "state",
    "status",
    "sit_payable",
]

COMPACT_DISPLAY_COLUMNS = [
    "customer_name",
    "appointment_time",
    "risk_level",
    "recommended_action",
    "confirmation_status",
    "current_contact_status",
    "phone",
    "city",
    "rep",
    "text_message",
]


def clean_column_name(name: object) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def base_clean_column_name(name: object) -> str:
    text = clean_column_name(name)
    return re.sub(r"_\d+$", "", text)


def alias_lookup() -> dict[str, str]:
    reverse_aliases = {}
    for standard, aliases in COLUMN_ALIASES.items():
        reverse_aliases[clean_column_name(standard)] = standard
        for alias in aliases:
            reverse_aliases[clean_column_name(alias)] = standard
    return reverse_aliases


def build_column_mapping(columns: list[object]) -> dict[str, object]:
    reverse_aliases = alias_lookup()
    mapping = {standard: None for standard in COLUMN_ALIASES}
    used_targets = set()
    for original_col in columns:
        clean_col = clean_column_name(original_col)
        target = reverse_aliases.get(clean_col)
        if target and target not in used_targets:
            mapping[target] = original_col
            used_targets.add(target)
        if clean_col == "a1_date":
            mapping["appointment_datetime"] = original_col
            mapping["appointment_date"] = original_col
            mapping["appointment_time"] = original_col
        if clean_col == "current_contact_status":
            mapping["status"] = original_col
            mapping["current_contact_status"] = original_col
    return mapping


def clean_rep_value(value: object) -> str:
    text = normalize_text_value(value)
    if re.search(r"\(\s*\d+\s*\)$", text):
        return ""
    return text


def choose_rep(row: pd.Series) -> str:
    rep_candidates = []
    for col in row.index:
        if base_clean_column_name(col) == "a1_osr" or clean_column_name(col) in {"rep_osr", "rep"}:
            rep_candidates.append(row.get(col, ""))
    for value in rep_candidates:
        clean_value = clean_rep_value(value)
        if clean_value:
            return clean_value
    return first_present_value(*rep_candidates)


def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    normalized = df.copy()
    mapping = build_column_mapping(list(normalized.columns))
    rename_map = {}
    mapped_originals = set()

    for target, original_col in mapping.items():
        if original_col is not None:
            if target in {"appointment_date", "appointment_time"} and original_col == mapping.get("appointment_datetime"):
                continue
            rename_map[original_col] = target
            mapped_originals.add(original_col)

    for col in normalized.columns:
        if col not in mapped_originals:
            rename_map[col] = clean_column_name(col)

    normalized = normalized.rename(columns=rename_map)
    for standard in COLUMN_ALIASES:
        if standard not in normalized.columns:
            normalized[standard] = ""
    if mapping.get("current_contact_status") is not None:
        normalized["current_contact_status"] = df[mapping["current_contact_status"]]
        normalized["status"] = df[mapping["current_contact_status"]]
    if mapping.get("appointment_datetime") is not None:
        normalized["appointment_datetime"] = df[mapping["appointment_datetime"]]
        normalized["appointment_date"] = df[mapping["appointment_datetime"]]
    if "a1_osr_1" not in normalized.columns:
        normalized["a1_osr_1"] = ""
    return normalized, mapping


def mapping_debug_frame(mapping: dict[str, object]) -> pd.DataFrame:
    rows = []
    for standard, label in DEBUG_MAPPING_FIELDS:
        rows.append({"field": label, "mapped from": mapping.get(standard) or "Not found"})
    return pd.DataFrame(rows)


def score_possible_header(row: pd.Series) -> int:
    reverse_aliases = alias_lookup()
    matched_fields = set()
    for value in row.dropna().tolist():
        target = reverse_aliases.get(clean_column_name(value))
        if target:
            matched_fields.add(target)
    return len(matched_fields)


def detect_header_row(preview: pd.DataFrame) -> int:
    best_row = 0
    best_score = 0
    for row_index, row in preview.head(15).iterrows():
        score = score_possible_header(row)
        if score > best_score:
            best_row = int(row_index)
            best_score = score
    return best_row if best_score > 0 else 0


def read_table_from_bytes(file_bytes: bytes, name: str, header_row: int | None = 0, nrows: int | None = None) -> pd.DataFrame:
    buffer = BytesIO(file_bytes)
    if name.endswith(".csv"):
        return pd.read_csv(buffer, header=header_row, nrows=nrows)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(buffer, header=header_row, nrows=nrows)
    raise ValueError("Please upload a CSV or Excel file.")


def make_import_debug(raw_df: pd.DataFrame, header_row: int) -> dict[str, object]:
    mapping = build_column_mapping(list(raw_df.columns))
    return {
        "header_row": header_row,
        "raw_columns": list(raw_df.columns),
        "raw_preview": raw_df.head(5),
        "mapping": mapping,
        "mapping_found": any(value is not None for value in mapping.values()),
    }


def combine_date_time(row: pd.Series) -> tuple[object, str]:
    raw_date = row.get("appointment_datetime", "") or row.get("appointment_date", "")
    raw_time = row.get("appointment_time", "")

    parsed_date = pd.to_datetime(raw_date, errors="coerce")
    parsed_time = pd.to_datetime(raw_time, errors="coerce")

    display_time = ""
    if pd.notna(parsed_time):
        display_time = parsed_time.strftime("%I:%M %p").lstrip("0") if hasattr(parsed_time, "strftime") else str(raw_time)
    elif pd.notna(parsed_date) and (
        parsed_date.hour != 0 or parsed_date.minute != 0 or parsed_date.second != 0
    ):
        display_time = parsed_date.strftime("%I:%M %p").lstrip("0")

    if pd.isna(parsed_date):
        combined = pd.to_datetime(f"{raw_date} {raw_time}", errors="coerce")
        if pd.notna(combined):
            parsed_date = combined
            if not display_time:
                display_time = combined.strftime("%I:%M %p").lstrip("0")

    return parsed_date, display_time


def date_bucket(appt_date: object, today: date) -> str:
    if pd.isna(appt_date):
        return "Past / needs cleanup"
    appt_day = appt_date.date()
    if appt_day == today:
        return "Today"
    if appt_day == today + timedelta(days=1):
        return "Tomorrow"
    if appt_day > today + timedelta(days=1):
        return "Future"
    return "Past / needs cleanup"


def lower_text(*values: object) -> str:
    return " ".join(str(v).lower().strip() for v in values if pd.notna(v))


def normalize_text_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def is_missing_value(value: object) -> bool:
    text = normalize_text_value(value)
    return text.lower() in MISSING_FIELD_VALUES


def is_missing_field(field: str, value: object) -> bool:
    if is_missing_value(value):
        return True
    if field == "phone":
        digits = re.sub(r"\D", "", normalize_text_value(value))
        return len(digits) < 7
    return False


def missing_key_fields(row: pd.Series) -> list[str]:
    return [field for field in KEY_FIELDS if is_missing_field(field, row.get(field, ""))]


def first_present_value(*values: object) -> str:
    for value in values:
        if not is_missing_value(value):
            return normalize_text_value(value)
    return ""


def first_name(full_name: object) -> str:
    text = normalize_text_value(full_name)
    if is_missing_value(text):
        return "there"
    return text.split()[0].strip(",") or "there"


def is_confirmed(*values: str) -> bool:
    haystack = " ".join(values).lower()
    haystack = re.sub(r"[^a-z0-9]+", " ", haystack).strip()
    for term in STATUS_CONFIRMED:
        clean_term = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
        if re.search(rf"\b{re.escape(clean_term)}\b", haystack):
            return True
    return False


def is_new_status(status_text: str) -> bool:
    return status_text == "new"


def is_unconfirmed_status(value: str) -> bool:
    return "unconfirmed" in value or "not confirmed" in value


def is_confirmation_status_confirmed(value: str) -> bool:
    return not is_unconfirmed_status(value) and is_confirmed(value)


def has_cancel_risk(status_text: str) -> bool:
    return any(term in status_text for term in STATUS_CANCEL_RISK)


def has_note_risk(status_text: str, notes_text: str) -> bool:
    haystack = f"{status_text} {notes_text}".lower()
    # Failed contact attempts raise no-show risk because a rep may be dispatched to an unconfirmed home.
    return any(term in haystack for term in HIGH_RISK_WORDS)


def lead_channel(lead_source: object) -> str:
    source = str(lead_source).strip().lower()
    if source in {"website", "employee self gen"}:
        return "Website / Employee Self Gen"
    if not source:
        return "Call center"
    return "Call center"


def sit_payable(status: object) -> str:
    text = str(status).strip().lower()
    if text in PAYABLE_SITS:
        return "Payable sit"
    if text in NON_PAYABLE:
        return "Not payable"
    return ""


def assess_row(row: pd.Series, today: date) -> pd.Series:
    status_text = normalize_text_value(row.get("status", "")).lower()
    current_contact_status = normalize_text_value(row.get("current_contact_status", row.get("status", ""))).lower()
    confirmation_status = normalize_text_value(row.get("confirmation_status", "")).lower()
    a1_status = normalize_text_value(row.get("a1_status", "")).lower()
    notes_text = normalize_text_value(row.get("notes", "")).lower()
    missing = missing_key_fields(row)
    bucket = row["bucket"]
    confirmation_confirmed = is_confirmation_status_confirmed(confirmation_status)
    confirmation_unconfirmed = is_unconfirmed_status(confirmation_status)
    confirmed = confirmation_confirmed or (not confirmation_unconfirmed and is_confirmed(status_text, notes_text))
    new_status = is_new_status(status_text)
    cancel_risk = has_cancel_risk(status_text) or has_cancel_risk(current_contact_status) or has_cancel_risk(a1_status)
    note_risk = has_note_risk(status_text, notes_text)

    if missing:
        return pd.Series({"risk_level": "Gray", "recommended_action": "Needs CRM cleanup", "missing_fields": ", ".join(missing)})

    if cancel_risk and bucket == "Past / needs cleanup":
        return pd.Series({"risk_level": "Red", "recommended_action": "Needs CRM cleanup", "missing_fields": ""})

    if cancel_risk:
        return pd.Series({"risk_level": "Red", "recommended_action": "Do not dispatch until confirmed", "missing_fields": ""})

    if note_risk:
        if bucket == "Today":
            return pd.Series({"risk_level": "Red", "recommended_action": "Final save text", "missing_fields": ""})
        return pd.Series({"risk_level": "Red", "recommended_action": "Do not dispatch until confirmed", "missing_fields": ""})

    if "scheduled" in current_contact_status:
        if confirmation_confirmed:
            if bucket == "Today":
                return pd.Series({"risk_level": "Green", "recommended_action": "Send morning-of confirmation", "missing_fields": ""})
            if bucket == "Tomorrow":
                return pd.Series({"risk_level": "Green", "recommended_action": "24-hour reminder", "missing_fields": ""})
            if bucket == "Future":
                return pd.Series({"risk_level": "Green", "recommended_action": "Route-ready", "missing_fields": ""})
        if confirmation_unconfirmed or not confirmation_confirmed:
            if bucket == "Today":
                return pd.Series({"risk_level": "Red", "recommended_action": "Final save text", "missing_fields": ""})
            return pd.Series({"risk_level": "Yellow", "recommended_action": "Send confirmation text", "missing_fields": ""})

    if confirmed:
        if bucket == "Today":
            return pd.Series({"risk_level": "Green", "recommended_action": "Send morning-of confirmation", "missing_fields": ""})
        if bucket == "Tomorrow":
            return pd.Series({"risk_level": "Green", "recommended_action": "24-hour reminder", "missing_fields": ""})
        return pd.Series({"risk_level": "Green", "recommended_action": "Route-ready", "missing_fields": ""})

    if "awaiting confirm" in current_contact_status or "awaiting scheduling" in current_contact_status:
        return pd.Series({"risk_level": "Yellow", "recommended_action": "Send confirmation text", "missing_fields": ""})

    if new_status and not confirmed:
        if bucket == "Today":
            return pd.Series({"risk_level": "Red", "recommended_action": "Final save text", "missing_fields": ""})
        if bucket in {"Tomorrow", "Future"}:
            return pd.Series({"risk_level": "Yellow", "recommended_action": "Send confirmation text", "missing_fields": ""})

    if bucket == "Today":
        return pd.Series({"risk_level": "Red", "recommended_action": "Final save text", "missing_fields": ""})
    if bucket == "Tomorrow":
        return pd.Series({"risk_level": "Yellow", "recommended_action": "Send confirmation text", "missing_fields": ""})
    if bucket == "Past / needs cleanup":
        return pd.Series({"risk_level": "Yellow", "recommended_action": "Needs CRM cleanup", "missing_fields": ""})
    return pd.Series({"risk_level": "Yellow", "recommended_action": "Send confirmation text", "missing_fields": ""})


def format_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "your scheduled date"
    return parsed.strftime("%A, %B %d").replace(" 0", " ")


def make_message(row: pd.Series, today: date) -> str:
    name = first_name(row.get("customer_name", ""))
    appt_date = format_date(row.get("appointment_date", ""))
    appt_time = normalize_text_value(row.get("appointment_time", "")) or "your scheduled time"
    consultant = first_present_value(row.get("rep", ""), row.get("rep_osr", "")) or "your Energy Advisor"
    bucket = row.get("bucket", "")
    action = row.get("recommended_action", "")
    risk = row.get("risk_level", "")

    if risk == "Gray":
        return ""
    if action in {"Do not dispatch until confirmed", "Final save text"}:
        return (
            f"Hi {name}, I have not been able to confirm today's appointment at {appt_time}.\n"
            "Before I keep the Energy Advisor on the route, can you reply YES to confirm you are still available?\n"
            "If something changed, reply R and I can help reschedule.\n"
            "Power Energy Solutions"
        )
    if bucket == "Today":
        return (
            f"Good morning {name}, your Energy Advisor {consultant} is scheduled for today at {appt_time}.\n"
            "Please reply YES so I can keep the advisor route confirmed. If anything changed, reply R and I will help move the appointment.\n"
            "Power Energy Solutions"
        )
    if bucket == "Tomorrow":
        return (
            f"Hi {name}, quick confirmation for tomorrow at {appt_time}.\n"
            "Your Energy Advisor is already scheduled, and we are holding that time for you. Please reply YES to keep the appointment locked in, or R if something changed.\n"
            "Power Energy Solutions"
        )
    return (
        f"Hi {name}, your Power Energy appointment is locked in for {appt_date} at {appt_time}.\n"
        "Your Energy Advisor will review your current electric rate, what your home may qualify for, and whether there is a real way to lower your monthly cost.\n"
        "Reply YES to confirm or R if we need to reschedule.\n"
        "Power Energy Solutions"
    )


def process_appointments(df: pd.DataFrame, today: date, return_mapping: bool = False):
    data, mapping = normalize_columns(df)
    parsed = data.apply(combine_date_time, axis=1, result_type="expand")
    data["appointment_date_parsed"] = parsed[0]
    data["appointment_time"] = parsed[1].where(parsed[1].astype(str).str.strip() != "", data["appointment_time"].astype(str))
    data["appointment_date"] = data["appointment_date_parsed"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "")
    data["rep"] = data.apply(choose_rep, axis=1)
    data["bucket"] = data["appointment_date_parsed"].apply(lambda x: date_bucket(x, today))
    data["lead_channel"] = data["lead_source"].apply(lead_channel)
    data["sit_payable"] = data["status"].apply(sit_payable)

    assessment = data.apply(lambda row: assess_row(row, today), axis=1)
    data = pd.concat([data, assessment], axis=1)
    data["text_message"] = data.apply(lambda row: make_message(row, today), axis=1)
    if return_mapping:
        return data, mapping
    return data


def read_upload(uploaded_file) -> tuple[pd.DataFrame, dict[str, object]]:
    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()
    preview = read_table_from_bytes(file_bytes, name, header_row=None, nrows=15)
    header_row = detect_header_row(preview)
    raw_df = read_table_from_bytes(file_bytes, name, header_row=header_row)
    return raw_df, make_import_debug(raw_df, header_row)


def sample_dataframe() -> tuple[pd.DataFrame, dict[str, object]]:
    raw_df = pd.read_csv("sample_data.csv")
    return raw_df, make_import_debug(raw_df, 0)


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def ready_for_dispatch_today_count(df: pd.DataFrame, selected_date: date) -> int:
    selected_date_text = selected_date.isoformat()
    scheduled = df["status"].apply(lambda value: "scheduled" in normalize_text_value(value).lower())
    confirmed = df["confirmation_status"].apply(lambda value: is_confirmation_status_confirmed(normalize_text_value(value).lower()))
    return int(
        (
            (df["appointment_date"] == selected_date_text)
            & scheduled
            & confirmed
            & (df["risk_level"] == "Green")
            & (df["missing_fields"].fillna("") == "")
        ).sum()
    )


def risk_style_value(value: object) -> str:
    text = normalize_text_value(value).lower()
    if text == "green":
        return "background-color: #d8f3dc; color: #0f3d22; font-weight: 600;"
    if text == "yellow":
        return "background-color: #fff3bf; color: #4f3700; font-weight: 600;"
    if text == "red":
        return "background-color: #ffd6d6; color: #5f1111; font-weight: 600;"
    if text == "gray":
        return "background-color: #e9ecef; color: #2f3437; font-weight: 600;"
    return ""


def action_style_value(value: object) -> str:
    text = normalize_text_value(value).lower()
    if text in {"route-ready", "send morning-of confirmation", "24-hour reminder"}:
        return risk_style_value("Green")
    if text in {"send confirmation text", "call before dispatch"}:
        return risk_style_value("Yellow")
    if text in {"final save text", "do not dispatch until confirmed"}:
        return risk_style_value("Red")
    if text == "needs crm cleanup":
        return risk_style_value("Gray")
    return ""


def confirmation_style_value(value: object) -> str:
    text = normalize_text_value(value).lower()
    if is_confirmation_status_confirmed(text):
        return risk_style_value("Green")
    if is_unconfirmed_status(text):
        return risk_style_value("Yellow")
    return ""


def style_appointment_table(df: pd.DataFrame):
    style_map = {
        "risk_level": risk_style_value,
        "recommended_action": action_style_value,
        "confirmation_status": confirmation_style_value,
    }
    styled = df.style
    for column, style_func in style_map.items():
        if column in df.columns:
            styled = styled.map(style_func, subset=[column])
    return styled


st.title("PES Command Center")
st.caption("Daily sit-rate control for Power Energy Solutions LLC")

with st.sidebar:
    st.header("Import")
    uploaded_file = st.file_uploader("Upload Zoho appointment export", type=["csv", "xlsx", "xls"])
    with st.expander("Developer testing only"):
        use_sample = st.checkbox("Use sample data", value=False)
    selected_date = st.date_input("Report date", value=date.today())

try:
    if uploaded_file is not None:
        raw_df, import_debug = read_upload(uploaded_file)
    elif use_sample:
        raw_df, import_debug = sample_dataframe()
    else:
        raw_df = pd.DataFrame()
        import_debug = make_import_debug(raw_df, 0)
except Exception as exc:
    st.error(f"Could not read file: {exc}")
    st.stop()

with st.sidebar.expander("Column Mapping Debug"):
    st.write(f"Detected header row: {int(import_debug['header_row']) + 1}")
    st.write("Raw columns detected")
    st.write([str(col) for col in import_debug["raw_columns"]])
    st.write("First 5 raw rows")
    st.dataframe(import_debug["raw_preview"], use_container_width=True)
    st.write("Mapping result")
    st.dataframe(mapping_debug_frame(import_debug["mapping"]), use_container_width=True, hide_index=True)
    if not import_debug["mapping_found"]:
        st.warning("The app could not identify the Zoho headers. Check the raw columns above and add aliases for this export format.")

if raw_df.empty:
    st.info("Upload a CSV/XLSX Zoho appointment export to start.")
    st.stop()

report, column_mapping = process_appointments(raw_df, selected_date, return_mapping=True)

confirmed_count = int((report["risk_level"] == "Green").sum())
needs_confirmation_count = int((report["risk_level"] == "Yellow").sum())
high_risk_count = int((report["risk_level"] == "Red").sum())
missing_count = int((report["risk_level"] == "Gray").sum())
ready_for_dispatch_today = ready_for_dispatch_today_count(report, selected_date)

summary_cols = st.columns(6)
summary_cols[0].metric("Total appointments", len(report))
summary_cols[1].metric("Confirmed", confirmed_count)
summary_cols[2].metric("Needs confirmation", needs_confirmation_count)
summary_cols[3].metric("High risk", high_risk_count)
summary_cols[4].metric("Missing data", missing_count)
summary_cols[5].metric("Ready for Dispatch Today", ready_for_dispatch_today)

st.divider()

filters = st.columns(4)
with filters[0]:
    bucket_filter = st.multiselect("Date group", sorted(report["bucket"].dropna().unique()), default=sorted(report["bucket"].dropna().unique()))
with filters[1]:
    risk_filter = st.multiselect("Risk", ["Green", "Yellow", "Red", "Gray"], default=["Green", "Yellow", "Red", "Gray"])
with filters[2]:
    action_filter = st.multiselect("Action", sorted(report["recommended_action"].dropna().unique()), default=sorted(report["recommended_action"].dropna().unique()))
with filters[3]:
    channel_filter = st.multiselect("Lead channel", sorted(report["lead_channel"].dropna().unique()), default=sorted(report["lead_channel"].dropna().unique()))

filtered = report[
    report["bucket"].isin(bucket_filter)
    & report["risk_level"].isin(risk_filter)
    & report["recommended_action"].isin(action_filter)
    & report["lead_channel"].isin(channel_filter)
].copy()

st.subheader("Appointment Table")
st.caption("Green = Confirmed / ready | Yellow = Needs confirmation | Red = High risk | Gray = Missing data / CRM cleanup")
compact_view = st.toggle("Compact table view", value=True)
table_columns = COMPACT_DISPLAY_COLUMNS if compact_view else DISPLAY_COLUMNS
visible_cols = [col for col in table_columns if col in filtered.columns]
styled_table = style_appointment_table(filtered[visible_cols])
st.dataframe(styled_table, use_container_width=True, hide_index=True, height=650)

st.download_button(
    "Export filtered action report CSV",
    data=csv_bytes(filtered[visible_cols]),
    file_name=f"pes_sit_rate_action_report_{selected_date.isoformat()}.csv",
    mime="text/csv",
)

st.subheader("Daily Action List")

action_groups = {
    "Call first": ["Call before dispatch"],
    "Text now": ["Send confirmation text", "Send morning-of confirmation", "24-hour reminder", "Final save text"],
    "Route-ready": ["Route-ready"],
    "Do not dispatch yet": ["Do not dispatch until confirmed"],
    "CRM cleanup": ["Needs CRM cleanup"],
}

tabs = st.tabs(list(action_groups.keys()))
for tab, (label, actions) in zip(tabs, action_groups.items()):
    with tab:
        subset = report[report["recommended_action"].isin(actions)].copy()
        if subset.empty:
            st.success("No appointments in this lane.")
        else:
            for _, row in subset.iterrows():
                title = f"{row.get('appointment_time', '')} | {row.get('customer_name', '')} | {row.get('city', '')}, {row.get('state', '')}"
                with st.expander(title):
                    st.write(f"Risk: {row.get('risk_level', '')}")
                    st.write(f"Status: {row.get('status', '')}")
                    st.write(f"Phone: {row.get('phone', '')}")
                    st.write(f"Address: {row.get('address', '')}")
                    notes = str(row.get("notes", "")).strip()
                    if notes:
                        st.write(f"Notes: {notes}")
                    message = str(row.get("text_message", "")).strip()
                    if message:
                        st.text_area("Copy/paste text", value=message, height=150, key=f"msg_{label}_{row.name}")


