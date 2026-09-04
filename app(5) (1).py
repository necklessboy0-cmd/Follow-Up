import os
import io
import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None


# -----------------------------
# Page configuration
# -----------------------------
st.set_page_config(
    page_title="Aurora Follow-Up",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --navy: #07152f;
        --blue: #0b4ea2;
        --blue2: #176fc1;
        --gold: #d7aa42;
        --gold2: #f1d37a;
        --ink: #10213e;
        --muted: #61708a;
        --panel: rgba(255,255,255,.92);
        --border: rgba(215,170,66,.35);
    }

    html, body, [class*="css"] {
        font-family: "Inter", sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at 78% 11%, rgba(241,211,122,.22) 0 1px, transparent 2px),
            radial-gradient(circle at 18% 22%, rgba(255,255,255,.28) 0 1px, transparent 2px),
            radial-gradient(circle at 65% 32%, rgba(255,255,255,.22) 0 1px, transparent 2px),
            radial-gradient(circle at 88% 55%, rgba(241,211,122,.20) 0 1px, transparent 2px),
            linear-gradient(135deg, #06122b 0%, #0a397a 45%, #0b5da7 62%, #b9892e 100%);
        background-attachment: fixed;
    }

    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background:
            linear-gradient(115deg, transparent 0 47%, rgba(241,211,122,.13) 49%, transparent 51%),
            linear-gradient(25deg, transparent 0 67%, rgba(255,255,255,.07) 68%, transparent 70%);
        opacity: .7;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(5,19,45,.97), rgba(10,58,111,.97));
        border-right: 1px solid rgba(241,211,122,.25);
    }

    section[data-testid="stSidebar"] * {
        color: #f7f3e7;
    }

    .hero {
        padding: 2rem 2.2rem;
        border: 1px solid rgba(241,211,122,.45);
        border-radius: 24px;
        background:
            linear-gradient(120deg, rgba(5,20,48,.93), rgba(10,78,146,.80) 58%, rgba(187,139,44,.58));
        box-shadow: 0 20px 60px rgba(0,0,0,.25);
        margin-bottom: 1.2rem;
    }

    .hero h1 {
        color: white;
        font-size: clamp(2rem, 4vw, 3.5rem);
        margin: 0 0 .35rem 0;
        letter-spacing: -1.5px;
    }

    .hero p {
        color: #eef5ff;
        margin: 0;
        font-size: 1.03rem;
    }

    .gold {
        color: #f1d37a;
    }

    .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1.1rem 1.2rem;
        box-shadow: 0 14px 40px rgba(2,18,42,.16);
    }

    .metric {
        background: linear-gradient(145deg, rgba(255,255,255,.97), rgba(245,249,255,.91));
        border: 1px solid rgba(215,170,66,.35);
        border-radius: 16px;
        padding: 1rem 1.1rem;
        min-height: 105px;
    }

    .metric .label {
        color: #66758d;
        font-size: .8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .08em;
    }

    .metric .value {
        color: #0b3974;
        font-size: 1.75rem;
        font-weight: 800;
        margin-top: .25rem;
    }

    .stButton > button {
        border-radius: 11px;
        border: 1px solid rgba(215,170,66,.55);
        font-weight: 700;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #0a4d9b, #126fc0);
        color: white;
    }

    div[data-baseweb="tab-list"] {
        gap: 6px;
    }

    button[data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        font-weight: 700;
    }

    .small-note {
        color: #d8e7fa;
        font-size: .78rem;
    }

    .stTextArea textarea, .stTextInput input, .stNumberInput input {
        border-radius: 10px;
    }

    .footer {
        text-align: center;
        color: rgba(255,255,255,.72);
        font-size: .78rem;
        padding: 1.5rem 0 .5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Session state
# -----------------------------
if "invoices" not in st.session_state:
    st.session_state.invoices = pd.DataFrame(
        columns=[
            "Client",
            "Company",
            "Invoice",
            "Amount",
            "Currency",
            "Invoice Date",
            "Due Date",
            "Status",
            "Last Follow-up",
            "Next Follow-up",
            "Notes",
        ]
    )

if "generated" not in st.session_state:
    st.session_state.generated = ""

if "generated_subject" not in st.session_state:
    st.session_state.generated_subject = ""

if "last_client_reply" not in st.session_state:
    st.session_state.last_client_reply = ""


# -----------------------------
# Helpers
# -----------------------------
def get_secret(name: str):
    """Read a Streamlit secret first, then environment variable."""
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name)


def money(value, currency):
    try:
        return f"{currency} {float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{currency} 0.00"


def normalize_date(value):
    if pd.isna(value) or value == "":
        return ""
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return str(value)


def safe_text(value):
    return "" if value is None else str(value).strip()


def build_context(client, company, invoice, amount, currency, due_date, status, tone, channel):
    return f"""
Client: {client or "Not provided"}
Company: {company or "Not provided"}
Invoice/reference: {invoice or "Not provided"}
Amount: {money(amount, currency) if amount is not None else "Not provided"}
Due date: {due_date or "Not provided"}
Payment status: {status}
Requested tone: {tone}
Channel: {channel}
"""


def local_template_followup(
    client,
    company,
    invoice,
    amount,
    currency,
    due_date,
    status,
    tone,
    channel,
    stage,
    extra,
):
    greeting = f"Dear {client}," if client else "Dear Client,"
    company_line = f" for {company}" if company else ""
    invoice_line = f" regarding invoice {invoice}" if invoice else ""
    amount_line = (
        f" for {money(amount, currency)}"
        if amount is not None and amount != ""
        else ""
    )
    due_line = f" The due date was {due_date}." if due_date else ""

    if stage == "First payment reminder":
        opening = (
            f"I hope you are doing well. I am writing to kindly follow up{invoice_line}"
            f"{amount_line}{company_line}."
        )
        body = (
            f"Our records indicate that the payment is currently marked as {status.lower()}."
            f"{due_line} Could you please confirm the expected payment date at your convenience?"
        )
        close = "Thank you for your attention and continued cooperation."
    elif stage == "Due-date reminder":
        opening = f"I hope you are well. This is a courteous reminder{invoice_line}{amount_line}."
        body = (
            f"The payment is due{f' on {due_date}' if due_date else ''}. "
            "Please let us know if the payment has already been scheduled or completed."
        )
        close = "Thank you, and please let us know if you need any information from our side."
    elif stage == "Overdue payment":
        opening = f"I am writing to follow up on the outstanding payment{invoice_line}{amount_line}."
        body = (
            f"Our records show that the payment remains {status.lower()}.{due_line} "
            "We would appreciate an update on the payment status and expected settlement date."
        )
        close = "We appreciate your prompt attention to this matter."
    elif stage == "Second follow-up":
        opening = f"I wanted to follow up again regarding{invoice_line}{amount_line}."
        body = (
            "We have not yet received confirmation of the payment status. "
            "Could you please provide an update or advise us of the expected payment date?"
        )
        close = "Thank you for your cooperation."
    elif stage == "Final reminder":
        opening = f"This is a final courteous follow-up regarding{invoice_line}{amount_line}."
        body = (
            "The balance remains outstanding, and we would appreciate your confirmation "
            "of the payment arrangements or expected settlement date."
        )
        close = "Please let us know promptly if there is anything preventing settlement."
    elif stage == "Payment confirmation request":
        opening = f"I am following up to confirm the payment status for{invoice_line}{amount_line}."
        body = (
            "If payment has already been made, please share the payment confirmation or "
            "reference so that we can update our records."
        )
        close = "Thank you for helping us keep our records accurate."
    elif stage == "Partial-payment follow-up":
        opening = f"I am following up regarding the remaining balance{invoice_line}."
        body = (
            "Thank you for any payment already received. Could you please confirm the "
            "remaining balance and expected date for the outstanding amount?"
        )
        close = "We appreciate your continued cooperation."
    elif stage == "Promised-payment follow-up":
        opening = f"I am following up regarding the payment date previously discussed{invoice_line}."
        body = (
            "Could you please confirm whether the payment is still scheduled for the agreed "
            "date, or provide an updated timeline if circumstances have changed?"
        )
        close = "Thank you for keeping us updated."
    elif stage == "No-response follow-up":
        opening = f"I wanted to follow up once more regarding{invoice_line}{amount_line}."
        body = (
            "We have not yet received a response to our previous messages. "
            "When convenient, please confirm the current payment status and expected next step."
        )
        close = "Thank you for your attention."
    else:
        opening = f"I hope you are doing well. I am following up regarding{invoice_line}{amount_line}."
        body = "Please share an update when convenient so that we can keep our records current."
        close = "Thank you for your cooperation."

    tone_prefix = ""
    if tone == "Firm":
        tone_prefix = "We would appreciate your prompt attention to this request. "
    elif tone == "Very firm":
        tone_prefix = "We require a clear update on the payment status and expected settlement date. "

    extra_line = f"\n\nAdditional context: {extra}" if extra else ""

    subject = (
        f"Payment Follow-Up"
        + (f" — {invoice}" if invoice else "")
        + (f" — {company}" if company else "")
    )

    message = (
        f"{greeting}\n\n"
        f"{opening}\n\n"
        f"{tone_prefix}{body}{extra_line}\n\n"
        f"{close}\n\n"
        "Kind regards,\n"
        "[Your Name]\n"
        "[Company Name]"
    )

    return subject, message


def generate_with_gemini(prompt: str):
    api_key = get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY")
    if not api_key or genai is None:
        return None

    try:
        client = genai.Client(api_key=api_key)
        model_name = get_secret("GEMINI_MODEL") or "gemini-2.5-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        text = getattr(response, "text", None)
        return text.strip() if text else None
    except Exception as exc:
        st.warning(f"AI generation was unavailable, so the built-in professional template was used. ({exc})")
        return None


def parse_ai_output(text):
    subject = ""
    message = text.strip()

    match = re.search(r"(?im)^subject\s*:\s*(.+)$", message)
    if match:
        subject = match.group(1).strip()
        message = re.sub(r"(?im)^subject\s*:\s*.+$\n?", "", message).strip()

    return subject, message


def generate_followup(data):
    stage = data["stage"]
    tone = data["tone"]
    length = data["length"]
    channel = data["channel"]

    subject, fallback = local_template_followup(
        data["client"],
        data["company"],
        data["invoice"],
        data["amount"],
        data["currency"],
        data["due_date"],
        data["status"],
        tone,
        channel,
        stage,
        data["extra"],
    )

    prompt = f"""
You are a senior business communications specialist.

Create a {length.lower()} {channel} follow-up for a client.
Purpose/stage: {stage}
Tone: {tone}

{build_context(
    data["client"],
    data["company"],
    data["invoice"],
    data["amount"],
    data["currency"],
    data["due_date"],
    data["status"],
    tone,
    channel,
)}

Additional context: {data["extra"] or "None"}

Rules:
- Be polished, concise, respectful, and business-appropriate.
- Clearly request the needed action without sounding threatening or accusatory.
- Never invent facts, fees, legal consequences, payment terms, dates, or promises.
- If information is missing, phrase the request generally rather than guessing.
- For email, output "Subject: ..." followed by the message.
- For WhatsApp/SMS, keep it concise and natural.
- Do not use emojis unless the requested tone explicitly calls for them.
"""
    ai_text = generate_with_gemini(prompt)
    if ai_text:
        ai_subject, ai_message = parse_ai_output(ai_text)
        return ai_subject or subject, ai_message
    return subject, fallback


def generate_rewrite(original, tone, length, channel):
    prompt = f"""
Rewrite the following client-facing business message into a professional {channel} message.

Tone: {tone}
Length: {length}

Rules:
- Preserve the original facts and intended request.
- Improve clarity, grammar, professionalism, and diplomacy.
- Do not invent facts, dates, fees, legal claims, or commitments.
- Do not make the message unnecessarily aggressive.
- If it is an email, output "Subject: ..." first.

Original message:
{original}
"""
    ai_text = generate_with_gemini(prompt)
    if ai_text:
        return parse_ai_output(ai_text)

    # Safe non-AI fallback
    subject = "Professional Follow-Up"
    rewritten = (
        "Dear Client,\n\n"
        "I hope you are doing well.\n\n"
        "I am writing to follow up on the matter mentioned below. "
        "Could you please provide an update when convenient?\n\n"
        f"{original.strip()}\n\n"
        "Thank you for your time and cooperation.\n\n"
        "Kind regards,\n"
        "[Your Name]"
    )
    return subject, rewritten


def generate_reply(client_reply, scenario, tone, channel):
    prompt = f"""
Draft a professional response to a client's message.

Channel: {channel}
Tone: {tone}
Situation: {scenario}

Client's message:
{client_reply}

Rules:
- Acknowledge the client's message appropriately.
- Respond only to facts present in the client's message.
- If they propose a payment date, confirm or politely request a clear date as appropriate.
- Do not invent agreements or concessions.
- Keep it professional and concise.
- For email, include a subject line.
"""
    ai_text = generate_with_gemini(prompt)
    if ai_text:
        return parse_ai_output(ai_text)

    return (
        "Re: Payment Follow-Up",
        (
            f"Dear {scenario if scenario else 'Client'},\n\n"
            "Thank you for your message and for the update. "
            "We appreciate you keeping us informed.\n\n"
            "Please confirm the expected payment date so that we can update our records accordingly.\n\n"
            "Kind regards,\n[Your Name]"
        ),
    )


def status_from_due(due_date, status):
    if status == "Paid":
        return "Paid"
    if not due_date:
        return status
    try:
        due = pd.to_datetime(due_date).date()
        if due < date.today():
            return "Overdue"
        if due <= date.today() + timedelta(days=3):
            return "Due Soon"
    except Exception:
        pass
    return status


# -----------------------------
# Header
# -----------------------------
st.markdown(
    """
    <div class="hero">
        <h1>✦ Aurora <span class="gold">Follow-Up</span></h1>
        <p>Professional client communication, payment reminders, response handling, and follow-up tracking — in one workspace.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("## Workspace")
    page = st.radio(
        "Navigate",
        [
            "Dashboard",
            "Payment Follow-Up",
            "Email Rewriter",
            "Client Reply Assistant",
            "Follow-Up Sequence",
            "Client History",
            "Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("### AI status")
    has_key = bool(get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY"))
    if has_key and genai is not None:
        st.success("Gemini AI connected")
    elif has_key and genai is None:
        st.warning("API key found; install google-genai")
    else:
        st.info("Template mode active")
    st.caption("Your API key should be stored in Streamlit Secrets, not in GitHub.")


# -----------------------------
# Dashboard
# -----------------------------
if page == "Dashboard":
    df = st.session_state.invoices.copy()

    total = len(df)
    outstanding = (
        df[df["Status"] != "Paid"]["Amount"].apply(pd.to_numeric, errors="coerce").fillna(0).sum()
        if not df.empty
        else 0
    )
    overdue = (
        len(df[df["Status"].apply(lambda x: status_from_due("", x)) == "Overdue"])
        if not df.empty
        else 0
    )
    paid = len(df[df["Status"] == "Paid"]) if not df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric"><div class="label">Total Records</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric"><div class="label">Outstanding</div><div class="value">{outstanding:,.2f}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric"><div class="label">Overdue</div><div class="value">{overdue}</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric"><div class="label">Paid</div><div class="value">{paid}</div></div>', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Quick start")
    st.write("Add an invoice below, then use **Payment Follow-Up** to create a polished reminder.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.write("")
    with st.expander("Add client / invoice record", expanded=True):
        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Client name", key="dash_client")
        company = c2.text_input("Company", key="dash_company")
        invoice = c3.text_input("Invoice / reference", key="dash_invoice")

        c1, c2, c3 = st.columns(3)
        amount = c1.number_input("Amount", min_value=0.0, step=100.0, key="dash_amount")
        currency = c2.text_input("Currency", value="USD", max_chars=5, key="dash_currency")
        due_date = c3.date_input("Due date", value=date.today(), key="dash_due")

        c1, c2 = st.columns(2)
        status = c1.selectbox("Status", ["Pending", "Due Soon", "Overdue", "Paid"], key="dash_status")
        notes = c2.text_input("Notes", key="dash_notes")

        if st.button("Add record", type="primary", use_container_width=True):
            new_row = {
                "Client": client,
                "Company": company,
                "Invoice": invoice,
                "Amount": amount,
                "Currency": currency.upper(),
                "Invoice Date": date.today().isoformat(),
                "Due Date": due_date.isoformat(),
                "Status": status_from_due(due_date.isoformat(), status),
                "Last Follow-up": "",
                "Next Follow-up": "",
                "Notes": notes,
            }
            st.session_state.invoices = pd.concat(
                [st.session_state.invoices, pd.DataFrame([new_row])],
                ignore_index=True,
            )
            st.success("Record added.")
            st.rerun()

    if not df.empty:
        st.subheader("Current records")
        display_df = df.copy()
        display_df["Status"] = display_df.apply(
            lambda row: status_from_due(row["Due Date"], row["Status"]), axis=1
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)


# -----------------------------
# Payment Follow-Up
# -----------------------------
elif page == "Payment Follow-Up":
    st.subheader("Payment Follow-Up")
    st.caption("Generate a professional message from the client's payment situation.")

    c1, c2, c3 = st.columns(3)
    client = c1.text_input("Client name", key="pf_client")
    company = c2.text_input("Company", key="pf_company")
    invoice = c3.text_input("Invoice / reference", key="pf_invoice")

    c1, c2, c3 = st.columns(3)
    amount = c1.number_input("Amount", min_value=0.0, step=100.0, key="pf_amount")
    currency = c2.text_input("Currency", value="USD", max_chars=5, key="pf_currency")
    due = c3.date_input("Due date", value=date.today(), key="pf_due")

    c1, c2, c3 = st.columns(3)
    stage = c1.selectbox(
        "Follow-up stage",
        [
            "First payment reminder",
            "Due-date reminder",
            "Overdue payment",
            "Second follow-up",
            "Final reminder",
            "Payment confirmation request",
            "Partial-payment follow-up",
            "Promised-payment follow-up",
            "No-response follow-up",
            "General business follow-up",
        ],
        key="pf_stage",
    )
    tone = c2.selectbox("Tone", ["Professional", "Polite", "Friendly", "Firm", "Very firm"], key="pf_tone")
    length = c3.selectbox("Length", ["Short", "Standard", "Detailed"], key="pf_length")

    c1, c2 = st.columns(2)
    channel = c1.selectbox("Channel", ["Email", "WhatsApp", "SMS"], key="pf_channel")
    status = c2.selectbox("Payment status", ["Pending", "Due Soon", "Overdue", "Paid"], key="pf_status")

    extra = st.text_area(
        "Additional context (optional)",
        placeholder="Example: The client previously said payment would be made this week.",
        key="pf_extra",
    )

    if st.button("Generate professional follow-up", type="primary", use_container_width=True):
        subject, message = generate_followup(
            {
                "client": client,
                "company": company,
                "invoice": invoice,
                "amount": amount,
                "currency": currency.upper(),
                "due_date": due.isoformat(),
                "status": status,
                "stage": stage,
                "tone": tone,
                "length": length,
                "channel": channel,
                "extra": extra,
            }
        )
        st.session_state.generated_subject = subject
        st.session_state.generated = message

    if st.session_state.generated:
        st.divider()
        st.subheader("Generated communication")
        st.text_input("Subject", value=st.session_state.generated_subject, key="pf_subject_output")
        st.text_area(
            "Message",
            value=st.session_state.generated,
            height=360,
            key="pf_message_output",
        )
        st.download_button(
            "Download as TXT",
            data=f"Subject: {st.session_state.generated_subject}\n\n{st.session_state.generated}",
            file_name="payment_follow_up.txt",
            mime="text/plain",
        )


# -----------------------------
# Email rewriter
# -----------------------------
elif page == "Email Rewriter":
    st.subheader("Email Rewriter")
    st.caption("Turn a rough message into polished client-facing communication.")

    original = st.text_area(
        "Paste your original message",
        height=250,
        placeholder="Hi, you haven't paid yet. Please pay.",
    )
    c1, c2, c3 = st.columns(3)
    tone = c1.selectbox("Tone", ["Professional", "Polite", "Friendly", "Firm", "Very firm"], key="rw_tone")
    length = c2.selectbox("Length", ["Short", "Standard", "Detailed"], key="rw_length")
    channel = c3.selectbox("Channel", ["Email", "WhatsApp", "SMS"], key="rw_channel")

    if st.button("Rewrite professionally", type="primary", use_container_width=True):
        if not original.strip():
            st.error("Please paste a message first.")
        else:
            subject, message = generate_rewrite(original, tone, length, channel)
            st.session_state.generated_subject = subject
            st.session_state.generated = message

    if st.session_state.generated:
        st.divider()
        st.text_input("Subject", value=st.session_state.generated_subject, key="rw_subject_output")
        st.text_area("Rewritten message", value=st.session_state.generated, height=350, key="rw_message_output")


# -----------------------------
# Client reply assistant
# -----------------------------
elif page == "Client Reply Assistant":
    st.subheader("Client Reply Assistant")
    st.caption("Paste a client's response and generate a professional reply.")

    client_reply = st.text_area(
        "Client's message",
        height=260,
        placeholder="Sorry, we're having a cash-flow issue. Can we pay next Friday?",
        key="cra_reply",
    )
    c1, c2, c3 = st.columns(3)
    scenario = c1.text_input("Client / company", key="cra_client")
    tone = c2.selectbox("Tone", ["Professional", "Polite", "Friendly", "Firm", "Very firm"], key="cra_tone")
    channel = c3.selectbox("Channel", ["Email", "WhatsApp", "SMS"], key="cra_channel")

    if st.button("Draft reply", type="primary", use_container_width=True):
        if not client_reply.strip():
            st.error("Please paste the client's message first.")
        else:
            subject, message = generate_reply(client_reply, scenario, tone, channel)
            st.session_state.last_client_reply = client_reply
            st.session_state.generated_subject = subject
            st.session_state.generated = message

    if st.session_state.generated:
        st.divider()
        st.text_input("Subject", value=st.session_state.generated_subject, key="cra_subject_output")
        st.text_area("Suggested reply", value=st.session_state.generated, height=350, key="cra_message_output")


# -----------------------------
# Follow-up sequence
# -----------------------------
elif page == "Follow-Up Sequence":
    st.subheader("Follow-Up Sequence")
    st.caption("Create a structured reminder plan without making the communication unnecessarily aggressive.")

    c1, c2, c3 = st.columns(3)
    client = c1.text_input("Client name", key="seq_client")
    company = c2.text_input("Company", key="seq_company")
    invoice = c3.text_input("Invoice / reference", key="seq_invoice")

    c1, c2, c3 = st.columns(3)
    amount = c1.number_input("Amount", min_value=0.0, step=100.0, key="seq_amount")
    currency = c2.text_input("Currency", value="USD", max_chars=5, key="seq_currency")
    due = c3.date_input("Due date", value=date.today(), key="seq_due")

    tone = st.selectbox("Default tone", ["Professional", "Polite", "Friendly", "Firm"], key="seq_tone")
    include_final = st.checkbox("Include final reminder", value=True)

    if st.button("Build sequence", type="primary", use_container_width=True):
        stages = [
            ("Day 0", "First payment reminder"),
            ("Due date", "Due-date reminder"),
            ("+3 days", "Overdue payment"),
            ("+7 days", "Second follow-up"),
        ]
        if include_final:
            stages.append(("+14 days", "Final reminder"))

        rows = []
        for timing, stage_name in stages:
            subject, message = local_template_followup(
                client,
                company,
                invoice,
                amount,
                currency.upper(),
                due.isoformat(),
                "Pending",
                tone,
                "Email",
                stage_name,
                "",
            )
            rows.append(
                {
                    "Timing": timing,
                    "Stage": stage_name,
                    "Subject": subject,
                    "Message": message,
                }
            )

        st.session_state.sequence = rows

    if "sequence" in st.session_state:
        for item in st.session_state.sequence:
            with st.expander(f"{item['Timing']} — {item['Stage']}"):
                st.text_input("Subject", value=item["Subject"], key=f"sub_{item['Timing']}_{item['Stage']}")
                st.text_area("Message", value=item["Message"], height=260, key=f"msg_{item['Timing']}_{item['Stage']}")


# -----------------------------
# Client history
# -----------------------------
elif page == "Client History":
    st.subheader("Client History")
    st.caption("Keep a lightweight local record of payment and follow-up activity during the current session.")

    df = st.session_state.invoices.copy()

    if df.empty:
        st.info("No client records yet. Add records from the Dashboard.")
    else:
        search = st.text_input("Search client, company, or invoice")
        filtered = df[
            df.apply(
                lambda row: search.lower() in " ".join(row.astype(str)).lower(),
                axis=1,
            )
        ] if search else df

        st.dataframe(filtered, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Import / export")
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export records as CSV",
            data=csv_data,
            file_name="client_follow_up_records.csv",
            mime="text/csv",
        )

        uploaded = st.file_uploader("Import CSV", type=["csv"])
        if uploaded is not None:
            try:
                imported = pd.read_csv(uploaded)
                required = set(df.columns)
                if required.issubset(imported.columns):
                    st.session_state.invoices = imported
                    st.success("Records imported.")
                    st.rerun()
                else:
                    st.error("The CSV is missing one or more required columns.")
            except Exception as exc:
                st.error(f"Could not import the CSV: {exc}")


# -----------------------------
# Settings
# -----------------------------
else:
    st.subheader("Settings")
    st.caption("Personalize the workspace and verify your deployment configuration.")

    c1, c2 = st.columns(2)
    business_name = c1.text_input("Business name", value="Your Company")
    default_currency = c2.text_input("Default currency", value="USD", max_chars=5)

    signature = st.text_area(
        "Default signature",
        value="[Your Name]\n[Company Name]",
        height=120,
    )

    st.divider()
    st.subheader("Gemini configuration")
    st.write(
        "For Streamlit Cloud, add your API key under **Settings → Secrets**. "
        "Do not commit the key to GitHub."
    )

    key_present = bool(get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY"))
    model_name = get_secret("GEMINI_MODEL") or "gemini-2.5-flash"

    if key_present:
        st.success(f"API secret detected. Model: {model_name}")
    else:
        st.warning("No Gemini API secret detected. The app will still work using professional built-in templates.")

    st.info(
        "Privacy note: this app does not store client data in a database. "
        "Records entered here remain in the current Streamlit session unless you export them."
    )

    if st.button("Clear session data", type="secondary"):
        for key in ["invoices", "generated", "generated_subject", "last_client_reply", "sequence"]:
            st.session_state.pop(key, None)
        st.rerun()


# -----------------------------
# Footer
# -----------------------------
st.markdown(
    '<div class="footer">Aurora Follow-Up • Professional client communication workspace</div>',
    unsafe_allow_html=True,
)
