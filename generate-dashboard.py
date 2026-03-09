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
import base64
import urllib.request
import urllib.error
import sys
import os
import time
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
CLOSE_API_BASE = "https://api.close.com/api/v1"
CLOSE_API_KEY = os.environ.get("CLOSE_API_KEY", "")
WON_STATUS_ID = "stat_IyAn2lpFlElQQjqLVGs9Pc1TfeJqTJaN3ZX0L147a61"
PIPELINE_ID = "pipe_4r3PtlYGyS8nyD57HXlyyQ"

REPS = {
    'user_yBw9tNt4WNDf34dsPFG48SpvefoK7A8zPMjfU4K4DYM': {'name': 'Robert Bengtsson', 'initials': 'RB', 'target': 13182},
    'user_7bbV5f2geHD1hLDw54p9Vr088T3yW6TSBLUs8JAMEzV': {'name': 'Peter Rossé', 'initials': 'PR', 'target': 12273},
    'user_O0GV7AdCKCB5bOrK89NeJYyNoPYpcLjJCCUHinDgoLR': {'name': 'Anders Hildan', 'initials': 'AH', 'target': 16500},
    'user_guKLcbLohZnYhgae5FGvEK6f9ay5fTsAvOnfq6pq3gn': {'name': 'Braxton Phillips', 'initials': 'BP', 'target': 16500},
    'user_5Mkg13Ge14LxiplY5t8phIud1vfqxkVe6su6RF4IJRh': {'name': 'Arnab Deb', 'initials': 'AD', 'target': 5000},
    'user_YJuiXnlZrSDAeBGXHL7ehssMRWzxlH86jtXr7NExbss': {'name': 'Alexander Alken', 'initials': 'AA', 'target': 10500},
    'user_rgafRJqGdOmQVhsZx3fh8PcL12ASTMFm9asWvHpfDs2': {'name': 'Alexandra Beikerts', 'initials': 'AB', 'target': 10500},
    'user_SAZq4wEnfq5ILVTsn0ftwUOk2B3buDEoboxWigYg0ku': {'name': 'Daniela Drobna', 'initials': 'DD', 'target': 10500},
    'user_sVcAJW2NzbU6ZlfVrX4zqUp78rbJXQEyGq7tmFugyHY': {'name': 'Christian Antoniu', 'initials': 'CA', 'target': 7989},
    'user_nwSw0RV3curn6amDVD8qbiYkB02K3D7a2PN7CBZlZPa': {'name': 'Alessio Catania', 'initials': 'AC', 'target': 9250},
    'user_5pIrGaTwAhuFiCpleT0rdfI86E2HoOra853wfUuJmRx': {'name': 'Maja Krokowska', 'initials': 'MK', 'target': 5000},
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
    """Fetch all won opportunities from Close API with pagination."""
    opportunities = []
    skip = 0
    limit = 100

    while True:
        params = {
            'status_id': WON_STATUS_ID,
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
            print(f"Error fetching opportunities: {e}")
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


def count_deals_by_rep(opps):
    """Count number of deals per rep."""
    counts = {}
    for opp in opps:
        user_id = opp.get('user_id')
        if not user_id or user_id not in REPS:
            continue
        counts[user_id] = counts.get(user_id, 0) + 1
    return counts


def get_last_deal(opps):
    """Get the most recently closed deal from the list of opportunities."""
    best = None
    best_date = ''
    for opp in opps:
        close_date = get_close_date(opp)
        if not close_date:
            continue
        # Also check date_updated or date_created for more precise ordering
        updated = opp.get('date_updated', '') or opp.get('date_created', '') or close_date
        if updated > best_date:
            best_date = updated
            best = opp
    return best


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


def generate_html(monthly_mrr, ytd_mrr, monthly_opps, streak_counts, last_deal_info):
    """Generate the complete dashboard HTML with all CSS and data."""
    today = date.today()
    now = datetime.now()
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

    # ── Last deal info ──
    last_deal_html = ''
    if last_deal_info:
        ld_rep = last_deal_info.get('rep_name', 'Unknown')
        ld_company = last_deal_info.get('lead_name', 'Unknown')
        ld_value = last_deal_info.get('value', 0)
        last_deal_html = f'''
    <div class="deal-ticker">
        <div class="deal-ticker-inner">
            <div class="deal-ticker-icon">&#127881;</div>
            <div class="deal-ticker-text">
                <span class="deal-ticker-label">LATEST WIN</span>
                <span class="deal-ticker-rep">{ld_rep}</span> closed
                <span class="deal-ticker-company">{ld_company}</span>
                for <span class="deal-ticker-value">{format_currency(ld_value)}</span>
            </div>
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

        row = f'''            <div class="{' '.join(classes)}">
                <div class="lb-rank">{rank}</div>
                <div class="lb-photo-wrapper">
                    <div class="lb-photo">{photo_inner}</div>
                    {crown_html}
                </div>
                <div class="lb-info">
                    <div class="lb-name-row">
                        <span class="lb-name">{rep['name']}</span>
                        {streak_html}
                    </div>
                    <div class="{bar_container_class}">
                        <div class="lb-bar-fill{shimmer_class}" style="{bar_style}"></div>
                    </div>
                </div>
                <div class="lb-mrr">
                    <div class="lb-mrr-amount" data-countup="{rep['mrr']:.2f}">{format_amount(rep['mrr'])}</div>
                    <div class="lb-mrr-target">of {format_amount(rep['target'])}</div>
                </div>
                <div class="lb-pct">
                    <div class="lb-pct-value" style="color: {pct_color};" data-countup-pct="{rep['pct']:.0f}">{rep['pct']:.0f}%</div>
                    <div class="lb-pct-label">Target</div>
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

        body {{
            font-family: 'Poppins', sans-serif;
            background: var(--bg);
            min-height: 100vh;
            color: var(--text-primary);
            padding: 24px 40px;
            transition: background 0.4s ease, color 0.3s ease;
        }}

        /* ═══════════════════════════════════════════
           DEAL TICKER — slides in from right
           ═══════════════════════════════════════════ */
        .deal-ticker {{
            background: linear-gradient(135deg, var(--green-bg), var(--surface));
            border: 2px solid var(--green);
            border-radius: var(--radius-md);
            padding: 14px 24px;
            margin-bottom: 20px;
            overflow: hidden;
            animation: tickerSlideIn 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94) both;
        }}

        @keyframes tickerSlideIn {{
            from {{ opacity: 0; transform: translateX(100px); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}

        .deal-ticker-inner {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .deal-ticker-icon {{
            font-size: 28px;
            animation: tickerBounce 2s ease-in-out infinite;
        }}

        @keyframes tickerBounce {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.2); }}
        }}

        .deal-ticker-text {{
            font-size: 15px;
            font-weight: 500;
            color: var(--text-primary);
        }}

        .deal-ticker-label {{
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
            color: var(--green);
            background: var(--green-bg);
            padding: 3px 10px;
            border-radius: 4px;
            margin-right: 10px;
            vertical-align: middle;
        }}

        .deal-ticker-rep {{
            font-weight: 700;
            color: var(--clerk-orange);
        }}

        .deal-ticker-company {{
            font-weight: 700;
            color: var(--text-primary);
        }}

        .deal-ticker-value {{
            font-weight: 800;
            color: var(--green);
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

        /* Layout */
        .layout {{
            display: grid;
            grid-template-columns: 380px 1fr;
            gap: 28px;
        }}

        /* Left Panel */
        .panel-left {{
            display: flex;
            flex-direction: column;
            gap: 20px;
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
            font-size: 52px;
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

        /* Summary Grid */
        .summary-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
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

        /* Year Leaders */
        .year-leaders {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}

        .year-leader {{
            display: grid;
            grid-template-columns: 44px 1fr auto;
            gap: 14px;
            align-items: center;
            background: var(--surface-raised);
            padding: 20px 22px;
            border-radius: var(--radius-lg);
            border: 2px solid var(--clerk-orange);
            box-shadow: var(--shadow-sm);
            transition: box-shadow 0.2s ease;
        }}

        .year-leader:hover {{
            box-shadow: var(--shadow-md);
        }}

        .year-leader-rank {{
            font-size: 30px;
            text-align: center;
            line-height: 1;
        }}

        .year-leader-name {{
            font-size: 17px;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .year-leader-amount {{
            font-size: 22px;
            font-weight: 700;
            color: var(--green);
        }}

        /* Right Panel: Leaderboard */
        .panel-right {{
            display: flex;
            flex-direction: column;
        }}

        .leaderboard-card {{
            background: var(--surface);
            border-radius: var(--radius-xl);
            padding: 28px 32px;
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
            grid-template-columns: 56px 56px 1fr 120px 100px;
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

        .lb-row.top-3 .lb-mrr-amount {{
            font-size: 24px;
        }}

        .lb-row.top-3 .lb-pct-value {{
            font-size: 26px;
        }}

        .lb-row.top-3 .lb-photo {{
            width: 50px;
            height: 50px;
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

        .lb-row.compact .lb-mrr-amount {{
            font-size: 18px;
        }}

        .lb-row.compact .lb-pct-value {{
            font-size: 20px;
        }}

        .lb-row.compact .lb-photo {{
            width: 36px;
            height: 36px;
        }}

        .lb-row.compact .lb-rank {{
            width: 36px;
            height: 36px;
            font-size: 14px;
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

        /* Photo wrapper for crown positioning */
        .lb-photo-wrapper {{
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .crown-emoji {{
            position: absolute;
            top: -10px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 18px;
            z-index: 2;
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

        /* Rep photo */
        .lb-photo {{
            width: 44px;
            height: 44px;
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
            font-size: 14px;
            font-weight: 700;
            color: var(--text-tertiary);
            letter-spacing: -0.5px;
        }}

        .lb-row:hover {{
            box-shadow: var(--shadow-md);
            transform: translateX(4px);
        }}

        .lb-row.below-target {{
            border-left-color: var(--red);
            opacity: 0.7;
        }}

        .lb-rank {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            border-radius: var(--radius-sm);
            font-size: 18px;
            font-weight: 700;
            color: var(--clerk-orange);
            background: var(--clerk-orange-bg);
        }}

        /* Top 3 metallic rank badges */
        .lb-row.top-3:nth-child(1) .lb-rank {{
            background: linear-gradient(145deg, #FFD700, #FFC107, #FFB300);
            color: #5C3D00;
            border: 2px solid #FFD700;
            box-shadow: 0 0 12px rgba(255, 215, 0, 0.5), 0 0 24px rgba(255, 215, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.4);
            font-size: 20px;
        }}

        .lb-row.top-3:nth-child(2) .lb-rank {{
            background: linear-gradient(145deg, #E8E8E8, #C0C0C0, #A8A8A8);
            color: #3a3a3a;
            border: 2px solid #C0C0C0;
            box-shadow: 0 0 12px rgba(192, 192, 192, 0.5), 0 0 24px rgba(192, 192, 192, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.6);
            font-size: 20px;
        }}

        .lb-row.top-3:nth-child(3) .lb-rank {{
            background: linear-gradient(145deg, #E08A4A, #CD7F32, #B8702D);
            color: #3D2200;
            border: 2px solid #CD7F32;
            box-shadow: 0 0 12px rgba(205, 127, 50, 0.5), 0 0 24px rgba(205, 127, 50, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.3);
            font-size: 20px;
        }}

        .lb-row.below-target .lb-rank {{
            color: var(--red);
            background: var(--red-bg);
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

        .lb-mrr {{
            text-align: right;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .lb-mrr-amount {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }}

        .lb-mrr-target {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-tertiary);
        }}

        .lb-pct {{
            text-align: right;
        }}

        .lb-pct-value {{
            font-size: 24px;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.5px;
        }}

        .lb-pct-label {{
            font-size: 10px;
            font-weight: 500;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
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

{last_deal_html}

<div class="layout">
    <!-- Left Panel -->
    <div class="panel-left">

        <!-- Hero: Total MRR -->
        <div class="hero-card">
            <div class="hero-label">Total Team MRR</div>
            <div class="hero-value" style="color: var(--green);" data-countup-currency="{total_mrr:.2f}">{format_currency(total_mrr)}</div>
            <div class="hero-change">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                <span data-countup-pct="{achieved_pct:.0f}">{achieved_pct:.0f}%</span><span> of target</span>
            </div>
        </div>

        <!-- Summary Tiles -->
        <div class="card" style="padding: 20px;">
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
            </div>
        </div>

        <!-- Days Left Countdown -->
        <div class="countdown-card">
            <div class="countdown-row">
                <div class="countdown-number">{days_left}</div>
                <div class="countdown-label">
                    <strong>days left</strong><br>
                    in {month_names[today.month - 1]}
                </div>
            </div>
            <div class="pace-indicator">
                Team needs <strong>{format_currency(pace_per_day)}/day</strong> to hit target
            </div>
        </div>

        <!-- Year Leaders -->
        <div class="card">
            <div class="card-label">Year-to-Date Leaders</div>
            <div class="year-leaders">{year_leaders_html}
            </div>
        </div>

    </div>

    <!-- Right Panel: Leaderboard -->
    <div class="panel-right">
        <div class="leaderboard-card">
            <div class="leaderboard-header">
                <div class="leaderboard-title">Monthly MRR Leaderboard</div>
                <div class="leaderboard-month">{current_month}</div>
            </div>

            <div class="leaderboard-list">
{leaderboard_html}
            </div>
        </div>
    </div>
</div>

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
    // ── Dark mode toggle ──
    const themeToggle = document.getElementById('themeToggle');
    const prefersDark = localStorage.getItem('clerk-dash-theme') === 'dark';
    if (prefersDark) {{
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

    // ── Count-up animations ──
    function animateCountUp(el, target, suffix, prefix, duration) {{
        const start = 0;
        const startTime = performance.now();

        function update(currentTime) {{
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
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

    // Animate all data-countup elements
    document.querySelectorAll('[data-countup]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup'));
        animateCountUp(el, target, '', '', 1500);
    }});

    // Animate percentage elements
    document.querySelectorAll('[data-countup-pct]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup-pct'));
        animateCountUp(el, target, '%', '', 1500);
    }});

    // Animate currency elements
    document.querySelectorAll('[data-countup-currency]').forEach(el => {{
        const target = parseFloat(el.getAttribute('data-countup-currency'));
        animateCountUp(el, target, '', 'DKK ', 1800);
    }});

    // ── Confetti burst for target achievers ──
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
</script>

</body>
</html>'''

    return html


def main():
    """Main entry point."""
    run_once = '--once' in sys.argv

    try:
        while True:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching opportunities from Close...")

            # Fetch all won opportunities
            all_opps = fetch_won_opportunities()
            print(f"  Fetched {len(all_opps)} total won opportunities")

            # Calculate date bounds (include the FULL month and FULL year,
            # not just up to today — deals can have future close dates)
            today = date.today()
            month_start = f"{today.year}-{today.month:02d}-01"
            # Next month start (handles December → January rollover)
            if today.month == 12:
                month_end = f"{today.year + 1}-01-01"
            else:
                month_end = f"{today.year}-{today.month + 1:02d}-01"
            year_start = f"{today.year}-01-01"
            year_end = f"{today.year + 1}-01-01"

            # Streak: deals in the last 5 days
            five_days_ago = (today - timedelta(days=5)).isoformat()
            tomorrow = (today + timedelta(days=1)).isoformat()
            recent_opps = filter_by_date_range(all_opps, five_days_ago, tomorrow)
            streak_counts = count_deals_by_rep(recent_opps)

            # Filter by date
            monthly_opps = filter_by_date_range(all_opps, month_start, month_end)
            ytd_opps = filter_by_date_range(all_opps, year_start, year_end)
            print(f"  Monthly: {len(monthly_opps)} opps, YTD: {len(ytd_opps)} opps")

            # Aggregate by rep
            monthly_mrr = aggregate_by_rep(monthly_opps)
            ytd_mrr = aggregate_by_rep(ytd_opps)

            # Last deal closed (most recent in current month)
            last_deal = get_last_deal(monthly_opps)
            last_deal_info = None
            if last_deal:
                ld_user_id = last_deal.get('user_id', '')
                ld_rep_name = REPS.get(ld_user_id, {}).get('name', 'Unknown')
                ld_lead_name = last_deal.get('lead_name', 'Unknown')
                ld_value = calculate_mrr(last_deal)
                last_deal_info = {
                    'rep_name': ld_rep_name,
                    'lead_name': ld_lead_name,
                    'value': ld_value,
                }

            # Log totals
            total = sum(monthly_mrr.get(uid, 0) for uid in REPS)
            print(f"  Total monthly MRR: DKK {total:,.2f}")

            # Generate HTML
            html = generate_html(monthly_mrr, ytd_mrr, monthly_opps, streak_counts, last_deal_info)

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
