import requests
import smtplib
import pytz
import os
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Credentials ───────────────────────────────────────────
GMAIL_ADDRESS  = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]
CLIST_USERNAME = os.environ["CLIST_USERNAME"]
CLIST_API_KEY  = os.environ["CLIST_API_KEY"]

# ── Platforms ─────────────────────────────────────────────
ALLOWED_PLATFORMS = {
    'codeforces.com' : 'Codeforces',
    'codechef.com'   : 'CodeChef',
    'leetcode.com'   : 'LeetCode'
}

IST = pytz.timezone('Asia/Kolkata')

# ── Send Email ────────────────────────────────────────────
def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From']    = GMAIL_ADDRESS
    msg['To']      = NOTIFY_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.sendmail(GMAIL_ADDRESS, NOTIFY_EMAIL, msg.as_string())

    print(f"Email sent: {subject}")

# ── Fetch Contests from clist.by ──────────────────────────
def fetch_contests():
    now = datetime.now(timezone.utc)
    start_from = now.strftime('%Y-%m-%dT%H:%M:%S')
    start_to   = (now + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')

    url    = "https://clist.by/api/v4/contest/"
    params = {
        "username"   : CLIST_USERNAME,
        "api_key"    : CLIST_API_KEY,
        "start__gte" : start_from,
        "start__lte" : start_to,
        "order_by"   : "start",
        "limit"      : 100,
        "format"     : "json"
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json().get("objects", [])

# ── Parse Contest Start Time Safely ──────────────────────
def parse_start(raw):
    raw = raw.replace('Z', '+00:00')
    if '+' not in raw and 'T' in raw:
        raw += '+00:00'
    return datetime.fromisoformat(raw)

# ── Build Email Body ──────────────────────────────────────
def build_body(alert_type, platform, contest_name, ist_time, diff_minutes, link):
    if alert_type == "morning":
        header  = "CONTEST TODAY - Mark Your Calendar"
        message = "You have a contest scheduled today. Prepare early!"
    elif alert_type == "one_hour":
        header  = "CONTEST ALERT - Starting in 1 Hour"
        message = "Get ready! Contest starts in about 1 hour."
    else:
        header  = "CONTEST ALERT - Starting RIGHT NOW"
        message = "The contest has started! Open the link and begin."

    body = (
        "============================================\n"
        f"  {header}\n"
        "============================================\n"
        "\n"
        f"Platform   :  {platform}\n"
        f"Contest    :  {contest_name}\n"
        f"Start Time :  {ist_time} IST\n"
        f"In About   :  {int(diff_minutes)} minutes\n"
        f"Link       :  {link}\n"
        "\n"
        f"  {message}\n"
        "\n"
        "============================================\n"
        "  Good luck! Get ready to code!\n"
        "============================================"
    )
    return body

# ── Main Function ─────────────────────────────────────────
def check_contests():
    now_utc = datetime.now(timezone.utc)
    now_ist = datetime.now(IST)

    print(f"Running at: {now_ist.strftime('%I:%M %p IST | %d %b %Y')}")
    print("Fetching contests from clist.by...")

    try:
        contests = fetch_contests()
        print(f"API OK. Contests found: {len(contests)}")
    except requests.exceptions.Timeout:
        print("Error: API request timed out.")
        return
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to clist.by")
        return
    except Exception as e:
        print(f"Error: {e}")
        return

    # Check if current IST time is in the morning alert window (6:00 AM to 6:30 AM)
    ist_hour   = now_ist.hour
    ist_minute = now_ist.minute
    is_morning_window = (ist_hour == 6 and 0 <= ist_minute <= 30)

    total_sent = 0

    for contest in contests:

        # Filter: only our 3 platforms
        resource = (contest.get('resource') or '').lower().strip()
        matched  = next(
            (r for r in ALLOWED_PLATFORMS if r in resource), None
        )
        if not matched:
            continue

        # Parse start time
        try:
            start_time = parse_start(contest.get('start', ''))
        except Exception as e:
            print(f"Could not parse time for {contest.get('event')}: {e}")
            continue

        platform     = ALLOWED_PLATFORMS[matched]
        contest_name = contest.get('event', 'Unknown Contest')
        link         = contest.get('href', 'No link available')
        ist_time     = start_time.astimezone(IST).strftime('%I:%M %p  |  %d %b %Y')
        diff_minutes = (start_time - now_utc).total_seconds() / 60

        print(f"Checking: {contest_name} | {platform} | in {int(diff_minutes)} min")

        # ── ALERT 1: Morning Alert ────────────────────────
        # Fires once between 6:00 AM and 6:30 AM IST
        # if contest is happening today
        contest_ist_date = start_time.astimezone(IST).date()
        today_ist        = now_ist.date()
        is_today         = (contest_ist_date == today_ist)

        if is_morning_window and is_today:
            subject = f"[Morning Alert] {platform} Contest Today!"
            body    = build_body(
                "morning", platform, contest_name,
                ist_time, diff_minutes, link
            )
            try:
                send_email(subject, body)
                total_sent += 1
                print(f"Morning alert sent for: {contest_name}")
            except Exception as e:
                print(f"Email failed: {e}")

        # ── ALERT 2: One Hour Before ──────────────────────
        # Fires when contest is between 45 and 75 minutes away
        elif 45 <= diff_minutes <= 75:
            subject = f"[1 Hour Alert] {platform} Contest Starting Soon!"
            body    = build_body(
                "one_hour", platform, contest_name,
                ist_time, diff_minutes, link
            )
            try:
                send_email(subject, body)
                total_sent += 1
                print(f"One-hour alert sent for: {contest_name}")
            except Exception as e:
                print(f"Email failed: {e}")

        # ── ALERT 3: Contest Starting Now ────────────────
        # Fires when contest is between -5 and 25 minutes
        # (covers the 30-minute run window perfectly)
        elif -5 <= diff_minutes <= 25:
            subject = f"[Starting NOW] {platform} Contest Has Begun!"
            body    = build_body(
                "now", platform, contest_name,
                ist_time, diff_minutes, link
            )
            try:
                send_email(subject, body)
                total_sent += 1
                print(f"Start alert sent for: {contest_name}")
            except Exception as e:
                print(f"Email failed: {e}")

    # Final summary
    if total_sent == 0:
        print("No alerts triggered this run.")
    else:
        print(f"Done. {total_sent} alert(s) sent this run.")


# ── Entry Point ───────────────────────────────────────────
if __name__ == "__main__":
    check_contests()