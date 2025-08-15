# app.py

import os
import pandas as pd
import sqlite3
import json
import re
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, redirect, url_for
from PIL import Image
from fpdf import FPDF
import io
import time
import base64
import numpy as np
from collections import defaultdict
from fpdf.enums import XPos, YPos

# Custom FPDF Class for Branded Header
class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 10)
        self.cell(0, 5, 'Quantway Consulting LLP', 0, 1, 'L')
        self.set_font('helvetica', '', 8)
        self.set_text_color(40, 112, 184)
        self.cell(0, 5, 'https://quantwayconsulting.com', 0, 1, 'L', link='https://quantwayconsulting.com')
        self.set_text_color(0, 0, 0)
        self.ln(5)

# App Setup
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'backtests.db')
DATA_DIR = os.path.join(BASE_DIR, 'data')
STOCK_LIST_FILE = os.path.join(BASE_DIR, 'StockList.csv')

def init_db():
    with app.app_context():
        db = sqlite3.connect(DATABASE); cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, test_type TEXT NOT NULL,
                test_name TEXT NOT NULL DEFAULT 'Untitled', pattern TEXT NOT NULL, parameters TEXT, 
                results TEXT NOT NULL, notes TEXT, share_uuid TEXT UNIQUE
            )''')
        cursor.execute("PRAGMA table_info(backtests)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        if 'notes' not in existing_columns: cursor.execute("ALTER TABLE backtests ADD COLUMN notes TEXT")
        if 'share_uuid' not in existing_columns: cursor.execute("ALTER TABLE backtests ADD COLUMN share_uuid TEXT UNIQUE")
        db.commit(); db.close()

# CORE LOGIC FUNCTIONS
def calculate_camarilla(df):
    pivots = {}; p = (df['high'] + df['low'] + df['close']) / 3; pivots['P'] = p; range_val = df['high'] - df['low']
    pivots['R1'] = df['close'] + 1.1 * range_val / 12; pivots['S1'] = df['close'] - 1.1 * range_val / 12; pivots['R2'] = df['close'] + 1.1 * range_val / 6; pivots['S2'] = df['close'] - 1.1 * range_val / 6; pivots['R3'] = df['close'] + 1.1 * range_val / 4; pivots['S3'] = df['close'] - 1.1 * range_val / 4; pivots['R4'] = df['close'] + 1.1 * range_val / 2; pivots['S4'] = df['close'] - 1.1 * range_val / 2; pivots['R5'] = (df['high'] / df['low']) * df['close'] if df['low'] > 0 else df['close']; pivots['S5'] = df['close'] - (pivots['R5'] - df['close'])
    return pd.Series(pivots)
def parse_advanced_pattern(pattern_text):
    condition_pattern = re.compile(r"(High|Low)\s+(touched|above|below)\s+(R[1-5]|S[1-5]|P)", re.IGNORECASE); monthly_parts = [p.strip() for p in pattern_text.split(';') if p.strip()]; parsed_structure = []
    for part in monthly_parts:
        if ':' not in part: raise ValueError(f"Invalid month definition. Missing ':' in '{part}'")
        month_def, conditions_str = part.split(':', 1); month_offset_match = re.search(r"Month\s+(-?\d+)", month_def, re.IGNORECASE)
        if not month_offset_match: raise ValueError(f"Could not parse month offset from '{month_def}'")
        offset = int(month_offset_match.group(1)); conditions_list_str = [c.strip() for c in conditions_str.split(' and ')]
        month_conditions = []
        for cond_str in conditions_list_str:
            match = condition_pattern.match(cond_str)
            if not match: raise ValueError(f"Invalid condition format: '{cond_str}'")
            month_conditions.append({'price_point': match.group(1).lower(), 'operator': match.group(2).lower(), 'pivot': match.group(3).upper()})
        parsed_structure.append({'offset': offset, 'conditions': month_conditions})
    parsed_structure.sort(key=lambda x: x['offset']); return parsed_structure
def evaluate_condition(row, condition):
    price = row[condition['price_point']]; pivot_value = row[condition['pivot']]; op = condition['operator']
    if pd.isna(pivot_value): return False
    if op == 'touched': return price >= pivot_value if condition['price_point'] == 'high' else price <= pivot_value
    elif op == 'above': return price > pivot_value
    elif op == 'below': return price < pivot_value
    return False

def get_zone_name(price, pivots):
    p = pivots
    if not p or not isinstance(p, dict): return "Invalid Pivots"
    levels = sorted([(k, v) for k, v in p.items() if k.startswith(('R', 'S', 'P')) and pd.notna(v)], 
                    key=lambda item: item[1], reverse=True)
    if not levels: return "No Pivots"
    if price > levels[0][1]: return f"Above {levels[0][0]}"
    for i in range(len(levels) - 1):
        if levels[i+1][1] < price <= levels[i][1]:
            return f"{levels[i+1][0]}-{levels[i][0]} Zone"
    if price <= levels[-1][1]: return f"Below {levels[-1][0]}"
    return "Unknown Zone"

def get_detailed_outcome(daily_df_outcome, pivots):
    if daily_df_outcome.empty: return []
    first_week_df = daily_df_outcome.head(5)
    last_week_df = daily_df_outcome.tail(5)
    if first_week_df.empty or last_week_df.empty: return []
    avg_close_first_week = first_week_df['close'].mean()
    avg_close_last_week = last_week_df['close'].mean()
    start_zone = get_zone_name(avg_close_first_week, pivots)
    end_zone = get_zone_name(avg_close_last_week, pivots)
    outcomes = {f"Ends in {end_zone}"}
    if "Unknown" not in start_zone and "Unknown" not in end_zone and "Invalid" not in start_zone:
        if start_zone != end_zone: outcomes.add(f"{start_zone} -> {end_zone}")
        else: outcomes.add(f"Stays in {start_zone}")
    return list(outcomes)
    
def run_analysis(ticker, start_date, end_date, parsed_pattern):
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path): return []
    df = pd.read_csv(file_path, on_bad_lines='skip'); df.columns = [col.lower() for col in df.columns]; 
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True, errors='coerce').dt.tz_convert('Asia/Kolkata')
    df.dropna(subset=['datetime'], inplace=True); df.set_index('datetime', inplace=True)
    start_date_aware = pd.Timestamp(start_date, tz='Asia/Kolkata')
    end_date_aware = pd.Timestamp(end_date, tz='Asia/Kolkata')
    df_filtered = df.loc[start_date_aware:end_date_aware]
    if df_filtered.empty: return []
    monthly_df = df_filtered.resample('MS').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    if len(monthly_df) < 2: return []
    pivots_df = monthly_df.shift(1).apply(calculate_camarilla, axis=1)
    combined_df = monthly_df.join(pivots_df.add_prefix('p_'))
    matches = []
    max_offset = max(p['offset'] for p in parsed_pattern) if parsed_pattern else 0
    min_offset = min(p['offset'] for p in parsed_pattern) if parsed_pattern else 0
    start_index = -min_offset if min_offset < 0 else 0
    end_index = len(combined_df) - (max_offset + 1)
    for i in range(start_index, end_index):
        pattern_match_found = True
        for p in parsed_pattern:
            offset_index = i + p['offset']
            if not (0 <= offset_index < len(combined_df)):
                pattern_match_found = False; break
            target_month_row = combined_df.iloc[offset_index]
            context_for_eval = {
                'high': target_month_row['high'], 'low': target_month_row['low'],
                'R1': target_month_row['p_R1'], 'R2': target_month_row['p_R2'], 'R3': target_month_row['p_R3'],
                'R4': target_month_row['p_R4'], 'R5': target_month_row['p_R5'], 'P': target_month_row['p_P'],
                'S1': target_month_row['p_S1'], 'S2': target_month_row['p_S2'], 'S3': target_month_row['p_S3'],
                'S4': target_month_row['p_S4'], 'S5': target_month_row['p_S5']
            }
            if not all(evaluate_condition(context_for_eval, c) for c in p['conditions']):
                pattern_match_found = False; break
        if pattern_match_found:
            outcome_index = i + max_offset + 1
            if outcome_index < len(combined_df):
                outcome_month_start = combined_df.index[outcome_index]
                outcome_month_end = outcome_month_start + pd.offsets.MonthEnd(0)
                daily_df_outcome = df_filtered.loc[outcome_month_start:outcome_month_end]
                if daily_df_outcome.empty: continue
                pivots_for_outcome = combined_df.iloc[outcome_index - 1].to_dict()
                pivots_renamed = {k.replace('p_', ''):v for k,v in pivots_for_outcome.items() if k.startswith('p_')}
                outcomes = get_detailed_outcome(daily_df_outcome, pivots_renamed)
                if not outcomes: continue
                match_data = {"premise_date": combined_df.index[i + max_offset].strftime('%Y-%m-%d'), "outcome_date": outcome_month_start.strftime('%Y-%m-%d'), "outcomes": outcomes}
                matches.append(match_data)
    return matches

def get_histogram_data(probabilities):
    if not probabilities or len(probabilities) < 2: return None
    values = np.array([p['probability'] for p in probabilities])
    if np.std(values) < 0.01: return None
    counts, bin_edges = np.histogram(values, bins=10, range=(0, 100))
    return {'counts': counts.tolist(), 'bin_edges': bin_edges.tolist()}

def process_and_package_results(historical_matches, test_type, ticker=None):
    if not historical_matches: return None
    
    # --- Overall Probabilities ---
    all_outcomes_flat = [outcome for match in historical_matches for outcome in match['outcomes']]
    total_matches_all = len(historical_matches)
    counts_all = pd.Series(all_outcomes_flat).value_counts()
    probs_all = [{"state": state, "probability": round((count / total_matches_all) * 100, 2)} for state, count in counts_all.items()] if total_matches_all > 0 else []
    
    # --- Singular Probabilities ---
    singular_matches = [m['outcomes'] for m in historical_matches if not any('->' in o for o in m['outcomes'])]
    total_matches_singular = len(singular_matches)
    singular_outcomes_flat = [o for sublist in singular_matches for o in sublist]
    probs_singular = []
    if singular_outcomes_flat and total_matches_singular > 0:
        counts_singular = pd.Series(singular_outcomes_flat).value_counts()
        probs_singular = [{"state": state, "probability": round((count / total_matches_singular) * 100, 2)} for state, count in counts_singular.items()]
    
    # --- Path Probabilities ---
    path_matches = [m['outcomes'] for m in historical_matches if any('->' in o for o in m['outcomes'])]
    total_matches_path = len(path_matches)
    path_outcomes_flat = [o for sublist in path_matches for o in sublist if '->' in o]
    probs_path = []
    if path_outcomes_flat and total_matches_path > 0:
        counts_path = pd.Series(path_outcomes_flat).value_counts()
        probs_path = [{"state": state, "probability": round((count / total_matches_path) * 100, 2)} for state, count in counts_path.items()]
    
    # --- NEW: Conditional Probabilities by Starting Zone ---
    probs_by_start_zone = defaultdict(lambda: defaultdict(int))
    total_by_start_zone = defaultdict(int)
    for match in path_matches:
        for outcome in match:
            if '->' in outcome:
                start_zone, end_zone = [p.strip() for p in outcome.split('->')]
                probs_by_start_zone[start_zone][end_zone] += 1
                total_by_start_zone[start_zone] += 1
    
    final_probs_by_start_zone = {}
    for start_zone, end_zones in probs_by_start_zone.items():
        total = total_by_start_zone[start_zone]
        final_probs_by_start_zone[start_zone] = [
            {"state": end_zone, "probability": round((count / total) * 100, 2)}
            for end_zone, count in end_zones.items()
        ]

    # --- Package all results ---
    results_json = {
        "probabilities": {
            "all": probs_all,
            "singular": probs_singular,
            "path": probs_path
        },
        "probabilities_by_start_zone": final_probs_by_start_zone, # Add new data
        "totals": {
            "all": total_matches_all,
            "singular": total_matches_singular,
            "path": total_matches_path
        }
    }
    
    if test_type == 'Single':
        results_json["total_matches"] = total_matches_all
        history_for_json = [{"premise_date": m["premise_date"], "outcome_date": m["outcome_date"], "state": ", ".join(sorted(m['outcomes'], key=lambda x: ('->' in x, x)))} for m in historical_matches]
        results_json["history"] = history_for_json
        results_json["ticker"] = ticker
    else:
        results_json["total_historical_matches"] = total_matches_all
        
    return results_json

@app.route("/")
def index(): return render_template("index.html")

@app.route("/history")
def history_page(): return render_template("history.html")

@app.route("/readme")
def readme_page():
    return render_template("readme.html")

@app.route('/favicon.ico')
def favicon(): return Response(status=204)

@app.route('/view/<share_uuid>')
def view_shared_test(share_uuid):
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cursor = db.cursor()
    row = cursor.execute("SELECT * FROM backtests WHERE share_uuid = ?", (share_uuid,)).fetchone(); db.close()
    if not row: return "Test not found or not shared.", 404
    return render_template("view.html", test_data=dict(row))

@app.route('/api/get_history_by_id/<int:test_id>')
def get_history_by_id(test_id):
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cursor = db.cursor()
    row = cursor.execute("SELECT * FROM backtests WHERE id = ?", (test_id,)).fetchone(); db.close()
    if not row: return jsonify({"error": "Test not found"}), 404
    data = dict(row)
    data['results'] = json.loads(data['results'])
    if data.get('parameters'): data['parameters'] = json.loads(data['parameters'])
    data['results']['test_id'] = data['id']
    return jsonify(data)

@app.route('/api/get_tickers')
def get_tickers():
    try: return jsonify(sorted([f.replace('.csv', '') for f in os.listdir(DATA_DIR) if f.endswith('.csv')]))
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/get_stock_universes')
def get_stock_universes():
    try:
        if not os.path.exists(STOCK_LIST_FILE): return jsonify({'All Tickers': []})
        df = pd.read_csv(STOCK_LIST_FILE, on_bad_lines='skip'); df.columns = [col.strip() for col in df.columns]
        universes = {'All Tickers': []}
        for type_name, group in df.groupby('Type'): universes[type_name.strip()] = group['Symbol'].str.strip().tolist()
        return jsonify(universes)
    except Exception as e: app.logger.error(f"Error reading stock list: {e}"); return jsonify({"error": str(e)}), 500

@app.route('/api/get_history')
def get_history_route():
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cursor = db.cursor()
    rows = cursor.execute("SELECT id, timestamp, test_type, test_name, parameters, results, notes, share_uuid FROM backtests ORDER BY timestamp DESC").fetchall()
    db.close(); return jsonify([dict(row) for row in rows])

@app.route('/api/run_backtest', methods=['POST'])
def run_backtest_endpoint():
    try:
        data = request.json; test_name = data.get('test_name') or 'Untitled Single Test'
        params = {'ticker': data['ticker'], 'start_date': data['start_date'], 'end_date': data['end_date']}
        parsed_pattern = parse_advanced_pattern(data['pattern']); notes = data.get('notes', '')
        historical_matches = run_analysis(params['ticker'], params['start_date'], params['end_date'], parsed_pattern)
        if not historical_matches: return jsonify({"message": f"No historical instances found for {params['ticker']}."})
        results_json = process_and_package_results(historical_matches, 'Single', params['ticker'])
        db = sqlite3.connect(DATABASE); cursor = db.cursor()
        cursor.execute("INSERT INTO backtests (timestamp, test_type, test_name, pattern, parameters, results, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'Single', test_name, data['pattern'], json.dumps(params), json.dumps(results_json), notes))
        results_json['test_id'] = cursor.lastrowid; db.commit(); db.close()
        return jsonify(results_json)
    except Exception as e: app.logger.error(f"Error: {e}", exc_info=True); return jsonify({"error": f"An internal server error occurred: {e}"}), 500

@app.route('/api/run_camarilla_mind', methods=['POST'])
def run_camarilla_mind_endpoint():
    try:
        data = request.json; test_name = data.get('test_name') or 'Untitled Mind Test'
        params = {'start_date': data['start_date'], 'end_date': data['end_date'], 'universe': data.get('universe', 'All Tickers')}
        parsed_pattern = parse_advanced_pattern(data['pattern']); notes = data.get('notes', '')
        if params['universe'] == 'All Tickers': tickers_to_run = [f.replace('.csv', '') for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
        else: stock_df = pd.read_csv(STOCK_LIST_FILE); stock_df.columns = [col.strip() for col in stock_df.columns]; tickers_to_run = stock_df[stock_df['Type'] == params['universe']]['Symbol'].str.strip().tolist()
        all_historical_matches = []
        for ticker in tickers_to_run:
            matches = run_analysis(ticker, params['start_date'], params['end_date'], parsed_pattern)
            all_historical_matches.extend(matches)
        if not all_historical_matches: return jsonify({"message": f"No historical matches found in the '{params['universe']}' universe."})
        results_json = process_and_package_results(all_historical_matches, 'Mind')
        db = sqlite3.connect(DATABASE); cursor = db.cursor()
        cursor.execute("INSERT INTO backtests (timestamp, test_type, test_name, pattern, parameters, results, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'Mind', test_name, data['pattern'], json.dumps(params), json.dumps(results_json), notes))
        results_json['test_id'] = cursor.lastrowid; db.commit(); db.close()
        return jsonify(results_json)
    except Exception as e: app.logger.error(f"Error: {e}", exc_info=True); return jsonify({"error": f"An internal server error occurred: {e}"}), 500

@app.route('/api/share_test/<int:test_id>', methods=['POST'])
def share_test(test_id):
    db = sqlite3.connect(DATABASE); cursor = db.cursor()
    cursor.execute("SELECT share_uuid FROM backtests WHERE id = ?", (test_id,)); result = cursor.fetchone()
    if result and result[0]: share_uuid = result[0]
    else: share_uuid = str(uuid.uuid4()); cursor.execute("UPDATE backtests SET share_uuid = ? WHERE id = ?", (share_uuid, test_id)); db.commit()
    db.close(); share_url = url_for('view_shared_test', share_uuid=share_uuid, _external=True); return jsonify({"share_url": share_url})

@app.route('/api/export_test/<int:test_id>')
def export_test(test_id):
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cursor = db.cursor()
    row = cursor.execute("SELECT * FROM backtests WHERE id = ?", (test_id,)).fetchone(); db.close()
    if not row: return jsonify({"error": "Test not found"}), 404
    test_data = dict(row)
    if test_data.get('parameters'): test_data['parameters'] = json.loads(test_data['parameters'])
    if test_data.get('results'): test_data['results'] = json.loads(test_data['results'])
    test_data.pop('id', None); test_data.pop('share_uuid', None)
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', test_data.get('test_name', 'export'))
    filename = f"backtest_{sanitized_name}.qwc"
    return Response(json.dumps(test_data, indent=2), mimetype="application/json", headers={"Content-Disposition": f"attachment;filename={filename}"})

@app.route('/api/pdf/<int:test_id>', methods=['POST'])
def generate_pdf_from_images(test_id):
    try:
        data = request.json
        bar_chart_b64 = data.get('bar_chart_img')
        histogram_b64 = data.get('histogram_img')

        db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; cursor = db.cursor()
        row = cursor.execute("SELECT * FROM backtests WHERE id = ?", (test_id,)).fetchone()
        db.close()
        if not row:
            return jsonify({"error": "Test not found"}), 404

        test_data = dict(row)
        params = json.loads(test_data['parameters'])
        results = json.loads(test_data['results'])

        pdf = PDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        page_w = pdf.w - 2 * pdf.l_margin
        label_w = 38
        value_w = page_w - label_w

        # --- HEADER ---
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 12, f"Backtest Report: {test_data['test_name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.set_font('helvetica', '', 11)
        if test_data['test_type'] == 'Single':
            pdf.cell(0, 7, f"Test Type: Single | Ticker: {params.get('ticker', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        else:
            pdf.cell(0, 7, f"Test Type: Mind | Universe: {params.get('universe', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(2)

        # --- PARAMETERS ---
        pdf.set_font('helvetica', 'B', 12)
        pdf.cell(0, 10, "Test Parameters", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(label_w, 6, "Pattern:")
        pdf.set_font('helvetica', '', 10)
        pdf.multi_cell(value_w, 6, test_data['pattern'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(label_w, 6, "Date Range:")
        pdf.set_font('helvetica', '', 10)
        pdf.cell(value_w, 6, f"{params['start_date']} to {params['end_date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if test_data.get('notes'):
            pdf.set_font('helvetica', 'B', 10)
            pdf.cell(label_w, 6, "Notes:")
            pdf.set_font('helvetica', '', 10)
            pdf.multi_cell(value_w, 6, test_data['notes'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        # --- PROBABILITY OUTCOME TABLE ---
        pdf.set_font('helvetica', 'B', 12)
        pdf.cell(0, 9, "Probability Outcomes", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', 'B', 10)
        pdf.set_fill_color(58, 104, 184)
        pdf.set_text_color(255)
        pdf.cell(120, 7, "Outcome", border=1, align='L', fill=True)
        pdf.cell(page_w - 120, 7, "Probability (%)", border=1, align='C', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 10)
        pdf.set_text_color(30)
        for item in results.get('probabilities', {}).get('all', []):
            pdf.cell(120, 7, str(item['state']), border=1)
            pdf.cell(page_w - 120, 7, f"{item['probability']:.2f}", border=1, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        # --- HISTORY TABLE (if present) ---
        if 'history' in results and isinstance(results['history'], list) and results['history']:
            pdf.set_font('helvetica', 'B', 12)
            pdf.cell(0, 9, "Historical Matches (up to 30 shown)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font('helvetica', 'B', 10)
            pdf.set_fill_color(58, 104, 184)
            pdf.set_text_color(255)
            date_w = 38
            outcome_w = page_w - (date_w * 2)
            pdf.cell(date_w, 7, "Pattern Date", border=1, align='C', fill=True)
            pdf.cell(date_w, 7, "Outcome Date", border=1, align='C', fill=True)
            pdf.cell(outcome_w, 7, "Outcome State(s)", border=1, align='L', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(30)
            for hist in results['history'][:30]:
                pdf.cell(date_w, 7, str(hist['premise_date']), border=1)
                pdf.cell(date_w, 7, str(hist['outcome_date']), border=1)
                pdf.multi_cell(outcome_w, 7, str(hist['state']), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        # --- IMAGE SECTION (Bar & Histogram) ---
        chart_dir = os.path.join(BASE_DIR, 'static', 'charts')
        os.makedirs(chart_dir, exist_ok=True)

        # Bar chart image
        img_path = None
        try:
            if bar_chart_b64:
                img_data = base64.b64decode(bar_chart_b64.split(',')[1])
                img = Image.open(io.BytesIO(img_data)).convert('RGB')
                img_path = os.path.join(chart_dir, f'temp_bar_{test_id}.jpg')
                img.save(img_path, 'JPEG')
                img_w = pdf.w - 2 * pdf.l_margin
                img_h = img_w * img.height / img.width
                if pdf.get_y() + img_h > pdf.h - pdf.b_margin:
                    pdf.add_page()
                pdf.set_font('helvetica', 'B', 11)
                pdf.cell(0, 8, "Probability Bar Chart", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                pdf.image(img_path, x=pdf.l_margin, w=img_w)
        finally:
            if img_path and os.path.exists(img_path):
                os.remove(img_path)

        # Histogram chart image
        hist_path = None
        try:
            if histogram_b64:
                img_data = base64.b64decode(histogram_b64.split(',')[1])
                img = Image.open(io.BytesIO(img_data)).convert('RGB')
                hist_path = os.path.join(chart_dir, f'temp_hist_{test_id}.jpg')
                img.save(hist_path, 'JPEG')
                img_w = pdf.w - 2 * pdf.l_margin
                img_h = img_w * img.height / img.width
                if pdf.get_y() + img_h > pdf.h - pdf.b_margin:
                    pdf.add_page()
                pdf.ln(5)
                pdf.set_font('helvetica', 'B', 11)
                pdf.cell(0, 8, "Probability Distribution Histogram", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                pdf.image(hist_path, x=pdf.l_margin, w=img_w)
        finally:
            if hist_path and os.path.exists(hist_path):
                os.remove(hist_path)

        pdf.ln(7)
        pdf.set_font('helvetica', 'I', 8)
        pdf.set_text_color(60, 60, 80)
        pdf.cell(0, 7, "Report generated by Quantway Consulting LLP Camarilla Backtester", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        pdf_bytes = pdf.output(dest='S')
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        return jsonify({'pdf_data': base64_pdf})

    except Exception as e:
        import traceback
        app.logger.error(f"PDF Generation Error: {traceback.format_exc()}")
        return jsonify({"error": f"Failed to generate PDF. Error: {e}"}), 500



if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)