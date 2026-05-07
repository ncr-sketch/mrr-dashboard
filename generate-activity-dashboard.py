#!/usr/bin/env python3
"""
Clerk.io Daily Activity Tracker
================================
Fetches daily sales activities (calls, emails) from Close CRM and generates
a self-contained HTML dashboard with live activity ticker and leaderboard.

Usage:
  python3 generate-activity-dashboard.py --once     # Fetch once, generate HTML, exit
  python3 generate-activity-dashboard.py            # Loop every 5 minutes

The generated HTML file auto-refreshes in the browser every 5 minutes.
Photos: place rep headshots in a 'photos/' folder next to this script.
"""

import json
import base64
import urllib.request
import urllib.error
import urllib.parse
import sys
import os
import time
import random
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Copenhagen timezone for accurate "today" calculation
CPH_TZ = ZoneInfo("Europe/Copenhagen")

# ── Configuration ─────────────────────────────────────────────────────────────
CLOSE_API_BASE = "https://api.close.com/api/v1"
CLOSE_API_KEY = os.environ.get("CLOSE_API_KEY", "")

REPS = {
    'user_yBw9tNt4WNDf34dsPFG48SpvefoK7A8zPMjfU4K4DYM': {'name': 'Robert Bengtsson', 'initials': 'RB', 'email': 'rob@clerk.io'},
    'user_7bbV5f2geHD1hLDw54p9Vr088T3yW6TSBLUs8JAMEzV': {'name': 'Peter Rossé', 'initials': 'PR', 'email': 'ptr@clerk.io'},
    'user_O0GV7AdCKCB5bOrK89NeJYyNoPYpcLjJCCUHinDgoLR': {'name': 'Anders Hildan', 'initials': 'AH', 'email': 'anh@clerk.io'},
    'user_guKLcbLohZnYhgae5FGvEK6f9ay5fTsAvOnfq6pq3gn': {'name': 'Braxton Phillips', 'initials': 'BP', 'email': 'brp@clerk.io'},
    'user_5Mkg13Ge14LxiplY5t8phIud1vfqxkVe6su6RF4IJRh': {'name': 'Arnab Deb', 'initials': 'AD', 'email': 'ade@clerk.io'},
    'user_YJuiXnlZrSDAeBGXHL7ehssMRWzxlH86jtXr7NExbss': {'name': 'Alexander Alken', 'initials': 'AA', 'email': 'aal@clerk.io'},
    'user_rgafRJqGdOmQVhsZx3fh8PcL12ASTMFm9asWvHpfDs2': {'name': 'Alexandra Beikerts', 'initials': 'AB', 'email': 'alb@clerk.io'},
    'user_SAZq4wEnfq5ILVTsn0ftwUOk2B3buDEoboxWigYg0ku': {'name': 'Daniela Drobna', 'initials': 'DD', 'email': 'ddr@clerk.io'},
    'user_sVcAJW2NzbU6ZlfVrX4zqUp78rbJXQEyGq7tmFugyHY': {'name': 'Christian Antoniu', 'initials': 'CA', 'email': 'chn@clerk.io'},
    'user_nwSw0RV3curn6amDVD8qbiYkB02K3D7a2PN7CBZlZPa': {'name': 'Alessio Catania', 'initials': 'AC', 'email': 'alc@clerk.io'},
    'user_5pIrGaTwAhuFiCpleT0rdfI86E2HoOra853wfUuJmRx': {'name': 'Maja Krokowska', 'initials': 'MK', 'email': 'maj@clerk.io'},
}

TARGETS = {
    'calls':    {'green': 50, 'orange': 25},   # <25 red, 25-49 orange, 50+ green
    'duration': {'green': 30, 'orange': 20},  # <20min red, 20-29min orange, 30+ green (in minutes)
    'emails':   {'green': 25, 'orange': 10},  # <10 red, 10-24 orange, 25+ green
}

SCRIPT_DIR = Path(__file__).parent
# Try both 'photos' and 'Photos' (Linux is case-sensitive)
PHOTOS_DIR = SCRIPT_DIR / "photos"
if not PHOTOS_DIR.exists():
    PHOTOS_DIR = SCRIPT_DIR / "Photos"
# ──────────────────────────────────────────────────────────────────────────────


def close_api_request(endpoint, params=None):
    """Make a request to Close API with basic auth."""
    url = f"{CLOSE_API_BASE}{endpoint}"
    if params:
        param_str = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{param_str}"

    request = urllib.request.Request(url)
    credentials = f"{CLOSE_API_KEY}:"
    encoded = base64.b64encode(credentials.encode()).decode()
    request.add_header("Authorization", f"Basic {encoded}")
    request.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        raise
    except Exception as e:
        print(f"Request failed: {e}")
        raise


def get_photo_data_uri(rep_name):
    """
    Look for a photo in photos/ folder and return base64 data URI.
    Tries: firstname.{ext}, full-name.{ext}
    Returns None if no photo found.
    """
    if not PHOTOS_DIR.exists():
        return None

    first_name = rep_name.split()[0].lower()
    full_name_hyphen = rep_name.lower().replace(' ', '-')
    full_name_space = rep_name  # Original casing with spaces
    full_name_lower_space = rep_name.lower()  # lowercase with spaces
    # Handle accented characters
    full_name_clean = full_name_hyphen.replace('é', 'e').replace('ö', 'o').replace('ä', 'a').replace('ø', 'o').replace('å', 'a')
    first_name_clean = first_name.replace('é', 'e').replace('ö', 'o').replace('ä', 'a').replace('ø', 'o').replace('å', 'a')

    names_to_try = list(dict.fromkeys([
        full_name_space,          # "Robert Bengtsson"
        full_name_lower_space,    # "robert bengtsson"
        first_name,               # "robert"
        first_name_clean,         # "robert" (without accents)
        full_name_hyphen,         # "robert-bengtsson"
        full_name_clean,          # "robert-bengtsson" (without accents)
    ]))

    for name in names_to_try:
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            photo_path = PHOTOS_DIR / f"{name}.{ext}"
            if photo_path.exists():
                try:
                    with open(photo_path, 'rb') as f:
                        photo_data = f.read()
                    mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
                    encoded = base64.b64encode(photo_data).decode()
                    return f"data:{mime};base64,{encoded}"
                except Exception as e:
                    print(f"Error reading photo {photo_path}: {e}")
    return None


def fetch_todays_calls():
    """Fetch all call activities from today (Copenhagen time) for configured reps."""
    now_cph = datetime.now(CPH_TZ)
    today_cph = now_cph.date()
    # Convert Copenhagen midnight boundaries to UTC for the API
    start_cph = datetime(today_cph.year, today_cph.month, today_cph.day, tzinfo=CPH_TZ)
    end_cph = start_cph + timedelta(days=1)
    date_gte = start_cph.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    date_lt = end_cph.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

    all_calls = []
    skip = 0
    limit = 100

    while True:
        params = {
            'date_created__gte': date_gte,
            'date_created__lt': date_lt,
            '_limit': limit,
            '_skip': skip,
        }
        try:
            response = close_api_request('/activity/call/', params)
            data = response.get('data', [])
            all_calls.extend(data)

            if not response.get('has_more', False):
                break
            skip += limit
        except Exception as e:
            print(f"Error fetching calls: {e}")
            break

    return all_calls


def fetch_todays_emails():
    """Fetch all email activities from today (Copenhagen time) for configured reps."""
    now_cph = datetime.now(CPH_TZ)
    today_cph = now_cph.date()
    # Convert Copenhagen midnight boundaries to UTC for the API
    start_cph = datetime(today_cph.year, today_cph.month, today_cph.day, tzinfo=CPH_TZ)
    end_cph = start_cph + timedelta(days=1)
    date_gte = start_cph.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    date_lt = end_cph.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

    all_emails = []
    skip = 0
    limit = 100

    while True:
        params = {
            'date_created__gte': date_gte,
            'date_created__lt': date_lt,
            '_limit': limit,
            '_skip': skip,
        }
        try:
            response = close_api_request('/activity/email/', params)
            data = response.get('data', [])
            all_emails.extend(data)

            if not response.get('has_more', False):
                break
            skip += limit
        except Exception as e:
            print(f"Error fetching emails: {e}")
            break

    return all_emails


def fetch_lead_names(lead_ids):
    """Batch fetch lead names from a list of lead IDs."""
    lead_names = {}
    for lead_id in lead_ids:
        try:
            response = close_api_request(f'/lead/{lead_id}/')
            if response.get('name'):
                lead_names[lead_id] = response['name']
        except Exception as e:
            print(f"Error fetching lead {lead_id}: {e}")
    return lead_names


def aggregate_activities(calls, emails):
    """Aggregate today's activities by rep. Returns dict of rep stats."""
    stats = {}
    for uid in REPS:
        stats[uid] = {
            'calls': 0,
            'duration_seconds': 0,
            'emails': 0,
        }

    # Count calls and durations (only outbound)
    for call in calls:
        user_id = call.get('user_id')
        if user_id not in REPS:
            continue
        # Only count outbound calls
        if call.get('direction') != 'outbound':
            continue
        stats[user_id]['calls'] += 1
        duration = call.get('duration', 0) or 0
        stats[user_id]['duration_seconds'] += duration

    # Count emails (only outgoing)
    for email in emails:
        user_id = email.get('user_id')
        if user_id not in REPS:
            continue
        # Only count outgoing emails
        if email.get('direction') != 'outgoing':
            continue
        stats[user_id]['emails'] += 1

    return stats


def get_status(value, metric):
    """Get status (red/orange/green) for a value given a metric."""
    thresholds = TARGETS[metric]
    if value >= thresholds['green']:
        return 'green'
    elif value >= thresholds['orange']:
        return 'orange'
    else:
        return 'red'


def build_ticker_items(calls, emails, rep_stats):
    """Build live activity ticker items from recent calls and milestone celebrations."""
    ticker_items = []

    # Get recent calls >3 minutes, sorted by date_created descending
    recent_calls = [
        c for c in calls
        if c.get('user_id') in REPS and c.get('duration', 0) and c.get('duration') > 180
    ]
    recent_calls.sort(key=lambda x: x.get('date_created', ''), reverse=True)
    recent_calls = recent_calls[:10]  # Limit to 10 for ticker

    # Fetch lead names for these calls
    lead_ids = [c.get('lead_id') for c in recent_calls if c.get('lead_id')]
    lead_names = fetch_lead_names(lead_ids)

    # Build call ticker items
    for call in recent_calls:
        user_id = call.get('user_id')
        duration_sec = call.get('duration', 0) or 0
        duration_min = duration_sec // 60
        rep_name = REPS[user_id]['name']
        lead_id = call.get('lead_id')
        lead_name = lead_names.get(lead_id, 'a client')
        ticker_items.append({
            'type': 'call',
            'rep': rep_name,
            'duration': duration_min,
            'lead': lead_name,
        })

    # Get recent sent emails, sorted by date_created descending
    recent_emails = [
        e for e in emails
        if e.get('user_id') in REPS and e.get('direction', '') == 'outgoing'
    ]
    recent_emails.sort(key=lambda x: x.get('date_created', ''), reverse=True)
    recent_emails = recent_emails[:10]  # Limit to 10 for ticker

    # Fetch lead names for emails (reuse any already fetched)
    email_lead_ids = [e.get('lead_id') for e in recent_emails if e.get('lead_id') and e.get('lead_id') not in lead_names]
    if email_lead_ids:
        email_lead_names = fetch_lead_names(email_lead_ids)
        lead_names.update(email_lead_names)

    # Build email ticker items
    for email in recent_emails:
        user_id = email.get('user_id')
        rep_name = REPS[user_id]['name']
        lead_id = email.get('lead_id')
        lead_name = lead_names.get(lead_id, 'a client')
        ticker_items.append({
            'type': 'email',
            'rep': rep_name,
            'lead': lead_name,
        })

    # Interleave calls and emails by mixing them
    random.shuffle(ticker_items)

    # Build milestone ticker items (add after shuffle so milestones are sprinkled in)
    milestone_items = []
    for user_id, stats in rep_stats.items():
        rep_name = REPS[user_id]['name']
        duration_min = stats['duration_seconds'] // 60

        # Check each metric for milestone
        if stats['calls'] >= TARGETS['calls']['green']:
            milestone_items.append({
                'type': 'milestone',
                'rep': rep_name,
                'metric': 'calls',
                'target': TARGETS['calls']['green'],
            })
        if duration_min >= TARGETS['duration']['green']:
            milestone_items.append({
                'type': 'milestone',
                'rep': rep_name,
                'metric': 'duration',
                'target': TARGETS['duration']['green'],
            })
        if stats['emails'] >= TARGETS['emails']['green']:
            milestone_items.append({
                'type': 'milestone',
                'rep': rep_name,
                'metric': 'emails',
                'target': TARGETS['emails']['green'],
            })

    # Sprinkle milestones evenly into the shuffled activity items
    combined = []
    if ticker_items and milestone_items:
        step = max(1, len(ticker_items) // (len(milestone_items) + 1))
        mi = 0
        for i, item in enumerate(ticker_items):
            combined.append(item)
            if mi < len(milestone_items) and (i + 1) % step == 0:
                combined.append(milestone_items[mi])
                mi += 1
        combined.extend(milestone_items[mi:])
    else:
        combined = ticker_items + milestone_items

    return combined


def get_countdown(value, metric):
    """Get countdown number to next threshold."""
    thresholds = TARGETS[metric]
    green = thresholds['green']
    if value >= green:
        return 0  # Already achieved
    return green - value


def generate_html(rep_stats, ticker_items, rep_photos_json):
    """Generate the complete dashboard HTML with all CSS and data."""
    now_cph = datetime.now(CPH_TZ)
    today = now_cph.date()
    now = now_cph
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    date_display = f"{month_names[today.month - 1]} {today.day}, {today.year}"

    # ── Build ticker HTML ──
    ticker_html_items = ''
    for item in ticker_items:
        if item['type'] == 'call':
            ticker_html_items += f'''        <div class="ticker-item">
            <span class="ticker-icon">📞</span>
            <span class="ticker-name">{item['rep']}</span> just finished a
            <span class="ticker-highlight">{item['duration']}m call</span> with {item['lead']}
            <span class="ticker-sep"></span>
        </div>
'''
        elif item['type'] == 'email':
            ticker_html_items += f'''        <div class="ticker-item">
            <span class="ticker-icon">&#9993;</span>
            <span class="ticker-name">{item['rep']}</span> sent an email to {item['lead']}
            <span class="ticker-sep"></span>
        </div>
'''
        elif item['type'] == 'milestone':
            metric = item['metric']
            target = item['target']
            metric_label = 'calls' if metric == 'calls' else ('min call time' if metric == 'duration' else 'emails')
            ticker_html_items += f'''        <div class="ticker-item">
            <span class="ticker-icon">🟢</span>
            <span class="ticker-name">{item['rep']}</span> hit
            <span class="ticker-highlight green">{target} {metric_label}!</span>
            <span class="ticker-sep"></span>
        </div>
'''

    # Duplicate items for seamless loop
    ticker_html = f'''<div class="activity-ticker">
    <div class="ticker-label"><span class="live-dot"></span> Live</div>
    <div class="ticker-track">
{ticker_html_items}{ticker_html_items}    </div>
</div>
'''

    # ── Build leaderboard rows ──
    rep_data = []
    for uid, rep in REPS.items():
        stats = rep_stats[uid]
        duration_min = stats['duration_seconds'] // 60
        rep_data.append({
            'uid': uid,
            'name': rep['name'],
            'initials': rep['initials'],
            'calls': stats['calls'],
            'duration': duration_min,
            'emails': stats['emails'],
        })

    # Sort by calls (default)
    rep_data.sort(key=lambda x: x['calls'], reverse=True)

    leaderboard_rows = []
    for rank, rep in enumerate(rep_data, 1):
        calls_status = get_status(rep['calls'], 'calls')
        duration_status = get_status(rep['duration'], 'duration')
        emails_status = get_status(rep['emails'], 'emails')

        # Check if all green
        all_green = (calls_status == 'green' and duration_status == 'green' and emails_status == 'green')

        # Classes — default view is calls, so target-hit if calls target met
        calls_hit = calls_status == 'green'
        classes = ['lb-row']
        if calls_hit:
            classes.append('target-hit')
        if all_green:
            classes.append('all-green')
        if rank <= 3:
            classes.append('top-3')
        if rank > 5:
            classes.append('compact')

        # Photo or initials
        photo_uri = get_photo_data_uri(rep['name'])
        if photo_uri:
            photo_inner = f'<img src="{photo_uri}" alt="{rep["name"]}">'
        else:
            photo_inner = f'<span class="lb-photo-initials">{rep["initials"]}</span>'

        # Crown for target hit on current metric (calls default)
        crown_html = ''
        if calls_hit:
            crown_html = '<span class="crown-emoji">👑</span>'

        # Rank badge
        badge_class = 'rank-badge'
        if rank == 1:
            badge_class += ' gold'
        elif rank == 2:
            badge_class += ' silver'
        elif rank == 3:
            badge_class += ' bronze'

        # Progress bar (based on calls for default view) with shimmer tiers
        calls_pct = (rep['calls'] / TARGETS['calls']['green'] * 100) if TARGETS['calls']['green'] > 0 else 0
        calls_pct = min(calls_pct, 100)
        if calls_pct >= 100:
            bar_shimmer = ' shimmer-green'
        elif calls_pct >= 75:
            bar_shimmer = ' shimmer-75'
        elif calls_pct >= 50:
            bar_shimmer = ' shimmer-50'
        else:
            bar_shimmer = ''

        # Countdown values
        calls_countdown = get_countdown(rep['calls'], 'calls')
        duration_countdown = get_countdown(rep['duration'], 'duration')
        emails_countdown = get_countdown(rep['emails'], 'emails')

        # Display checkmark if achieved, countdown otherwise
        calls_display = '✓' if calls_countdown == 0 else str(calls_countdown)
        duration_display = '✓' if duration_countdown == 0 else str(duration_countdown)
        emails_display = '✓' if emails_countdown == 0 else str(emails_countdown)

        # Labels change when target is achieved
        calls_label = 'Calls' if calls_countdown == 0 else 'Calls to go'
        duration_label = 'Duration' if duration_countdown == 0 else 'Min to go'
        emails_label = 'Emails' if emails_countdown == 0 else 'Emails to go'

        row = f'''            <div class="{' '.join(classes)}" style="animation-delay: {rank * 0.05}s">
                <div class="photo-rank-wrap">
                    {crown_html}
                    <div class="lb-photo">{photo_inner}</div>
                    <div class="{badge_class}">{rank}</div>
                </div>
                <div class="lb-info">
                    <div class="lb-name">{rep['name']}</div>
                    <div class="activity-bar-track"><div class="activity-bar-fill status-{calls_status}{bar_shimmer}" style="width:{calls_pct:.0f}%"></div></div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num {calls_status}">{calls_display}</div>
                    <div class="metric-label">{calls_label}</div>
                    <div class="metric-actual">{rep['calls']} made</div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num {duration_status}">{duration_display}</div>
                    <div class="metric-label">{duration_label}</div>
                    <div class="metric-actual">{rep['duration']}m total</div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num {emails_status}">{emails_display}</div>
                    <div class="metric-label">{emails_label}</div>
                    <div class="metric-actual">{rep['emails']} sent</div>
                </div>
            </div>
'''
        leaderboard_rows.append(row)

    leaderboard_html = '\n'.join(leaderboard_rows)

    # ── Compute team totals for tab display ──
    total_calls = sum(r['calls'] for r in rep_data)
    total_duration = sum(r['duration'] for r in rep_data)
    total_emails = sum(r['emails'] for r in rep_data)
    # Format duration as Xh Ym
    dur_hours = total_duration // 60
    dur_mins = total_duration % 60
    total_duration_display = f"{dur_hours}h {dur_mins}m" if dur_hours > 0 else f"{dur_mins}m"

    # ── Pre-compute JSON variables for f-string ──
    rep_data_json = json.dumps(rep_data)
    targets_json = json.dumps(TARGETS)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>Clerk.io — Daily Activity Tracker</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --clerk-orange: #FF5C28;
            --clerk-orange-light: #FF7A52;
            --clerk-orange-bg: rgba(255, 92, 40, 0.08);
            --green: #1DB954;
            --green-dark: #169c46;
            --green-bg: rgba(29, 185, 84, 0.10);
            --yellow: #E5A100;
            --yellow-dark: #cc8f00;
            --yellow-bg: rgba(229, 161, 0, 0.10);
            --red: #E04040;
            --red-dark: #c73636;
            --red-bg: rgba(224, 64, 64, 0.10);
            --bg: #ffffff;
            --surface: #F7F7F8;
            --surface-raised: #ffffff;
            --text-primary: #1a1a1a;
            --text-secondary: #666666;
            --text-tertiary: #999999;
            --border: #EBEBEB;
            --border-orange: rgba(255, 92, 40, 0.25);
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.10);
            --radius-sm: 12px;
            --radius-md: 16px;
            --radius-lg: 20px;
            --radius-xl: 24px;
        }}

        body.dark-mode {{
            --bg: #121218;
            --surface: #1a1a24;
            --surface-raised: #22222e;
            --text-primary: #f0f0f5;
            --text-secondary: #a0a0b0;
            --text-tertiary: #6a6a7a;
            --border: #2a2a38;
            --border-orange: rgba(255, 92, 40, 0.35);
            --clerk-orange-bg: rgba(255, 92, 40, 0.12);
            --green-bg: rgba(29, 185, 84, 0.15);
            --yellow-bg: rgba(229, 161, 0, 0.15);
            --red-bg: rgba(224, 64, 64, 0.15);
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.2);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.3);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.4);
        }}

        body.dark-mode .activity-bar-track {{
            background: linear-gradient(180deg, #111122 0%, #1e1e35 50%, #111122 100%);
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.05);
            border: 1px solid rgba(0,0,0,0.4);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        /* ═══════════════════════════════════════════
           LAYOUT — portrait dashboard at 1080px wide.
           Add ?tv=cw or ?tv=ccw to the URL to enable
           rotation for vertically-mounted TVs.
           ═══════════════════════════════════════════ */
        .tv-rotate-wrapper {{
            width: 1080px;
            margin: 0 auto;
            padding: 24px 32px 32px;
            background: var(--bg);
            min-height: 100vh;
        }}

        body {{
            font-family: 'Poppins', sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            margin: 0;
        }}

        /* ═══════════════════════════════════════════
           LIVE ACTIVITY TICKER
           ═══════════════════════════════════════════ */
        @keyframes tickerPulse {{
            0%, 100% {{ box-shadow: 0 0 12px rgba(29, 185, 84, 0.15), var(--shadow-sm); }}
            50% {{ box-shadow: 0 0 22px rgba(29, 185, 84, 0.3), 0 0 6px rgba(29, 185, 84, 0.1), var(--shadow-sm); }}
        }}
        @keyframes dotPulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(0.8); }}
        }}
        .activity-ticker {{
            display: flex;
            align-items: center;
            background: linear-gradient(135deg, var(--green-bg), var(--surface));
            border-radius: var(--radius-md);
            border: 2px solid var(--green);
            animation: tickerPulse 3s ease-in-out infinite;
            overflow: hidden;
            margin-bottom: 24px;
            height: 52px;
        }}
        .ticker-label {{
            background: var(--green);
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
            padding: 0 20px;
            height: 100%;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
            flex-shrink: 0;
            text-transform: uppercase;
            position: relative;
            z-index: 2;
            box-shadow: 4px 0 8px rgba(0,0,0,0.2);
        }}
        .live-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #fff;
            animation: dotPulse 1.5s ease-in-out infinite;
            flex-shrink: 0;
        }}
        .ticker-track {{
            display: flex;
            animation: tickerScroll 80s linear infinite;
            white-space: nowrap;
        }}
        @keyframes tickerScroll {{
            0% {{ transform: translateX(0); }}
            100% {{ transform: translateX(-50%); }}
        }}
        .ticker-item {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 0 24px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            flex-shrink: 0;
        }}
        .ticker-icon {{
            font-size: 16px;
        }}
        .ticker-name {{
            font-weight: 700;
            color: var(--text-primary);
        }}
        .ticker-highlight {{
            font-weight: 700;
            color: var(--clerk-orange);
        }}
        .ticker-highlight.green {{
            color: var(--green);
        }}
        .ticker-sep {{
            display: inline-block;
            width: 4px; height: 4px;
            border-radius: 50%;
            background: var(--text-tertiary);
            margin-left: 12px;
        }}

        /* ═══════════════════════════════════════════
           METRIC TABS
           ═══════════════════════════════════════════ */
        .metric-tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            background: var(--surface);
            padding: 6px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border);
        }}
        .metric-tab {{
            flex: 1;
            padding: 10px 20px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-weight: 600;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            color: var(--text-secondary);
            background: transparent;
            border: none;
            font-family: inherit;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
        }}
        .metric-tab:hover {{
            color: var(--text-primary);
            background: var(--surface-raised);
        }}
        .tab-metric-name {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .tab-total {{
            font-size: 20px;
            font-weight: 800;
            color: var(--text-tertiary);
            position: relative;
            z-index: 1;
        }}
        .metric-tab.active .tab-total {{
            color: var(--green);
        }}
        @keyframes shimmerSweep {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
        .metric-tab.active {{
            background: var(--surface-raised);
            color: var(--green);
            border: 1.5px solid rgba(29, 185, 84, 0.5);
            box-shadow: 0 0 14px rgba(29, 185, 84, 0.2), var(--shadow-sm);
            position: relative;
            overflow: hidden;
        }}
        .metric-tab.active::after {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(
                90deg,
                transparent 0%,
                rgba(29, 185, 84, 0.12) 45%,
                rgba(29, 185, 84, 0.25) 50%,
                rgba(29, 185, 84, 0.12) 55%,
                transparent 100%
            );
            background-size: 200% 100%;
            animation: shimmerSweep 2.5s ease-in-out infinite;
            border-radius: var(--radius-sm);
            pointer-events: none;
        }}
        .metric-tab .tab-icon {{ margin-right: 0; }}

        /* ═══════════════════════════════════════════
           LEADERBOARD
           ═══════════════════════════════════════════ */
        .leaderboard-section {{
            background: var(--surface);
            border-radius: var(--radius-lg);
            padding: 24px;
            border: 1px solid var(--border);
        }}
        .leaderboard-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .leaderboard-title {{
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .leaderboard-subtitle {{
            font-size: 13px;
            color: var(--text-tertiary);
        }}
        .leaderboard-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        /* ═══════════════════════════════════════════
           LEADERBOARD ROW
           ═══════════════════════════════════════════ */
        .lb-row {{
            display: grid;
            grid-template-columns: 68px 1fr 100px 100px 100px;
            gap: 16px;
            align-items: center;
            background: var(--surface-raised);
            padding: 14px 20px;
            border-radius: var(--radius-md);
            border-left: 4px solid var(--clerk-orange);
            box-shadow: var(--shadow-sm);
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
            animation: slideIn 0.4s ease backwards;
        }}
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateY(12px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .lb-row:hover {{
            box-shadow: var(--shadow-md);
            transform: translateX(4px);
        }}
        .lb-row.top-3 {{
            padding: 18px 24px;
            background: var(--clerk-orange-bg);
            border-left-width: 5px;
        }}
        .lb-row.top-3 .lb-name {{ font-size: 17px; }}
        .lb-row.top-3 .lb-photo {{ width: 58px; height: 58px; border-color: var(--clerk-orange); }}
        .lb-row.top-3 .countdown-num {{ font-size: 24px; }}
        .lb-row.compact {{
            padding: 10px 20px;
            gap: 12px;
        }}
        .lb-row.compact .lb-name {{ font-size: 14px; }}
        .lb-row.compact .lb-photo {{ width: 40px; height: 40px; }}
        .lb-row.compact .rank-badge {{ width: 20px; height: 20px; font-size: 10px; }}
        .lb-row.compact .countdown-num {{ font-size: 18px; }}
        .lb-row.compact .activity-bar-track {{ height: 16px; }}

        /* ═══════════════════════════════════════════
           BAR SHIMMER TIERS
           ═══════════════════════════════════════════ */
        @keyframes barShimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}

        /* 50%+ — gentle white sweep */
        .activity-bar-fill.shimmer-50::after {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%);
            background-size: 200% 100%;
            animation: barShimmer 3s ease-in-out infinite;
            border-radius: 3px;
            pointer-events: none;
        }}

        /* 75%+ — brighter, faster */
        .activity-bar-fill.shimmer-75::after {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 50%, transparent 100%);
            background-size: 200% 100%;
            animation: barShimmer 2.5s ease-in-out infinite;
            border-radius: 3px;
            pointer-events: none;
        }}

        /* 100%+ — bold shimmer */
        .activity-bar-fill.shimmer-green::after {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.45) 50%, transparent 100%);
            background-size: 200% 100%;
            animation: barShimmer 2s ease-in-out infinite;
            border-radius: 3px;
            pointer-events: none;
        }}

        /* ═══════════════════════════════════════════
           TARGET HIT ROW — pulse + row shimmer sweep
           Crown, confetti, pulsing glow, green sweep
           ═══════════════════════════════════════════ */
        @keyframes greenPulse {{
            0%, 100% {{ box-shadow: 0 0 16px rgba(29, 185, 84, 0.25), var(--shadow-sm); }}
            50% {{ box-shadow: 0 0 28px rgba(29, 185, 84, 0.4), 0 0 8px rgba(29, 185, 84, 0.15), var(--shadow-sm); }}
        }}
        @keyframes rowShimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}

        .lb-row.target-hit {{
            border-left-color: var(--green);
            background: linear-gradient(135deg, var(--green-bg) 0%, var(--surface-raised) 50%);
            animation: greenPulse 3s ease-in-out infinite;
        }}
        .lb-row.target-hit::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(
                90deg,
                transparent 0%,
                rgba(29, 185, 84, 0.08) 40%,
                rgba(29, 185, 84, 0.18) 50%,
                rgba(29, 185, 84, 0.08) 60%,
                transparent 100%
            );
            background-size: 200% 100%;
            animation: rowShimmer 3s ease-in-out infinite;
            border-radius: var(--radius-md);
            pointer-events: none;
            z-index: 0;
        }}
        .lb-row.target-hit > * {{ position: relative; z-index: 1; }}

        /* Legacy class for all-green (all 3 metrics hit) — same treatment */
        .lb-row.all-green {{
            border-left-color: var(--green);
            background: linear-gradient(135deg, var(--green-bg) 0%, var(--surface-raised) 50%);
            animation: greenPulse 3s ease-in-out infinite;
        }}
        .lb-row.all-green::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(
                90deg,
                transparent 0%,
                rgba(29, 185, 84, 0.08) 40%,
                rgba(29, 185, 84, 0.18) 50%,
                rgba(29, 185, 84, 0.08) 60%,
                transparent 100%
            );
            background-size: 200% 100%;
            animation: rowShimmer 3s ease-in-out infinite;
            border-radius: var(--radius-md);
            pointer-events: none;
            z-index: 0;
        }}
        .lb-row.all-green > * {{ position: relative; z-index: 1; }}

        /* Confetti pieces */
        .confetti-piece {{
            position: absolute;
            width: 6px; height: 6px;
            border-radius: 1px;
            opacity: 0.7;
            animation: confettiFall linear infinite;
            pointer-events: none;
        }}
        @keyframes confettiFall {{
            0% {{ transform: translateY(-10px) rotate(0deg); opacity: 0.8; }}
            100% {{ transform: translateY(100px) rotate(720deg); opacity: 0; }}
        }}

        /* ═══════════════════════════════════════════
           PHOTO + RANK BADGE (Option A)
           ═══════════════════════════════════════════ */
        .photo-rank-wrap {{
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .lb-photo {{
            width: 52px; height: 52px;
            border-radius: 50%;
            overflow: hidden;
            background: var(--surface);
            border: 2px solid var(--border);
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }}
        .lb-photo img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .lb-photo-initials {{
            font-size: 16px; font-weight: 700;
            color: var(--text-tertiary);
            letter-spacing: -0.5px;
        }}
        .rank-badge {{
            position: absolute;
            bottom: -2px; right: -4px;
            width: 24px; height: 24px;
            border-radius: 50%;
            background: var(--clerk-orange);
            color: #fff;
            font-size: 12px; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
            border: 2px solid #fff;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            z-index: 2;
        }}
        .rank-badge.gold {{
            background: linear-gradient(145deg, #FFD700, #FFC107);
            color: #5C3D00; border-color: #FFD700;
            box-shadow: 0 1px 6px rgba(255, 215, 0, 0.5);
        }}
        .rank-badge.silver {{
            background: linear-gradient(145deg, #E8E8E8, #C0C0C0);
            color: #3a3a3a; border-color: #C0C0C0;
            box-shadow: 0 1px 6px rgba(192, 192, 192, 0.5);
        }}
        .rank-badge.bronze {{
            background: linear-gradient(145deg, #E08A4A, #CD7F32);
            color: #3D2200; border-color: #CD7F32;
            box-shadow: 0 1px 6px rgba(205, 127, 50, 0.5);
        }}

        .crown-emoji {{
            position: absolute;
            top: -12px; left: 50%;
            transform: translateX(-50%);
            font-size: 16px; z-index: 3;
            filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));
            animation: crownBob 2s ease-in-out infinite;
        }}
        @keyframes crownBob {{
            0%, 100% {{ transform: translateX(-50%) translateY(0); }}
            50% {{ transform: translateX(-50%) translateY(-3px); }}
        }}

        /* ═══════════════════════════════════════════
           NAME + BAR
           ═══════════════════════════════════════════ */
        .lb-info {{ flex: 1; min-width: 0; }}
        .lb-name {{
            font-weight: 600; font-size: 15px;
            color: var(--text-primary);
            margin-bottom: 6px;
        }}
        .activity-bar-track {{
            width: 100%; height: 22px;
            background: linear-gradient(180deg, #c8c8c8 0%, #e0e0e0 50%, #c8c8c8 100%);
            border-radius: 4px; overflow: hidden; position: relative;
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.5);
            border: 1px solid rgba(0,0,0,0.15);
        }}
        .activity-bar-fill {{
            height: 100%; border-radius: 3px;
            box-shadow: inset 0 -4px 6px rgba(0,0,0,0.4), inset 0 3px 0 rgba(255,255,255,0.55),
                        inset 0 6px 8px rgba(255,255,255,0.15), 0 2px 6px rgba(0,0,0,0.5);
            transition: width 0.6s ease;
            position: relative;
        }}
        .activity-bar-fill.status-red {{
            background: linear-gradient(90deg, #E04040 0%, #F06060 50%, #E04040 100%);
        }}
        .activity-bar-fill.status-orange {{
            background: linear-gradient(90deg, #FF5C28 0%, #FF7A52 50%, #FF5C28 100%);
        }}
        .activity-bar-fill.status-green {{
            background: linear-gradient(90deg, #5CB854 0%, #1DB954 40%, #17a34a 100%);
        }}

        /* ═══════════════════════════════════════════
           COUNTDOWN METRIC COLUMNS
           ═══════════════════════════════════════════ */
        .metric-cell {{ text-align: center; }}
        .countdown-num {{
            font-size: 22px; font-weight: 700;
            line-height: 1.2;
        }}
        .countdown-num.green {{ color: var(--green); }}
        .countdown-num.orange {{ color: var(--clerk-orange); }}
        .countdown-num.red {{ color: var(--red); }}
        .countdown-num.achieved {{ color: var(--green); }}
        .metric-label {{
            font-size: 10px; font-weight: 600;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .metric-actual {{
            font-size: 11px;
            color: var(--text-tertiary);
            margin-top: 1px;
        }}

        /* ═══════════════════════════════════════════
           FOOTER
           ═══════════════════════════════════════════ */
        .dash-footer {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 24px;
            padding: 14px 24px;
            margin-top: 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
        }}
        .footer-date {{
            font-size: 14px; font-weight: 600;
            color: var(--clerk-orange);
            background: var(--clerk-orange-bg);
            padding: 6px 16px;
            border-radius: 20px;
            border: 1px solid var(--border-orange);
        }}
        .footer-clock {{
            font-size: 18px; font-weight: 600;
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
        }}
        .footer-sep {{
            width: 4px; height: 4px;
            border-radius: 50%;
            background: var(--text-tertiary);
        }}

        /* ═══════════════════════════════════════════
           THEME TOGGLE
           ═══════════════════════════════════════════ */
        .theme-toggle {{
            position: fixed;
            bottom: 70px; right: 40px;
            width: 48px; height: 48px;
            border-radius: 50%;
            border: 2px solid var(--border);
            background: var(--surface-raised);
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            box-shadow: var(--shadow-md);
            transition: all 0.3s ease;
            z-index: 100;
        }}
        .theme-toggle:hover {{
            border-color: var(--clerk-orange);
            box-shadow: 0 0 16px rgba(255, 92, 40, 0.25);
        }}
        .theme-toggle svg {{ width: 22px; height: 22px; color: var(--text-secondary); }}
        body:not(.dark-mode) .icon-sun {{ display: none; }}
        body.dark-mode .icon-moon {{ display: none; }}
    </style>
</head>
<body>
<div class="tv-rotate-wrapper" id="tvWrapper">

{ticker_html}

<!-- ═══════════════════ METRIC TABS ═══════════════════ -->
<div class="metric-tabs">
    <button class="metric-tab active" onclick="switchTab('calls')">
        <span class="tab-metric-name"><span class="tab-icon">📞</span> Calls Made</span>
        <span class="tab-total" id="tabTotalCalls">{total_calls}</span>
    </button>
    <button class="metric-tab" onclick="switchTab('duration')">
        <span class="tab-metric-name"><span class="tab-icon">⏱️</span> Call Duration</span>
        <span class="tab-total" id="tabTotalDuration">{total_duration_display}</span>
    </button>
    <button class="metric-tab" onclick="switchTab('emails')">
        <span class="tab-metric-name"><span class="tab-icon">✉️</span> Emails Sent</span>
        <span class="tab-total" id="tabTotalEmails">{total_emails}</span>
    </button>
</div>

<!-- ═══════════════════ LEADERBOARD ═══════════════════ -->
<div class="leaderboard-section">
    <div class="leaderboard-header">
        <div>
            <div class="leaderboard-title" id="boardTitle">Calls Made Today</div>
            <div class="leaderboard-subtitle" id="boardSubtitle">🔴 &lt;25 &nbsp; 🟠 25–49 &nbsp; 🟢 50+</div>
        </div>
    </div>

    <div class="leaderboard-list" id="leaderboard-list">
{leaderboard_html}
    </div>
</div>

<!-- ═══════════════════ FOOTER ═══════════════════ -->
<div class="dash-footer">
    <div class="footer-date">{date_display}</div>
    <div class="footer-sep"></div>
    <div class="footer-clock" id="clock">00:00:00 AM</div>
</div>

<!-- ═══════════════════ THEME TOGGLE ═══════════════════ -->
<button class="theme-toggle" id="themeToggle" title="Toggle dark mode">
    <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
    <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
</button>

<script>
    // Pre-computed data embedded in page
    const repData = {rep_data_json};
    const targets = {targets_json};
    const rep_photos_json = {rep_photos_json};

    // ── Dark mode toggle ──
    const themeToggle = document.getElementById('themeToggle');
    // Default to dark mode for TV display
    const prefersLight = localStorage.getItem('clerk-activity-theme') === 'light';
    if (!prefersLight) document.body.classList.add('dark-mode');

    themeToggle.addEventListener('click', () => {{
        document.body.classList.toggle('dark-mode');
        const isDark = document.body.classList.contains('dark-mode');
        localStorage.setItem('clerk-activity-theme', isDark ? 'dark' : 'light');
    }});

    // ── Live clock ──
    function updateClock() {{
        const now = new Date();
        document.getElementById('clock').textContent = now.toLocaleTimeString('en-US', {{
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }});
    }}
    updateClock();
    setInterval(updateClock, 1000);

    // ── Tab totals ──
    function updateTabTotals() {{
        const totalCalls = repData.reduce((s, r) => s + r.calls, 0);
        const totalDuration = repData.reduce((s, r) => s + r.duration, 0);
        const totalEmails = repData.reduce((s, r) => s + r.emails, 0);
        const dH = Math.floor(totalDuration / 60);
        const dM = totalDuration % 60;
        document.getElementById('tabTotalCalls').textContent = totalCalls;
        document.getElementById('tabTotalDuration').textContent = dH > 0 ? dH + 'h ' + dM + 'm' : dM + 'm';
        document.getElementById('tabTotalEmails').textContent = totalEmails;
    }}

    // ── Tab switching ──
    const tabConfig = {{
        calls:    {{ title: 'Calls Made Today',     subtitle: '🔴 &lt;25 &nbsp; 🟠 25–49 &nbsp; 🟢 50+' }},
        duration: {{ title: 'Call Duration Today',   subtitle: '🔴 &lt;20 min &nbsp; 🟠 20–29 min &nbsp; 🟢 30+ min' }},
        emails:   {{ title: 'Emails Sent Today',     subtitle: '🔴 &lt;10 &nbsp; 🟠 10–24 &nbsp; 🟢 25+' }},
    }};

    function switchTab(metric) {{
        document.querySelectorAll('.metric-tab').forEach(t => t.classList.remove('active'));
        const tabs = document.querySelectorAll('.metric-tab');
        const tabIndex = metric === 'calls' ? 0 : (metric === 'duration' ? 1 : 2);
        tabs[tabIndex].classList.add('active');
        document.getElementById('boardTitle').textContent = tabConfig[metric].title;
        document.getElementById('boardSubtitle').innerHTML = tabConfig[metric].subtitle;

        // Re-sort and re-render leaderboard based on metric
        const metric_key = metric === 'duration' ? 'duration' : (metric === 'emails' ? 'emails' : 'calls');
        const sorted = [...repData].sort((a, b) => b[metric_key] - a[metric_key]);

        // Re-render rows with new sort order and bar colors
        const lb = document.getElementById('leaderboard-list');
        lb.innerHTML = '';
        sorted.forEach((rep, idx) => {{
            const rank = idx + 1;
            const calls_status = rep.calls >= targets.calls.green ? 'green' : (rep.calls >= targets.calls.orange ? 'orange' : 'red');
            const duration_status = rep.duration >= targets.duration.green ? 'green' : (rep.duration >= targets.duration.orange ? 'orange' : 'red');
            const emails_status = rep.emails >= targets.emails.green ? 'green' : (rep.emails >= targets.emails.orange ? 'orange' : 'red');
            const all_green = calls_status === 'green' && duration_status === 'green' && emails_status === 'green';

            // Determine bar color based on active metric
            let bar_status = calls_status;
            if (metric_key === 'duration') bar_status = duration_status;
            if (metric_key === 'emails') bar_status = emails_status;

            // Calculate bar width based on active metric
            let bar_width = 0;
            if (metric_key === 'calls') bar_width = Math.min(rep.calls / targets.calls.green * 100, 100);
            if (metric_key === 'duration') bar_width = Math.min(rep.duration / targets.duration.green * 100, 100);
            if (metric_key === 'emails') bar_width = Math.min(rep.emails / targets.emails.green * 100, 100);

            // Countdown values
            const calls_cd = rep.calls >= targets.calls.green ? 0 : targets.calls.green - rep.calls;
            const duration_cd = rep.duration >= targets.duration.green ? 0 : targets.duration.green - rep.duration;
            const emails_cd = rep.emails >= targets.emails.green ? 0 : targets.emails.green - rep.emails;

            const calls_display = calls_cd === 0 ? '✓' : calls_cd;
            const duration_display = duration_cd === 0 ? '✓' : duration_cd;
            const emails_display = emails_cd === 0 ? '✓' : emails_cd;

            // Shimmer tier based on active metric bar width
            let bar_shimmer = '';
            if (bar_width >= 100) bar_shimmer = ' shimmer-green';
            else if (bar_width >= 75) bar_shimmer = ' shimmer-75';
            else if (bar_width >= 50) bar_shimmer = ' shimmer-50';

            // Target hit for current metric?
            const metric_hit = bar_status === 'green';
            let row_class = (metric_hit ? 'target-hit ' : '') + (all_green ? 'all-green ' : '') + (rank <= 3 ? 'top-3 ' : '') + (rank > 5 ? 'compact' : '');
            const badge_class = rank === 1 ? 'gold' : (rank === 2 ? 'silver' : (rank === 3 ? 'bronze' : ''));

            // Crown if current metric target hit
            const crown = metric_hit ? '<span class="crown-emoji">👑</span>' : '';
            const photo = rep_photos_json[rep.uid] ? `<img src="${{rep_photos_json[rep.uid]}}" alt="${{rep.name}}">` : `<span class="lb-photo-initials">${{rep.initials}}</span>`;
            const badge_ext = badge_class ? ` ${{badge_class}}` : '';

            const row = document.createElement('div');
            row.className = `lb-row ${{row_class}}`;
            row.style.animationDelay = `${{rank * 0.05}}s`;
            row.innerHTML = `
                <div class="photo-rank-wrap">
                    ${{crown}}
                    <div class="lb-photo">${{photo}}</div>
                    <div class="rank-badge${{badge_ext}}">${{rank}}</div>
                </div>
                <div class="lb-info">
                    <div class="lb-name">${{rep.name}}</div>
                    <div class="activity-bar-track"><div class="activity-bar-fill status-${{bar_status}}${{bar_shimmer}}" style="width:${{bar_width.toFixed(0)}}%"></div></div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num ${{calls_status}}">${{calls_display}}</div>
                    <div class="metric-label">${{calls_cd === 0 ? 'Calls' : 'Calls to go'}}</div>
                    <div class="metric-actual">${{rep.calls}} made</div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num ${{duration_status}}">${{duration_display}}</div>
                    <div class="metric-label">${{duration_cd === 0 ? 'Duration' : 'Min to go'}}</div>
                    <div class="metric-actual">${{rep.duration}}m total</div>
                </div>
                <div class="metric-cell">
                    <div class="countdown-num ${{emails_status}}">${{emails_display}}</div>
                    <div class="metric-label">${{emails_cd === 0 ? 'Emails' : 'Emails to go'}}</div>
                    <div class="metric-actual">${{rep.emails}} sent</div>
                </div>
            `;
            lb.appendChild(row);

            // Add confetti to target-hit rows
            if (metric_hit) {{
                const colors = ['#FFD700', '#FF5C28', '#1DB954', '#FF7A52', '#FFC107', '#E04040'];
                for (let c = 0; c < 12; c++) {{
                    const piece = document.createElement('div');
                    piece.className = 'confetti-piece';
                    piece.style.left = Math.random() * 100 + '%';
                    piece.style.top = '-10px';
                    piece.style.background = colors[Math.floor(Math.random() * colors.length)];
                    piece.style.animationDelay = (Math.random() * 3) + 's';
                    piece.style.animationDuration = (2 + Math.random() * 2) + 's';
                    row.appendChild(piece);
                }}
            }}
        }});
    }}

    // ── Confetti for initial target-hit rows ──
    document.querySelectorAll('.lb-row.target-hit').forEach(row => {{
        const colors = ['#FFD700', '#FF5C28', '#1DB954', '#FF7A52', '#FFC107', '#E04040'];
        for (let i = 0; i < 12; i++) {{
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = Math.random() * 100 + '%';
            piece.style.top = '-10px';
            piece.style.background = colors[Math.floor(Math.random() * colors.length)];
            piece.style.animationDelay = (Math.random() * 3) + 's';
            piece.style.animationDuration = (2 + Math.random() * 2) + 's';
            row.appendChild(piece);
        }}
    }});

    // ── Auto-rotate tabs every 10 seconds ──
    const metricCycle = ['calls', 'duration', 'emails'];
    let currentTabIndex = 0;
    setInterval(() => {{
        currentTabIndex = (currentTabIndex + 1) % metricCycle.length;
        switchTab(metricCycle[currentTabIndex]);
    }}, 10000);

    // ── TV MODE: add ?tv=cw or ?tv=ccw to URL, or auto-detect Samsung TV ──
    (function() {{
        var params = new URLSearchParams(window.location.search);
        var tvMode = params.get('tv');

        // Auto-detect Samsung Smart TV (Tizen browser) — default to ccw for activity dashboard
        if (!tvMode) {{
            var ua = navigator.userAgent || '';
            if (/SMART-TV|Tizen|Samsung/i.test(ua)) {{
                tvMode = 'ccw';
                console.log('Auto-detected Samsung TV, using tv=ccw. UA: ' + ua);
            }}
        }}

        if (!tvMode) return; // No param and not a TV = normal desktop view

        document.body.style.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';

        function setupTV() {{
            var w = document.getElementById('tvWrapper');
            var vw = window.innerWidth;
            var vh = window.innerHeight;
            var s = vh / 1080;
            var availH = Math.ceil(vw / s);
            w.style.position = 'absolute';
            w.style.top = '0';
            w.style.left = '0';
            w.style.margin = '0';
            w.style.width = '1080px';
            w.style.height = availH + 'px';
            w.style.overflow = 'hidden';
            w.style.transformOrigin = 'top left';
            if (tvMode === 'ccw') {{
                w.style.transform = 'translateY(' + vh + 'px) rotate(-90deg) scale(' + s + ')';
            }} else {{
                w.style.transform = 'translateX(' + vw + 'px) rotate(90deg) scale(' + s + ')';
            }}
            console.log('TV mode=' + tvMode + ': ' + vw + 'x' + vh + ', scale=' + s.toFixed(3));

            // Auto-scroll ONLY the leaderboard list — header stays pinned
            setTimeout(function() {{
                var list = document.getElementById('leaderboard-list');
                if (!list) return;

                // Calculate available height for the leaderboard list
                var ticker = document.querySelector('.activity-ticker');
                var tabs = document.querySelector('.metric-tabs');
                var lbHeader = document.querySelector('.leaderboard-header');
                var footer = document.querySelector('.dash-footer');
                var headerH = 0;
                if (ticker) headerH += ticker.offsetHeight;
                if (tabs) headerH += tabs.offsetHeight;
                if (lbHeader) headerH += lbHeader.offsetHeight;
                if (footer) headerH += footer.offsetHeight;
                // Add some padding
                headerH += 40;

                var listH = availH - headerH;
                if (listH < 200) listH = availH * 0.6;

                list.style.maxHeight = listH + 'px';
                list.style.overflow = 'hidden';

                console.log('TV scroll: availH=' + availH + ', headerH=' + headerH + ', listH=' + listH);

                // Scroll the leaderboard list
                var contentH = list.scrollHeight;
                if (contentH > listH && !list._scrolling) {{
                    list._scrolling = true;
                    var scrollMax = contentH - listH;
                    var pos = 0, speed = 30, pauseMs = 4000, dir = 1, lastT = 0;
                    function tick(t) {{
                        if (!lastT) {{ lastT = t; requestAnimationFrame(tick); return; }}
                        pos += speed * dir * ((t - lastT) / 1000);
                        lastT = t;
                        if (pos >= scrollMax) {{
                            pos = scrollMax; list.scrollTop = pos; dir = -1; lastT = 0;
                            setTimeout(function() {{ requestAnimationFrame(tick); }}, pauseMs); return;
                        }}
                        if (pos <= 0) {{
                            pos = 0; list.scrollTop = pos; dir = 1; lastT = 0;
                            setTimeout(function() {{ requestAnimationFrame(tick); }}, pauseMs); return;
                        }}
                        list.scrollTop = pos;
                        requestAnimationFrame(tick);
                    }}
                    setTimeout(function() {{ requestAnimationFrame(tick); }}, pauseMs);
                }}
            }}, 500);
        }}
        setupTV();
        window.addEventListener('resize', setupTV);

        // Fullscreen — hides TV browser toolbar/sidebar
        var wantFS = true;
        function goFS() {{
            var el = document.documentElement;
            var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
            if (fn) fn.call(el).catch(function(){{}});
        }}
        goFS();
        document.addEventListener('click', goFS);
        document.addEventListener('fullscreenchange', function() {{
            if (!document.fullscreenElement && wantFS) setTimeout(goFS, 500);
            setTimeout(setupTV, 200);
        }});
        document.addEventListener('webkitfullscreenchange', function() {{
            if (!document.webkitFullscreenElement && wantFS) setTimeout(goFS, 500);
            setTimeout(setupTV, 200);
        }});
        setInterval(function() {{
            if (wantFS && !document.fullscreenElement && !document.webkitFullscreenElement) goFS();
        }}, 30000);
    }})();
</script>

</div><!-- /tv-rotate-wrapper -->
</body>
</html>
'''
    return html


def main():
    """Main function: fetch data, generate HTML, write file."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Daily Activity Dashboard Generator")

    try:
        print("  Fetching today's calls...")
        calls = fetch_todays_calls()
        print(f"    Found {len(calls)} call activities")

        print("  Fetching today's emails...")
        emails = fetch_todays_emails()
        print(f"    Found {len(emails)} email activities")

        print("  Aggregating activities by rep...")
        rep_stats = aggregate_activities(calls, emails)

        print("  Building ticker items...")
        ticker_items = build_ticker_items(calls, emails, rep_stats)

        print("  Loading rep photos...")
        rep_photos = {}
        for uid, rep in REPS.items():
            photo_uri = get_photo_data_uri(rep['name'])
            if photo_uri:
                rep_photos[uid] = photo_uri

        rep_photos_json = json.dumps(rep_photos)

        print("  Generating HTML...")
        html = generate_html(rep_stats, ticker_items, rep_photos_json)

        output_file = SCRIPT_DIR / "activity-dashboard.html"
        with open(output_file, 'w') as f:
            f.write(html)
        print(f"  Written to {output_file}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Complete!")
        return True
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    if '--once' in sys.argv:
        main()
    else:
        while True:
            success = main()
            if success:
                print(f"Sleeping 5 minutes... (next update at {(datetime.now() + timedelta(minutes=5)).strftime('%H:%M:%S')})")
                time.sleep(300)
            else:
                print("Retrying in 30 seconds...")
                time.sleep(30)
