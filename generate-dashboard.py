#!/usr/bin/env python3
"""
Clerk.io MRR Dashboard Generator
=================================
Fetches won opportunities from Close CRM and generates a self-contained HTML dashboard.

Usage:
  python3 generate-dashboard.py --once     # Fetch once, generate HTML, exit
  python3 generate-dashboard.py            # Loop every 5 minutes

The generated HTML file auto-refreshes in the browser every 5 minutes.
Photos: place rep headshots in a 'photos/' folder next to this script.
"""

import json
import csv
import io
import base64
import urllib.request
import urllib.error
import sys
import os
import time
import calendar
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Copenhagen timezone for accurate "today" calculation
CPH_TZ = ZoneInfo("Europe/Copenhagen")

# ── Configuration ─────────────────────────────────────────────────────────────
CLOSE_API_BASE = "https://api.close.com/api/v1"
CLOSE_API_KEY = os.environ.get("CLOSE_API_KEY", "")
WON_STATUS_IDS = [
    "stat_IyAn2lpFlElQQjqLVGs9Pc1TfeJqTJaN3ZX0L147a61",  # Closed Won - contract signed
    "stat_sWOJvWOgidm8OspaJ0oiwgaAfHQtHv1kn4O5xKvZkrx",  # Cross-Sell Won
]
PIPELINE_ID = "pipe_4r3PtlYGyS8nyD57HXlyyQ"

# Local targets CSV (edit this file directly in the repo each month)
TARGETS_CSV_PATH = Path(__file__).parent / "targets.csv"

REPS = {
    'user_yBw9tNt4WNDf34dsPFG48SpvefoK7A8zPMjfU4K4DYM': {'name': 'Robert Bengtsson', 'initials': 'RB', 'email': 'rob@clerk.io', 'target': 11864},
    'user_7bbV5f2geHD1hLDw54p9Vr088T3yW6TSBLUs8JAMEzV': {'name': 'Peter Rossé', 'initials': 'PR', 'email': 'ptr@clerk.io', 'target': 11046},
    'user_O0GV7AdCKCB5bOrK89NeJYyNoPYpcLjJCCUHinDgoLR': {'name': 'Anders Hildan', 'initials': 'AH', 'email': 'anh@clerk.io', 'target': 9750},
    'user_guKLcbLohZnYhgae5FGvEK6f9ay5fTsAvOnfq6pq3gn': {'name': 'Braxton Phillips', 'initials': 'BP', 'email': 'brp@clerk.io', 'target': 14250},
    'user_5Mkg13Ge14LxiplY5t8phIud1vfqxkVe6su6RF4IJRh': {'name': 'Arnab Deb', 'initials': 'AD', 'email': 'ade@clerk.io', 'target': 5000},
    'user_YJuiXnlZrSDAeBGXHL7ehssMRWzxlH86jtXr7NExbss': {'name': 'Alexander Alken', 'initials': 'AA', 'email': 'aal@clerk.io', 'target': 9068},
    'user_rgafRJqGdOmQVhsZx3fh8PcL12ASTMFm9asWvHpfDs2': {'name': 'Alexandra Beikerts', 'initials': 'AB', 'email': 'alb@clerk.io', 'target': 7636},
    'user_SAZq4wEnfq5ILVTsn0ftwUOk2B3buDEoboxWigYg0ku': {'name': 'Daniela Drobna', 'initials': 'DD', 'email': 'ddr@clerk.io', 'target': 8650},
    'user_sVcAJW2NzbU6ZlfVrX4zqUp78rbJXQEyGq7tmFugyHY': {'name': 'Christian Antoniu', 'initials': 'CA', 'email': 'chn@clerk.io', 'target': 7989},
    'user_nwSw0RV3curn6amDVD8qbiYkB02K3D7a2PN7CBZlZPa': {'name': 'Alessio Catania', 'initials': 'AC', 'email': 'alc@clerk.io', 'target': 7636},
    'user_5pIrGaTwAhuFiCpleT0rdfI86E2HoOra853wfUuJmRx': {'name': 'Maja Krokowska', 'initials': 'MK', 'email': 'maj@clerk.io', 'target': 5000},
}

SCRIPT_DIR = Path(__file__).parent
# Try both 'photos' and 'Photos' (Linux is case-sensitive)
PHOTOS_DIR = SCRIPT_DIR / "photos"
if not PHOTOS_DIR.exists():
    PHOTOS_DIR = SCRIPT_DIR / "Photos"
# ──────────────────────────────────────────────────────────────────────────────


def format_currency(dkk_amount):
    """Format currency as 'DKK X,XXX.XX' with full amount and 2 decimal places."""
    return f'DKK {dkk_amount:,.2f}'


def format_amount(dkk_amount):
    """Format amount without DKK prefix: 'X,XXX.XX'."""
    return f'{dkk_amount:,.2f}'


def close_api_request(endpoint, params=None):
    """Make a request to Close API with basic auth."""
    url = f"{CLOSE_API_BASE}{endpoint}"
    if params:
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
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


def fetch_won_opportunities():
    """Fetch all won opportunities from Close API with pagination.
    Fetches from both 'Closed Won - contract signed' and 'Cross-Sell Won' statuses."""
    opportunities = []

    for status_id in WON_STATUS_IDS:
        skip = 0
        limit = 100

        while True:
            params = {
                'status_id': status_id,
                '_limit': limit,
                '_skip': skip,
            }
            try:
                response = close_api_request('/opportunity/', params)
                data = response.get('data', [])
                opportunities.extend(data)

                if not response.get('has_more', False):
                    break
                skip += limit
            except Exception as e:
                print(f"Error fetching opportunities (status {status_id}): {e}")
                break

    return opportunities


def get_close_date(opp):
    """Extract close date string from opportunity, trying multiple field names."""
    for field in ['close_date', 'date_won', 'close_at']:
        val = opp.get(field)
        if val:
            return val[:10]  # "YYYY-MM-DD"
    return None


def calculate_mrr(opp):
    """Calculate monthly MRR from an opportunity. Values are in cents."""
    value = opp.get('value', 0) or 0
    value_dkk = value / 100
    period = opp.get('value_period', 'monthly')

    if period == 'monthly':
        return value_dkk
    elif period == 'annual':
        return value_dkk / 12
    elif period == 'one_time':
        return value_dkk  # Count one-time as full value
    return value_dkk


def filter_by_date_range(opps, start_date, end_date_exclusive):
    """Filter opportunities where close date is in [start_date, end_date_exclusive)."""
    filtered = []
    for opp in opps:
        close_date = get_close_date(opp)
        if close_date and start_date <= close_date < end_date_exclusive:
            filtered.append(opp)
    return filtered


def aggregate_by_rep(opps):
    """Aggregate MRR by rep. Only counts configured reps."""
    rep_mrr = {}
    for opp in opps:
        user_id = opp.get('user_id')
        if not user_id or user_id not in REPS:
            continue
        mrr = calculate_mrr(opp)
        rep_mrr[user_id] = rep_mrr.get(user_id, 0) + mrr
    return rep_mrr


def get_won_date(opp):
    """Get the date a deal was actually won (when status changed), not the projected close date.
    Uses updated_at as proxy since Close doesn't expose a date_won field."""
    for field in ['date_won', 'updated_at']:
        val = opp.get(field)
        if val:
            return val[:10]  # "YYYY-MM-DD"
    return None


def count_recent_deals_by_rep(opps, start_date, end_date_exclusive):
    """Count deals per rep that were WON (updated) within a date range.
    Uses updated_at instead of close_at, since close_at is the projected date
    and may not reflect when the deal was actually marked as won."""
    counts = {}
    for opp in opps:
        user_id = opp.get('user_id')
        if not user_id or user_id not in REPS:
            continue
        won_date = get_won_date(opp)
        if won_date and start_date <= won_date < end_date_exclusive:
            counts[user_id] = counts.get(user_id, 0) + 1
    return counts


def get_recent_deals(opps, count=3):
    """Get the most recently closed deals from the list of opportunities."""
    scored = []
    for opp in opps:
        close_date = get_close_date(opp)
        if not close_date:
            continue
        updated = opp.get('date_updated', '') or opp.get('date_created', '') or close_date
        scored.append((updated, opp))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [opp for _, opp in scored[:count]]


def load_targets_from_csv():
    """
    Load monthly targets from the local targets.csv file.

    The CSV has columns: email, name, date (M/D/YYYY), target
    Returns a nested dict: {user_id: {YYYY-MM: target_amount}}
    Falls back to empty dict if file is missing (hardcoded REPS targets used instead).
    """
    if not TARGETS_CSV_PATH.exists():
        print(f"  ⚠ targets.csv not found at {TARGETS_CSV_PATH}")
        return {}

    email_to_uid = {r['email']: uid for uid, r in REPS.items()}

    try:
        raw = TARGETS_CSV_PATH.read_text(encoding='utf-8-sig')
    except Exception as e:
        print(f"  ⚠ Could not read targets.csv: {e}")
        return {}

    targets = {}
    reader = csv.reader(io.StringIO(raw))
    rows_matched = 0

    for row_num, row in enumerate(reader):
        if len(row) < 4:
            continue

        email_raw = row[0].strip().lower()
        date_raw = row[2].strip()
        target_raw = row[3].strip().replace(',', '')

        # Skip header row
        if row_num == 0 and not any(c.isdigit() for c in date_raw):
            continue

        uid = email_to_uid.get(email_raw)
        if not uid:
            continue

        try:
            parts = date_raw.split('/')
            month = int(parts[0])
            year = int(parts[2])
            month_key = f"{year}-{month:02d}"
        except (ValueError, IndexError):
            continue

        try:
            target_val = float(target_raw)
        except ValueError:
            continue

        if uid not in targets:
            targets[uid] = {}
        targets[uid][month_key] = target_val
        rows_matched += 1

    print(f"  Loaded {rows_matched} targets from targets.csv")
    return targets


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
    full_name_space = rep_name  # Original casing with spaces (e.g., "Robert Bengtsson")
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


def get_status_color(percent):
    """Return CSS color based on percentage of target achieved."""
    if percent >= 100:
        return 'var(--green)'
    elif percent >= 50:
        return 'var(--yellow-dark)'
    return 'var(--red)'


def generate_html(monthly_mrr, ytd_mrr, monthly_opps, streak_counts, recent_deals_info, all_ytd_opps_json, rep_photos_json, csv_targets_json):
    """Generate the complete dashboard HTML with all CSS and data."""
    now_cph = datetime.now(CPH_TZ)
    today = now_cph.date()
    now = now_cph
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    current_month = f"{month_names[today.month - 1]} {today.year}"
    updated_time = now.strftime('%I:%M:%S %p')

    # ── Days left in month ──
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day
    if days_left == 0:
        days_left = 1  # Avoid division by zero on last day

    # ── Calculate summary values ──
    total_mrr = sum(monthly_mrr.get(uid, 0) for uid in REPS)
    total_target = sum(r['target'] for r in REPS.values())
    achieved_pct = (total_mrr / total_target * 100) if total_target > 0 else 0
    on_track = sum(1 for uid in REPS if monthly_mrr.get(uid, 0) >= REPS[uid]['target'])

    # ── Pace calculation ──
    remaining = max(total_target - total_mrr, 0)
    pace_per_day = remaining / days_left if days_left > 0 else 0

    # ── Latest wins ticker (last 3 deals, duplicated for seamless loop) ──
    ticker_html = ''
    if recent_deals_info:
        ticker_items = ''
        for deal in recent_deals_info:
            d_rep = deal.get('rep_name', 'Unknown')
            d_company = deal.get('lead_name', 'Unknown')
            d_value = deal.get('value', 0)
            ticker_items += f'''
                <div class="ticker-item">
                    <span class="ticker-icon">&#127881;</span>
                    <span class="ticker-rep">{d_rep}</span> closed
                    <span class="ticker-company">{d_company}</span> for
                    <span class="ticker-value">{format_currency(d_value)}</span>
                    <span class="ticker-sep"></span>
                </div>'''
        # Duplicate the items for seamless infinite scroll
        ticker_html = f'''
    <div class="deal-ticker">
        <div class="ticker-label"><span class="ticker-dot"></span> LATEST WINS</div>
        <div class="ticker-track">
            {ticker_items}
            {ticker_items}
        </div>
    </div>'''

    # ── Build leaderboard rows ──
    rep_data = []
    for uid, rep in REPS.items():
        mrr = monthly_mrr.get(uid, 0)
        pct = (mrr / rep['target'] * 100) if rep['target'] > 0 else 0
        rep_data.append({
            'uid': uid,
            'name': rep['name'],
            'initials': rep['initials'],
            'target': rep['target'],
            'mrr': mrr,
            'pct': pct,
            'streak': streak_counts.get(uid, 0),
        })
    rep_data.sort(key=lambda x: x['pct'], reverse=True)

    leaderboard_rows = []
    for rank, rep in enumerate(rep_data, 1):
        # Row classes
        classes = ['lb-row']
        if rep['pct'] >= 100:
            classes.append('target-achieved')
        if rep['pct'] < 50:
            classes.append('below-target')
        elif rank <= 3:
            classes.append('top-3')
        if rank > 5:
            classes.append('compact')

        # Photo or initials
        photo_uri = get_photo_data_uri(rep['name'])
        if photo_uri:
            photo_inner = f'<img src="{photo_uri}" alt="{rep["name"]}">'
        else:
            photo_inner = f'<span class="lb-photo-initials">{rep["initials"]}</span>'

        # Crown for 100%+ achievers
        crown_html = ''
        if rep['pct'] >= 100:
            crown_html = '<span class="crown-emoji">&#128081;</span>'

        # Rank badge class (gold/silver/bronze for top 3)
        badge_class = 'rank-badge'
        if rank == 1:
            badge_class += ' gold'
        elif rank == 2:
            badge_class += ' silver'
        elif rank == 3:
            badge_class += ' bronze'

        # Flame streak indicator
        streak_html = ''
        if rep['streak'] >= 2:
            streak_html = f'<span class="streak-badge" title="{rep["streak"]} deals in last 5 days">&#128293; {rep["streak"]}</span>'

        # Progress bar
        display_pct = min(rep['pct'], 100)
        is_over = rep['pct'] >= 100
        bar_container_class = 'lb-bar-container over-target' if is_over else 'lb-bar-container'

        # Shimmer class for milestones
        shimmer_class = ''
        if rep['pct'] >= 100:
            shimmer_class = ' shimmer-100'
        elif rep['pct'] >= 75:
            shimmer_class = ' shimmer-75'
        elif rep['pct'] >= 50:
            shimmer_class = ' shimmer-50'

        if is_over:
            bar_style = f'width: 100%; background: linear-gradient(90deg, #5CB854 0%, #1DB954 40%, #17a34a 100%); background-size: 100% 100%;'
        elif display_pct > 0:
            bg_size = (100 / display_pct) * 100
            bar_style = f'width: {display_pct:.1f}%; background-size: {bg_size:.1f}% 100%;'
        else:
            bar_style = 'width: 0%;'

        # Percentage color
        pct_color = get_status_color(rep['pct'])

        # Countdown values
        remaining = max(rep['target'] - rep['mrr'], 0)
        is_hit = rep['pct'] >= 100
        earned_display = format_amount(rep['mrr'])
        bar_earned_class = 'bar-earned' if display_pct >= 35 else 'bar-earned outside'

        if is_hit:
            countdown_html = '<div class="countdown-amount hit">&#10003; Target hit</div>'
        else:
            countdown_html = f'<div><span class="countdown-amount">{format_amount(remaining)}</span><span class="countdown-arrow">&#8595;</span></div>'

        if is_hit:
            pct_arrow_html = f'<span class="pct-arrow" style="color: {pct_color};">&#8593;</span>'
        else:
            pct_arrow_html = f'<span class="pct-arrow" style="color: {pct_color};">&#8593;</span>'

        row = f'''            <div class="{' '.join(classes)}">
                <div class="photo-rank-wrap">
                    {crown_html}
                    <div class="lb-photo">{photo_inner}</div>
                    <div class="{badge_class}">{rank}</div>
                </div>
                <div class="lb-info">
                    <div class="lb-name-row">
                        <span class="lb-name">{rep['name']}</span>
                        {streak_html}
                    </div>
                    <div class="{bar_container_class}">
                        <div class="lb-bar-fill{shimmer_class}" style="{bar_style}">
                            <span class="{bar_earned_class}">{earned_display} DKK</span>
                        </div>
                    </div>
                </div>
                <div class="lb-countdown">
                    {countdown_html}
                </div>
                <div class="lb-pct">
                    <div>
                        <span class="lb-pct-value" style="color: {pct_color};" data-countup-pct="{rep['pct']:.0f}">{rep['pct']:.0f}%</span>{pct_arrow_html}
                    </div>
                    <div class="lb-pct-sub">{format_amount(rep['target'])}</div>
                </div>
            </div>'''
        leaderboard_rows.append(row)

    leaderboard_html = '\n'.join(leaderboard_rows)

    # ── Year leaders (top 3 by YTD) ──
    ytd_data = []
    for uid, rep in REPS.items():
        ytd_data.append({'name': rep['name'], 'mrr': ytd_mrr.get(uid, 0)})
    ytd_data.sort(key=lambda x: x['mrr'], reverse=True)
    medals = ['&#129351;', '&#129352;', '&#129353;']

    year_leaders_html = ''
    for i, leader in enumerate(ytd_data[:3]):
        year_leaders_html += f'''
            <div class="year-leader">
                <div class="year-leader-rank">{medals[i]}</div>
                <div class="year-leader-name">{leader['name']}</div>
                <div class="year-leader-amount" data-countup="{leader['mrr']:.2f}">{format_amount(leader['mrr'])}</div>
            </div>'''

    # ── Hero value color ──
    hero_color = get_status_color(achieved_pct)

    # ── Pre-compute REPS_CONFIG JSON (can't use json.dumps inside f-string) ──
    reps_config_json = json.dumps({uid: {'name': r['name'], 'initials': r['initials'], 'target': r['target']} for uid, r in REPS.items()})

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>Clerk.io — MRR Performance Dashboard</title>
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

        /* Dark Mode */
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

        body.dark-mode .lb-bar-container {{
            background: linear-gradient(180deg, #111122 0%, #1e1e35 50%, #111122 100%);
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.05);
            border: 1px solid rgba(0,0,0,0.4);
        }}

        body.dark-mode .lb-bar-container.over-target {{
            background: linear-gradient(180deg, rgba(29,185,84,0.12) 0%, rgba(29,185,84,0.22) 50%, rgba(29,185,84,0.12) 100%);
        }}

        /* Theme Toggle */
        .theme-toggle {{
            position: fixed;
            bottom: 24px;
            right: 40px;
            width: 48px;
            height: 48px;
            border-radius: 50%;
            border: 2px solid var(--border);
            background: var(--surface-raised);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: var(--shadow-md);
            transition: all 0.3s ease;
            z-index: 100;
        }}

        .theme-toggle:hover {{
            border-color: var(--clerk-orange);
            box-shadow: 0 0 16px rgba(255, 92, 40, 0.25);
            transform: scale(1.08);
        }}

        .theme-toggle svg {{
            width: 22px;
            height: 22px;
            color: var(--text-secondary);
            transition: color 0.3s ease;
        }}

        .theme-toggle:hover svg {{
            color: var(--clerk-orange);
        }}

        .theme-toggle .icon-sun {{ display: none; }}
        .theme-toggle .icon-moon {{ display: block; }}
        body.dark-mode .theme-toggle .icon-sun {{ display: block; }}
        body.dark-mode .theme-toggle .icon-moon {{ display: none; }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        /* ═══════════════════════════════════════════
           LAYOUT — portrait dashboard at 1080px wide.
           Add ?tv=cw or ?tv=ccw to the URL to enable
           rotation for vertically-mounted TVs.
           ═══════════════════════════════════════════ */
        .tv-rotate-wrapper {{
            width: 1080px;
            margin: 0 auto;
            padding: 24px 32px;
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
           DEAL TICKER — continuous scrolling news ticker
           ═══════════════════════════════════════════ */
        .deal-ticker {{
            background: linear-gradient(135deg, var(--green-bg), var(--surface));
            border: 2px solid var(--green);
            border-radius: var(--radius-md);
            margin-bottom: 20px;
            overflow: hidden;
            position: relative;
            height: 56px;
            display: flex;
            align-items: center;
        }}

        .ticker-label {{
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 18px;
            background: var(--green);
            color: #fff;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
            z-index: 2;
            white-space: nowrap;
            border-radius: 10px 0 0 10px;
        }}

        @keyframes tickerDotPulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(0.8); }}
        }}
        .ticker-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #fff;
            animation: tickerDotPulse 1.5s ease-in-out infinite;
            flex-shrink: 0;
        }}

        .ticker-track {{
            display: flex;
            animation: tickerScroll 22s linear infinite;
            padding-left: 140px;
        }}

        @keyframes tickerScroll {{
            0% {{ transform: translateX(0); }}
            100% {{ transform: translateX(-50%); }}
        }}

        .ticker-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 40px;
            white-space: nowrap;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
        }}

        .ticker-icon {{ font-size: 20px; }}
        .ticker-rep {{ font-weight: 700; color: var(--clerk-orange); }}
        .ticker-company {{ font-weight: 700; }}
        .ticker-value {{ font-weight: 800; color: var(--green); }}

        .ticker-sep {{
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: var(--text-tertiary);
            margin: 0 12px;
            flex-shrink: 0;
        }}

        /* Fade-out on right edge */
        .deal-ticker::after {{
            content: '';
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 60px;
            background: linear-gradient(90deg, transparent, var(--surface));
            z-index: 1;
            border-radius: 0 10px 10px 0;
        }}

        body.dark-mode .deal-ticker::after {{
            background: linear-gradient(90deg, transparent, var(--bg));
        }}

        .live-indicator {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 11px;
            font-weight: 600;
            color: var(--green);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .live-dot {{
            width: 8px;
            height: 8px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(29, 185, 84, 0.4); }}
            50% {{ opacity: 0.7; box-shadow: 0 0 0 6px rgba(29, 185, 84, 0); }}
        }}

        .clock {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            font-variant-numeric: tabular-nums;
        }}

        /* Layout — single-column portrait for vertical TV (1080×1920) */
        .layout {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-width: 1080px;
            margin: 0 auto;
        }}

        /* Left Panel — now stacks above leaderboard */
        .panel-left {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .card {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 28px;
            border: 1px solid var(--border);
        }}

        .card-label {{
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: var(--text-primary);
            margin-bottom: 18px;
        }}

        /* Hero MRR Card */
        .hero-card {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 32px;
            border: 2px solid var(--clerk-orange);
            text-align: center;
            position: relative;
            overflow: hidden;
        }}

        .hero-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--clerk-orange), var(--clerk-orange-light));
        }}

        .hero-label {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: var(--text-primary);
            margin-bottom: 12px;
        }}

        .hero-value {{
            font-size: 64px;
            font-weight: 800;
            line-height: 1;
            letter-spacing: -2px;
            margin-bottom: 8px;
        }}

        .hero-change {{
            font-size: 13px;
            font-weight: 600;
            color: var(--green);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }}

        .hero-change svg {{ width: 14px; height: 14px; }}

        /* Summary Grid — 4 tiles in portrait */
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }}

        .summary-tile {{
            background: var(--surface-raised);
            border: 2px solid var(--clerk-orange);
            border-radius: var(--radius-md);
            padding: 18px 12px;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .summary-tile-label {{
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-primary);
            margin-bottom: 10px;
        }}

        .summary-tile-value {{
            font-size: 26px;
            font-weight: 700;
            line-height: 1;
        }}

        /* ═══════════════════════════════════════════
           DAYS LEFT / PACE WIDGET
           ═══════════════════════════════════════════ */
        .countdown-card {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 24px 28px;
            border: 2px solid var(--clerk-orange);
            text-align: center;
        }}

        .countdown-row {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            margin-bottom: 12px;
        }}

        .countdown-number {{
            font-size: 48px;
            font-weight: 800;
            color: var(--clerk-orange);
            line-height: 1;
            letter-spacing: -2px;
        }}

        .countdown-label {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-align: left;
            line-height: 1.4;
        }}

        .countdown-label strong {{
            color: var(--text-primary);
            font-weight: 700;
        }}

        .pace-indicator {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            background: var(--clerk-orange-bg);
            padding: 10px 16px;
            border-radius: 8px;
        }}

        .pace-indicator strong {{
            color: var(--clerk-orange);
            font-weight: 700;
        }}

        /* Year Leaders — horizontal strip for portrait */
        .year-leaders {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }}

        .year-leader {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: var(--surface-raised);
            padding: 16px 18px;
            border-radius: var(--radius-lg);
            border: 2px solid var(--clerk-orange);
            box-shadow: var(--shadow-sm);
            transition: box-shadow 0.2s ease;
        }}

        .year-leader:hover {{
            box-shadow: var(--shadow-md);
        }}

        .year-leader-rank {{
            font-size: 28px;
            text-align: center;
            line-height: 1;
            flex-shrink: 0;
        }}

        .year-leader-name {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .year-leader-amount {{
            font-size: 18px;
            font-weight: 700;
            color: var(--green);
        }}

        /* Leaderboard — full width in portrait */
        .panel-right {{
            display: flex;
            flex-direction: column;
        }}

        .leaderboard-card {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 24px 28px;
            border: 1px solid var(--border);
            flex: 1;
        }}

        .leaderboard-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--border);
        }}

        .leaderboard-title {{
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }}

        .leaderboard-month {{
            font-size: 18px;
            font-weight: 700;
            color: var(--clerk-orange);
            background: var(--clerk-orange-bg);
            padding: 10px 24px;
            border-radius: 24px;
            letter-spacing: 0.5px;
        }}

        .month-selector {{
            font-family: 'Poppins', sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: var(--clerk-orange);
            background: var(--clerk-orange-bg);
            padding: 10px 20px;
            border-radius: 24px;
            border: 2px solid var(--clerk-orange);
            cursor: pointer;
            outline: none;
            appearance: none;
            -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23FF5C28' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 14px center;
            padding-right: 36px;
            transition: all 0.2s ease;
        }}

        .month-selector:hover {{
            box-shadow: 0 0 12px rgba(255, 92, 40, 0.25);
        }}

        .month-selector option {{
            font-family: 'Poppins', sans-serif;
            font-weight: 600;
            background: var(--surface-raised);
            color: var(--text-primary);
        }}

        .month-selector-note {{
            font-size: 10px;
            font-weight: 500;
            color: var(--text-tertiary);
            text-align: center;
            margin-top: -4px;
            opacity: 0;
            transition: opacity 0.3s;
        }}

        .month-selector-note.visible {{
            opacity: 1;
        }}

        .leaderboard-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        /* ═══════════════════════════════════════════
           LEADERBOARD ROW — with visual hierarchy
           ═══════════════════════════════════════════ */
        .lb-row {{
            display: grid;
            grid-template-columns: 68px 1fr 160px 130px;
            gap: 16px;
            align-items: center;
            background: var(--surface-raised);
            padding: 16px 20px;
            border-radius: var(--radius-md);
            border-left: 4px solid var(--clerk-orange);
            box-shadow: var(--shadow-sm);
            transition: all 0.2s ease;
        }}

        /* Top 3 are larger and more prominent */
        .lb-row.top-3 {{
            padding: 20px 24px;
            background: var(--clerk-orange-bg);
            border-left-width: 5px;
        }}

        .lb-row.top-3 .lb-name {{
            font-size: 18px;
        }}

        .lb-row.top-3 .countdown-amount {{
            font-size: 24px;
        }}

        .lb-row.top-3 .lb-pct-value {{
            font-size: 26px;
        }}

        .lb-row.top-3 .lb-photo {{
            width: 58px;
            height: 58px;
            border-color: var(--clerk-orange);
        }}

        /* Compact rows (rank 6+) */
        .lb-row.compact {{
            padding: 10px 20px;
            gap: 12px;
        }}

        .lb-row.compact .lb-name {{
            font-size: 14px;
        }}

        .lb-row.compact .countdown-amount {{
            font-size: 18px;
        }}

        .lb-row.compact .countdown-arrow {{
            font-size: 14px;
        }}

        .lb-row.compact .bar-earned {{
            font-size: 9px;
        }}

        .lb-row.compact .lb-pct-value {{
            font-size: 20px;
        }}

        .lb-row.compact .lb-photo {{
            width: 40px;
            height: 40px;
        }}

        .lb-row.compact .rank-badge {{
            width: 20px;
            height: 20px;
            font-size: 10px;
        }}

        .lb-row.compact .lb-bar-container {{
            height: 16px;
        }}

        /* ═══════════════════════════════════════════
           TARGET ACHIEVED — gold glow + confetti
           ═══════════════════════════════════════════ */
        .lb-row.target-achieved {{
            background: linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,215,0,0.03));
            border-left-color: #FFD700;
            box-shadow: 0 0 20px rgba(255, 215, 0, 0.15), 0 0 40px rgba(255, 215, 0, 0.05), var(--shadow-sm);
            animation: goldPulse 3s ease-in-out infinite;
        }}

        @keyframes goldPulse {{
            0%, 100% {{ box-shadow: 0 0 20px rgba(255, 215, 0, 0.15), 0 0 40px rgba(255, 215, 0, 0.05), var(--shadow-sm); }}
            50% {{ box-shadow: 0 0 28px rgba(255, 215, 0, 0.25), 0 0 56px rgba(255, 215, 0, 0.10), var(--shadow-sm); }}
        }}

        .lb-row.target-achieved .confetti-burst {{
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            pointer-events: none;
            overflow: hidden;
        }}

        /* Combined photo + rank badge wrapper */
        .photo-rank-wrap {{
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .crown-emoji {{
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 16px;
            z-index: 3;
            filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));
            animation: crownBob 2s ease-in-out infinite;
        }}

        @keyframes crownBob {{
            0%, 100% {{ transform: translateX(-50%) translateY(0); }}
            50% {{ transform: translateX(-50%) translateY(-3px); }}
        }}

        /* Streak badge */
        .streak-badge {{
            font-size: 12px;
            font-weight: 700;
            background: linear-gradient(135deg, #FF6B35, #FF4500);
            color: #fff;
            padding: 2px 8px;
            border-radius: 10px;
            margin-left: 8px;
            white-space: nowrap;
            box-shadow: 0 2px 6px rgba(255, 69, 0, 0.3);
        }}

        .lb-name-row {{
            display: flex;
            align-items: center;
        }}

        /* Rep photo — enlarged now that rank is merged */
        .lb-photo {{
            width: 52px;
            height: 52px;
            border-radius: 50%;
            overflow: hidden;
            background: var(--surface);
            border: 2px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}

        .lb-photo img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .lb-photo-initials {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-tertiary);
            letter-spacing: -0.5px;
        }}

        /* Rank badge — overlaps bottom-right of photo */
        .rank-badge {{
            position: absolute;
            bottom: -2px;
            right: -4px;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: var(--clerk-orange);
            color: #fff;
            font-size: 12px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px solid #fff;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            z-index: 2;
        }}

        /* Metallic badges for top 3 */
        .rank-badge.gold {{
            background: linear-gradient(145deg, #FFD700, #FFC107);
            color: #5C3D00;
            border-color: #FFD700;
            box-shadow: 0 1px 6px rgba(255, 215, 0, 0.5);
        }}
        .rank-badge.silver {{
            background: linear-gradient(145deg, #E8E8E8, #C0C0C0);
            color: #3a3a3a;
            border-color: #C0C0C0;
            box-shadow: 0 1px 6px rgba(192, 192, 192, 0.5);
        }}
        .rank-badge.bronze {{
            background: linear-gradient(145deg, #E08A4A, #CD7F32);
            color: #3D2200;
            border-color: #CD7F32;
            box-shadow: 0 1px 6px rgba(205, 127, 50, 0.5);
        }}

        .lb-row:hover {{
            box-shadow: var(--shadow-md);
            transform: translateX(4px);
        }}

        .lb-row.below-target {{
            border-left-color: var(--red);
            opacity: 0.7;
        }}

        .lb-info {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 0;
        }}

        .lb-name {{
            font-size: 17px;
            font-weight: 600;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        /* ═══════════════════════════════════════════
           PROGRESS BARS — Metallic Option D
           ═══════════════════════════════════════════ */
        .lb-bar-container {{
            width: 100%;
            height: 22px;
            background: linear-gradient(180deg, #c8c8c8 0%, #e0e0e0 50%, #c8c8c8 100%);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.5);
            border: 1px solid rgba(0,0,0,0.15);
        }}

        .lb-bar-fill {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94);
            position: relative;
            background: linear-gradient(90deg,
                #E04040 0%,
                #E85C3A 25%,
                #FF5C28 40%,
                #E5A100 58%,
                #C4B820 72%,
                #5CB854 88%,
                #1DB954 100%
            );
            background-position: left center;
            box-shadow:
                inset 0 -4px 6px rgba(0,0,0,0.4),
                inset 0 3px 0 rgba(255,255,255,0.55),
                inset 0 6px 8px rgba(255,255,255,0.15),
                0 2px 6px rgba(0,0,0,0.5);
        }}

        /* Shimmer animation for milestone bars */
        @keyframes shimmer {{
            0% {{ background-position: -200% center; }}
            100% {{ background-position: 200% center; }}
        }}

        .lb-bar-fill.shimmer-50::after,
        .lb-bar-fill.shimmer-75::after,
        .lb-bar-fill.shimmer-100::after {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(
                90deg,
                transparent 30%,
                rgba(255,255,255,0.3) 50%,
                transparent 70%
            );
            background-size: 200% 100%;
            animation: shimmer 3s ease-in-out infinite;
            border-radius: 3px;
        }}

        .lb-bar-fill.shimmer-75::after {{
            background: linear-gradient(
                90deg,
                transparent 30%,
                rgba(255,255,255,0.4) 50%,
                transparent 70%
            );
            background-size: 200% 100%;
            animation: shimmer 2.5s ease-in-out infinite;
        }}

        .lb-bar-fill.shimmer-100::after {{
            background: linear-gradient(
                90deg,
                transparent 25%,
                rgba(255,255,255,0.5) 50%,
                transparent 75%
            );
            background-size: 200% 100%;
            animation: shimmer 2s ease-in-out infinite;
        }}

        .bar-earned {{
            position: absolute;
            right: 6px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 11px;
            font-weight: 700;
            color: #ffffff;
            text-shadow: 0 1px 3px rgba(0,0,0,0.6);
            white-space: nowrap;
            z-index: 1;
        }}

        .bar-earned.outside {{
            right: auto;
            left: calc(100% + 8px);
            color: var(--text-tertiary);
            text-shadow: none;
        }}

        body.dark-mode .bar-earned.outside {{
            color: #9090a0;
        }}

        /* Over-target: soft green track */
        .lb-bar-container.over-target {{
            background: linear-gradient(180deg, rgba(29,185,84,0.15) 0%, rgba(29,185,84,0.25) 50%, rgba(29,185,84,0.15) 100%);
        }}

        .lb-bar-container.over-target::after {{
            content: '';
            position: absolute;
            left: calc(100% - 2px);
            top: 0;
            bottom: 0;
            width: 2px;
            background: var(--text-tertiary);
            opacity: 0.3;
        }}

        .lb-countdown {{
            text-align: right;
        }}

        .countdown-amount {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.5px;
            display: inline;
        }}

        .countdown-amount.hit {{
            color: var(--green);
        }}

        .countdown-arrow {{
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
            margin-left: 4px;
            display: inline;
        }}

        body.dark-mode .countdown-amount {{
            color: #ffffff;
        }}
        body.dark-mode .countdown-amount.hit {{
            color: var(--green);
        }}

        body.dark-mode .countdown-arrow {{
            color: #ffffff;
        }}

        .lb-pct {{
            text-align: center;
        }}

        .lb-pct-value {{
            font-size: 24px;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.5px;
            display: inline;
        }}

        .pct-arrow {{
            font-size: 18px;
            font-weight: 700;
            margin-left: 2px;
            display: inline;
        }}

        .lb-pct-sub {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-tertiary);
            margin-top: 2px;
        }}

        body.dark-mode .lb-pct-sub {{
            color: #9090a0;
            text-shadow: 0 0 6px rgba(144, 144, 160, 0.3);
        }}

        /* Footer */
        .footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 28px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 500;
        }}

        .footer-left {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .footer-divider {{
            color: var(--border);
            font-size: 14px;
        }}

        .footer-right {{
            text-align: right;
        }}

        .footer-timestamp {{
            color: var(--text-tertiary);
            font-size: 11px;
            font-weight: 500;
        }}

        /* ═══════════════════════════════════════════
           ANIMATIONS
           ═══════════════════════════════════════════ */
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(12px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .lb-row {{
            animation: fadeInUp 0.4s ease-out both;
        }}

        .lb-row:nth-child(1) {{ animation-delay: 0.05s; }}
        .lb-row:nth-child(2) {{ animation-delay: 0.10s; }}
        .lb-row:nth-child(3) {{ animation-delay: 0.15s; }}
        .lb-row:nth-child(4) {{ animation-delay: 0.20s; }}
        .lb-row:nth-child(5) {{ animation-delay: 0.25s; }}
        .lb-row:nth-child(6) {{ animation-delay: 0.30s; }}
        .lb-row:nth-child(7) {{ animation-delay: 0.35s; }}
        .lb-row:nth-child(8) {{ animation-delay: 0.40s; }}
        .lb-row:nth-child(9) {{ animation-delay: 0.45s; }}
        .lb-row:nth-child(10) {{ animation-delay: 0.50s; }}
        .lb-row:nth-child(11) {{ animation-delay: 0.55s; }}

        .hero-card {{ animation: fadeInUp 0.5s ease-out both; }}
        .summary-tile {{ animation: fadeInUp 0.4s ease-out both; }}
        .summary-tile:nth-child(1) {{ animation-delay: 0.1s; }}
        .summary-tile:nth-child(2) {{ animation-delay: 0.15s; }}
        .summary-tile:nth-child(3) {{ animation-delay: 0.2s; }}

        /* ═══════════════════════════════════════════
           CONFETTI BURST for target achievers
           ═══════════════════════════════════════════ */
        @keyframes confetti-fall {{
            0% {{ transform: translateY(-10px) rotate(0deg); opacity: 1; }}
            100% {{ transform: translateY(80px) rotate(720deg); opacity: 0; }}
        }}

        .confetti-piece {{
            position: absolute;
            width: 6px;
            height: 6px;
            border-radius: 1px;
            animation: confetti-fall 3s ease-in-out infinite;
            opacity: 0.8;
        }}
    </style>
</head>
<body>
<div class="tv-rotate-wrapper" id="tvWrapper">

{ticker_html}

<div class="layout">

    <!-- Hero: Total MRR -->
    <div class="hero-card">
        <div class="hero-label">Total Team MRR &mdash; {current_month}</div>
        <div class="hero-value" style="color: var(--green);" data-countup-currency="{total_mrr:.2f}">{format_currency(total_mrr)}</div>
        <div class="hero-change">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
            <span data-countup-pct="{achieved_pct:.0f}">{achieved_pct:.0f}%</span><span> of target</span>
        </div>
    </div>

    <!-- Summary Strip — 4 tiles -->
    <div class="summary-grid">
        <div class="summary-tile">
            <div class="summary-tile-label">Target</div>
            <div class="summary-tile-value" style="color: var(--text-primary);" data-countup="{total_target:.2f}">{format_amount(total_target)}</div>
        </div>
        <div class="summary-tile">
            <div class="summary-tile-label">Achieved</div>
            <div class="summary-tile-value" style="color: {get_status_color(achieved_pct)};" data-countup-pct="{achieved_pct:.0f}">{achieved_pct:.0f}%</div>
        </div>
        <div class="summary-tile">
            <div class="summary-tile-label">On Track</div>
            <div class="summary-tile-value" style="color: {get_status_color((on_track / len(REPS)) * 100)};">{on_track}/{len(REPS)}</div>
        </div>
        <div class="summary-tile">
            <div class="summary-tile-label">Days Left</div>
            <div class="summary-tile-value" style="color: var(--clerk-orange);">{days_left}</div>
        </div>
    </div>

    <!-- Leaderboard — full width -->
    <div class="leaderboard-card">
        <div class="leaderboard-header">
            <div class="leaderboard-title">Monthly MRR Leaderboard</div>
            <select id="monthSelector" class="month-selector"></select>
        </div>

        <div class="leaderboard-list">
{leaderboard_html}
        </div>
    </div>

    <!-- Year Leaders — horizontal strip -->
    <div class="card" style="padding: 20px;">
        <div class="card-label">Year-to-Date Leaders</div>
        <div class="year-leaders">{year_leaders_html}
        </div>
    </div>

    <!-- Pace Indicator -->
    <div class="pace-indicator" style="text-align: center; padding: 14px 20px; border-radius: var(--radius-sm);">
        Team needs <strong>{format_currency(pace_per_day)}/day</strong> to hit target &nbsp;&middot;&nbsp; <strong>{days_left} days</strong> left in {month_names[today.month - 1]}
    </div>

    <!-- Footer -->
    <div class="footer">
        <div class="footer-left">
            <div class="live-indicator">
                <div class="live-dot"></div>
                Live
            </div>
            <span class="footer-divider">&middot;</span>
            <div class="clock" id="clock"></div>
        </div>
        <div class="footer-right">
            <span class="footer-timestamp">Last updated: {updated_time}</span> &nbsp;&middot;&nbsp; Data from Close CRM
        </div>
    </div>

</div>

<!-- Theme Toggle Button -->
<button class="theme-toggle" id="themeToggle" title="Toggle dark mode">
    <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
    <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
</button>

<script>
    // ═══════════════════════════════════════════════════════════════
    // EMBEDDED DATA — all YTD opportunities + rep config for JS
    // ═══════════════════════════════════════════════════════════════
    const ALL_OPPS = {all_ytd_opps_json};
    const REP_PHOTOS = {rep_photos_json};
    const REPS_CONFIG = {reps_config_json};
    const SHEET_TARGETS = {csv_targets_json};
    const CURRENT_YEAR = {today.year};
    const CURRENT_MONTH = {today.month};
    const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

    // ── Dark mode toggle ──
    const themeToggle = document.getElementById('themeToggle');
    // Default to dark mode for TV display
    const prefersLight = localStorage.getItem('clerk-dash-theme') === 'light';
    if (!prefersLight) {{
        document.body.classList.add('dark-mode');
    }}

    themeToggle.addEventListener('click', () => {{
        document.body.classList.toggle('dark-mode');
        const isDark = document.body.classList.contains('dark-mode');
        localStorage.setItem('clerk-dash-theme', isDark ? 'dark' : 'light');
    }});

    // ── Live clock ──
    function updateClock() {{
        const now = new Date();
        document.getElementById('clock').textContent = now.toLocaleTimeString('en-US', {{
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }});
    }}
    updateClock();
    setInterval(updateClock, 1000);

    // ── Utility functions ──
    function formatAmount(v) {{
        return v.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
    }}
    function formatCurrency(v) {{
        return 'DKK ' + formatAmount(v);
    }}
    function getStatusColor(pct) {{
        if (pct >= 100) return 'var(--green)';
        if (pct >= 50) return 'var(--yellow-dark)';
        return 'var(--red)';
    }}
    function calcMrr(opp) {{
        const value = (opp.value || 0) / 100;
        const period = opp.value_period || 'monthly';
        if (period === 'annual') return value / 12;
        return value;
    }}
    function getCloseDate(opp) {{
        return opp.close_date || opp.date_won || opp.close_at || '';
    }}

    // ── Populate month selector ──
    const selector = document.getElementById('monthSelector');
    const startYear = CURRENT_YEAR;
    // Show Jan of current year through current month
    for (let m = CURRENT_MONTH; m >= 1; m--) {{
        const opt = document.createElement('option');
        opt.value = startYear + '-' + String(m).padStart(2, '0');
        opt.textContent = MONTH_NAMES[m - 1] + ' ' + startYear;
        if (m === CURRENT_MONTH) opt.selected = true;
        selector.appendChild(opt);
    }}

    // ── Month switch logic ──
    selector.addEventListener('change', () => {{
        const [year, month] = selector.value.split('-').map(Number);
        renderMonth(year, month);
    }});

    function renderMonth(year, month) {{
        const monthStart = year + '-' + String(month).padStart(2, '0') + '-01';
        let monthEnd;
        if (month === 12) {{
            monthEnd = (year + 1) + '-01-01';
        }} else {{
            monthEnd = year + '-' + String(month + 1).padStart(2, '0') + '-01';
        }}

        // Filter opps for this month
        const monthOpps = ALL_OPPS.filter(opp => {{
            const cd = getCloseDate(opp).substring(0, 10);
            return cd >= monthStart && cd < monthEnd;
        }});

        // Aggregate by rep
        const repMrr = {{}};
        const repDeals = {{}};
        for (const opp of monthOpps) {{
            const uid = opp.user_id;
            if (!uid || !REPS_CONFIG[uid]) continue;
            repMrr[uid] = (repMrr[uid] || 0) + calcMrr(opp);
            repDeals[uid] = (repDeals[uid] || 0) + 1;
        }}

        // Build sorted rep data — use sheet targets if available, else fallback
        const monthKey = year + '-' + String(month).padStart(2, '0');
        const repData = Object.entries(REPS_CONFIG).map(([uid, rep]) => {{
            const sheetTarget = (SHEET_TARGETS[uid] && SHEET_TARGETS[uid][monthKey]) ? SHEET_TARGETS[uid][monthKey] : rep.target;
            const mrr = repMrr[uid] || 0;
            return {{
                uid,
                name: rep.name,
                initials: rep.initials,
                target: sheetTarget,
                mrr: mrr,
                pct: sheetTarget > 0 ? (mrr / sheetTarget * 100) : 0,
                deals: repDeals[uid] || 0
            }};
        }});
        repData.sort((a, b) => b.pct - a.pct);

        // ── Update hero card ──
        const totalMrr = repData.reduce((s, r) => s + r.mrr, 0);
        const totalTarget = repData.reduce((s, r) => s + r.target, 0);
        const achievedPct = totalTarget > 0 ? (totalMrr / totalTarget * 100) : 0;
        const onTrack = repData.filter(r => r.mrr >= r.target).length;

        document.querySelector('.hero-value').textContent = formatCurrency(totalMrr);
        document.querySelector('.hero-value').style.color = 'var(--green)';
        document.querySelector('.hero-change span').textContent = Math.round(achievedPct) + '%';

        // ── Update summary tiles ──
        const tiles = document.querySelectorAll('.summary-tile-value');
        tiles[0].textContent = formatAmount(totalTarget);
        tiles[1].textContent = Math.round(achievedPct) + '%';
        tiles[1].style.color = getStatusColor(achievedPct);
        tiles[2].textContent = onTrack + '/' + repData.length;
        tiles[2].style.color = getStatusColor((onTrack / repData.length) * 100);

        // ── Update countdown ──
        const isCurrentMonth = (year === CURRENT_YEAR && month === CURRENT_MONTH);
        const countdownCard = document.querySelector('.countdown-card');
        if (isCurrentMonth) {{
            const today = new Date();
            const daysInMonth = new Date(year, month, 0).getDate();
            const daysLeft = Math.max(daysInMonth - today.getDate(), 1);
            const remaining = Math.max(totalTarget - totalMrr, 0);
            const pacePerDay = remaining / daysLeft;
            countdownCard.querySelector('.countdown-number').textContent = daysLeft;
            countdownCard.querySelector('.countdown-label').innerHTML = '<strong>days left</strong><br>in ' + MONTH_NAMES[month - 1];
            countdownCard.querySelector('.pace-indicator').innerHTML = 'Team needs <strong>' + formatCurrency(pacePerDay) + '/day</strong> to hit target';
        }} else {{
            const gap = totalMrr - totalTarget;
            countdownCard.querySelector('.countdown-number').textContent = Math.round(achievedPct) + '%';
            countdownCard.querySelector('.countdown-label').innerHTML = '<strong>achieved</strong><br>in ' + MONTH_NAMES[month - 1];
            if (gap >= 0) {{
                countdownCard.querySelector('.pace-indicator').innerHTML = 'Team exceeded target by <strong>' + formatCurrency(gap) + '</strong>';
            }} else {{
                countdownCard.querySelector('.pace-indicator').innerHTML = 'Team was <strong>' + formatCurrency(Math.abs(gap)) + '</strong> short of target';
            }}
        }}

        // ── Update ticker ──
        const tickerEl = document.querySelector('.deal-ticker');
        if (tickerEl) {{
            // Get last 3 deals for this month
            const sorted = [...monthOpps].sort((a, b) => {{
                const da = (a.date_updated || a.date_created || getCloseDate(a));
                const db = (b.date_updated || b.date_created || getCloseDate(b));
                return db.localeCompare(da);
            }});
            const last3 = sorted.slice(0, 3);
            if (last3.length > 0) {{
                let items = '';
                for (const deal of last3) {{
                    const repName = REPS_CONFIG[deal.user_id] ? REPS_CONFIG[deal.user_id].name : 'Unknown';
                    const company = deal.lead_name || 'Unknown';
                    const value = calcMrr(deal);
                    items += '<div class="ticker-item">' +
                        '<span class="ticker-icon">&#127881;</span>' +
                        '<span class="ticker-rep">' + repName + '</span> closed ' +
                        '<span class="ticker-company">' + company + '</span> for ' +
                        '<span class="ticker-value">' + formatCurrency(value) + '</span>' +
                        '<span class="ticker-sep"></span></div>';
                }}
                tickerEl.querySelector('.ticker-track').innerHTML = items + items;
                tickerEl.style.display = 'flex';
            }} else {{
                tickerEl.style.display = 'none';
            }}
        }}

        // ── Rebuild leaderboard rows ──
        const listEl = document.querySelector('.leaderboard-list');
        listEl.innerHTML = '';
        repData.forEach((rep, i) => {{
            const rank = i + 1;
            const classes = ['lb-row'];
            if (rep.pct >= 100) classes.push('target-achieved');
            if (rep.pct < 50) classes.push('below-target');
            else if (rank <= 3) classes.push('top-3');
            if (rank > 5) classes.push('compact');

            const photoUri = REP_PHOTOS[rep.name] || '';
            const photoInner = photoUri
                ? '<img src="' + photoUri + '" alt="' + rep.name + '">'
                : '<span class="lb-photo-initials">' + rep.initials + '</span>';

            const crownHtml = rep.pct >= 100 ? '<span class="crown-emoji">&#128081;</span>' : '';

            // Rank badge class (gold/silver/bronze for top 3)
            let badgeClass = 'rank-badge';
            if (rank === 1) badgeClass += ' gold';
            else if (rank === 2) badgeClass += ' silver';
            else if (rank === 3) badgeClass += ' bronze';

            // Streak only shown for current month
            let streakHtml = '';
            // (streaks are real-time only, skip for historical)

            const displayPct = Math.min(rep.pct, 100);
            const isOver = rep.pct >= 100;
            const barContainerClass = isOver ? 'lb-bar-container over-target' : 'lb-bar-container';

            let shimmerClass = '';
            if (rep.pct >= 100) shimmerClass = ' shimmer-100';
            else if (rep.pct >= 75) shimmerClass = ' shimmer-75';
            else if (rep.pct >= 50) shimmerClass = ' shimmer-50';

            let barStyle;
            if (isOver) {{
                barStyle = 'width:100%;background:linear-gradient(90deg,#5CB854 0%,#1DB954 40%,#17a34a 100%);background-size:100% 100%;';
            }} else if (displayPct > 0) {{
                const bgSize = (100 / displayPct) * 100;
                barStyle = 'width:' + displayPct.toFixed(1) + '%;background-size:' + bgSize.toFixed(1) + '% 100%;';
            }} else {{
                barStyle = 'width:0%;';
            }}

            const pctColor = getStatusColor(rep.pct);

            const remaining = Math.max(rep.target - rep.mrr, 0);
            const isHit = rep.pct >= 100;
            const earnedDisplay = formatAmount(rep.mrr);
            const barEarnedClass = displayPct >= 35 ? 'bar-earned' : 'bar-earned outside';
            const countdownHtml = isHit
                ? '<div class="countdown-amount hit">&#10003; Target hit</div>'
                : '<div><span class="countdown-amount">' + formatAmount(remaining) + '</span><span class="countdown-arrow">&#8595;</span></div>';
            const pctArrowHtml = '<span class="pct-arrow" style="color:' + pctColor + ';">&#8593;</span>';

            const row = document.createElement('div');
            row.className = classes.join(' ');
            row.style.animationDelay = (0.05 * rank) + 's';
            row.innerHTML =
                '<div class="photo-rank-wrap">' + crownHtml + '<div class="lb-photo">' + photoInner + '</div><div class="' + badgeClass + '">' + rank + '</div></div>' +
                '<div class="lb-info"><div class="lb-name-row"><span class="lb-name">' + rep.name + '</span>' + streakHtml + '</div>' +
                '<div class="' + barContainerClass + '"><div class="lb-bar-fill' + shimmerClass + '" style="' + barStyle + '"><span class="' + barEarnedClass + '">' + earnedDisplay + ' DKK</span></div></div></div>' +
                '<div class="lb-countdown">' + countdownHtml + '</div>' +
                '<div class="lb-pct"><div><span class="lb-pct-value" style="color:' + pctColor + ';">' + Math.round(rep.pct) + '%</span>' + pctArrowHtml + '</div><div class="lb-pct-sub">' + formatAmount(rep.target) + '</div></div>';
            listEl.appendChild(row);

            // Add confetti for achieved rows
            if (rep.pct >= 100) {{
                row.style.position = 'relative';
                row.style.overflow = 'hidden';
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

    // ── Count-up animations (initial load only) ──
    function animateCountUp(el, target, suffix, prefix, duration) {{
        const start = 0;
        const startTime = performance.now();

        function update(currentTime) {{
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = start + (target - start) * eased;

            if (prefix) {{
                el.textContent = prefix + current.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            }} else if (suffix) {{
                el.textContent = Math.round(current) + suffix;
            }} else {{
                el.textContent = current.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            }}

            if (progress < 1) {{
                requestAnimationFrame(update);
            }}
        }}
        requestAnimationFrame(update);
    }}

    document.querySelectorAll('[data-countup]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup'));
        animateCountUp(el, target, '', '', 1500);
    }});
    document.querySelectorAll('[data-countup-pct]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup-pct'));
        animateCountUp(el, target, '%', '', 1500);
    }});
    document.querySelectorAll('[data-countup-currency]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup-currency'));
        animateCountUp(el, target, '', 'DKK ', 1800);
    }});

    // ── Confetti burst for initial load ──
    document.querySelectorAll('.lb-row.target-achieved').forEach(row => {{
        row.style.position = 'relative';
        row.style.overflow = 'hidden';
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

    // ── TV MODE: add ?tv=cw or ?tv=ccw to URL for rotated TV display ──
    (function() {{
        var params = new URLSearchParams(window.location.search);
        var tvMode = params.get('tv');
        if (!tvMode) return; // No param = normal desktop view

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
            w.style.minHeight = '1920px';
            w.style.overflow = 'hidden';
            w.style.transformOrigin = 'top left';
            if (tvMode === 'ccw') {{
                w.style.transform = 'translateY(' + vh + 'px) rotate(-90deg) scale(' + s + ')';
            }} else {{
                w.style.transform = 'translateX(' + vw + 'px) rotate(90deg) scale(' + s + ')';
            }}
            console.log('TV mode=' + tvMode + ': ' + vw + 'x' + vh + ', scale=' + s.toFixed(3));
        }}
        setupTV();
        window.addEventListener('resize', setupTV);

        // Fullscreen management — hides TV browser toolbar/sidebar
        var wantFS = true;
        function goFS() {{
            var el = document.documentElement;
            var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
            if (fn) fn.call(el).catch(function(){{}});
        }}
        // Try fullscreen immediately on load
        goFS();
        // Also on any tap
        document.addEventListener('click', goFS);
        // Re-enter if dropped
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
</html>'''

    return html


def main():
    """Main entry point."""
    run_once = '--once' in sys.argv

    try:
        while True:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching opportunities from Close...")

            # Load targets from local CSV
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Loading targets from targets.csv...")
            csv_targets = load_targets_from_csv()  # {user_id: {YYYY-MM: target}}
            if csv_targets:
                print(f"  Loaded targets for {len(csv_targets)} reps from targets.csv")
            else:
                print(f"  ⚠ targets.csv empty or missing, using hardcoded fallback targets")

            # Fetch all won opportunities (Closed Won + Cross-Sell Won)
            all_opps = fetch_won_opportunities()
            print(f"  Fetched {len(all_opps)} total won opportunities")
            # Log breakdown by status for debugging
            status_counts = {}
            for opp in all_opps:
                sl = opp.get('status_label', opp.get('status_id', 'unknown'))
                status_counts[sl] = status_counts.get(sl, 0) + 1
            for sl, cnt in status_counts.items():
                print(f"    {sl}: {cnt} opps")

            # Calculate date bounds (include the FULL month and FULL year,
            # not just up to today — deals can have future close dates)
            today = datetime.now(CPH_TZ).date()
            current_month_key = f"{today.year}-{today.month:02d}"
            month_start = f"{today.year}-{today.month:02d}-01"
            # Next month start (handles December → January rollover)
            if today.month == 12:
                month_end = f"{today.year + 1}-01-01"
            else:
                month_end = f"{today.year}-{today.month + 1:02d}-01"
            year_start = f"{today.year}-01-01"
            year_end = f"{today.year + 1}-01-01"

            # Streak: deals actually won in the last 5 days (by updated_at, not close_at)
            five_days_ago = (today - timedelta(days=5)).isoformat()
            tomorrow = (today + timedelta(days=1)).isoformat()
            streak_counts = count_recent_deals_by_rep(all_opps, five_days_ago, tomorrow)

            # Filter by date
            monthly_opps = filter_by_date_range(all_opps, month_start, month_end)
            ytd_opps = filter_by_date_range(all_opps, year_start, year_end)
            print(f"  Monthly: {len(monthly_opps)} opps, YTD: {len(ytd_opps)} opps")

            # Override current month targets from the sheet (if available)
            for uid in REPS:
                if uid in csv_targets and current_month_key in csv_targets[uid]:
                    REPS[uid]['target'] = csv_targets[uid][current_month_key]

            # Aggregate by rep
            monthly_mrr = aggregate_by_rep(monthly_opps)
            ytd_mrr = aggregate_by_rep(ytd_opps)

            # Recent deals (last 3 for the scrolling ticker)
            recent_deals = get_recent_deals(monthly_opps, count=3)
            recent_deals_info = []
            for deal in recent_deals:
                d_user_id = deal.get('user_id', '')
                d_rep_name = REPS.get(d_user_id, {}).get('name', 'Unknown')
                d_lead_name = deal.get('lead_name', 'Unknown')
                d_value = calculate_mrr(deal)
                recent_deals_info.append({
                    'rep_name': d_rep_name,
                    'lead_name': d_lead_name,
                    'value': d_value,
                })

            # Prepare JSON data for client-side month switching
            # Only include fields the JS needs to keep the HTML size reasonable
            ytd_opps_slim = []
            for opp in ytd_opps:
                ytd_opps_slim.append({
                    'user_id': opp.get('user_id', ''),
                    'value': opp.get('value', 0) or 0,
                    'value_period': opp.get('value_period', 'monthly'),
                    'close_date': get_close_date(opp) or '',
                    'lead_name': opp.get('lead_name', 'Unknown'),
                    'date_updated': opp.get('date_updated', ''),
                    'date_created': opp.get('date_created', ''),
                })
            all_ytd_opps_json = json.dumps(ytd_opps_slim)

            # Photo URIs keyed by rep name
            rep_photos = {}
            for uid, rep in REPS.items():
                photo_uri = get_photo_data_uri(rep['name'])
                if photo_uri:
                    rep_photos[rep['name']] = photo_uri
            rep_photos_json = json.dumps(rep_photos)

            # Prepare sheet targets JSON for JS month switching
            # Format: {user_id: {YYYY-MM: target}} — JS uses this to look up
            # the correct target when the user switches months
            csv_targets_json = json.dumps(csv_targets)

            # Log totals
            total = sum(monthly_mrr.get(uid, 0) for uid in REPS)
            print(f"  Total monthly MRR: DKK {total:,.2f}")

            # Generate HTML
            html = generate_html(monthly_mrr, ytd_mrr, monthly_opps, streak_counts, recent_deals_info, all_ytd_opps_json, rep_photos_json, csv_targets_json)

            # Write to file
            output_path = SCRIPT_DIR / "clerk-mrr-dashboard-live.html"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"  Dashboard written to: {output_path}")

            if run_once:
                print("Done (--once mode).")
                break

            print("  Next refresh in 5 minutes...")
            time.sleep(300)

    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
