import io
import logging

import pandas as pd
from flask import Flask, request, render_template_string, jsonify

# Import your library
from tradingapi_a.mconnect import *

# --- CONFIGURATION (HARDCODED) ---
MY_SECRET_KEY = "CJOHJvQ/lUBtRZSXIVAtd3wkLRaSDpVGbO92K+FAIo8="
SYMBOL = "NIFTY"
EXCHANGE = "NFO"

app = Flask(__name__)

# --- GLOBAL STATE ---
trading_client = None
# Cache for the full instrument list
MASTER_DF = None 

app_state = {
    "spot_price": 0.0,
    "atm_strike": 0,
    "expiry": None,
    "is_connected": False
}

# --- HTML TEMPLATE (LIGHT MODE) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nifty Option Chain Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        /* LIGHT MODE OVERRIDES */
        body { 
            background-color: #f0f2f5; 
            color: #333; 
            padding-top: 20px; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        }
        
        .container { 
            max-width: 900px; 
            background-color: #ffffff; 
            border-radius: 8px; 
            padding: 25px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.05); 
            border: 1px solid #e1e4e8;
        }
        
        /* Table Styling */
        .table { color: #495057; margin-bottom: 0; }
        .table thead th { 
            background-color: #f8f9fa; 
            border-bottom: 2px solid #dee2e6; 
            font-weight: 600; 
            color: #212529;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
        }
        .table td { vertical-align: middle; border-color: #e9ecef; background-color: #fff; }
        
        /* Columns */
        .strike-col { background-color: #f8f9fa !important; font-weight: 700; font-size: 1.1em; color: #000; border-left: 1px solid #dee2e6; border-right: 1px solid #dee2e6;}
        
        /* Call/Put Colors */
        .ce-color { color: #198754; font-weight: 500; } 
        .pe-color { color: #dc3545; font-weight: 500; } 
        
        /* ATM Highlight */
        .atm-row { background-color: #fff9c4 !important; border-left: 4px solid #f1c40f; }

        /* Flash Animations */
        @keyframes flashGreen { 
            0% { background-color: #d1e7dd; color: #0f5132; } 
            100% { background-color: transparent; color: inherit; } 
        }
        @keyframes flashRed { 
            0% { background-color: #f8d7da; color: #842029; } 
            100% { background-color: transparent; color: inherit; } 
        }
        
        .flash-up { animation: flashGreen 0.8s ease-out; }
        .flash-down { animation: flashRed 0.8s ease-out; }

        /* Utility */
        .text-sm { font-size: 0.85rem; color: #6c757d; }
        #loading-spinner { display: none; }
        .card-header { border-bottom: 1px solid #dee2e6; margin-bottom: 20px; background: transparent; padding-bottom: 10px; }
        
        .form-control {
            background-color: #fff;
            color: #212529;
            border-color: #ced4da;
        }
        .form-control:focus {
            background-color: #fff;
            color: #212529;
            border-color: #86b7fe;
            box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.25);
        }
    </style>
</head>
<body>

    <div class="container">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h4 class="m-0 text-dark">{{ symbol }} Option Chain <span class="badge bg-success">LIVE</span></h4>
            <div id="connection-status" class="badge bg-secondary">Disconnected</div>
        </div>

        <!-- Login Form -->
        <div id="login-form">
            <form id="connectForm">
                <div class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label text-sm">TOTP Code</label>
                        <input type="text" class="form-control" name="totp_code" placeholder="e.g. 248493" required>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label text-sm">Spot Price (Approx)</label>
                        <input type="number" step="0.05" class="form-control" name="nifty_price" placeholder="e.g. 23150" required>
                    </div>
                </div>
                <div class="d-grid mt-4">
                    <button type="submit" class="btn btn-primary btn-lg">Connect & Start</button>
                </div>
            </form>
            <div id="login-error" class="alert alert-danger mt-3" style="display:none;"></div>
        </div>

        <!-- Data Display -->
        <div id="data-area" style="display:none;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <span class="text-sm">EXPIRY:</span> <strong id="expiry-display" class="text-dark">--</strong>
                    <span class="mx-2">|</span>
                    <span class="text-sm">SPOT:</span> <strong id="spot-display" class="text-warning">{{ spot_price }}</strong>
                </div>
                <div id="loading-spinner" class="spinner-border text-primary" role="status" style="width: 1rem; height: 1rem;"></div>
            </div>
            
            <div class="table-responsive rounded border">
                <table class="table table-sm table-hover mb-0">
                    <thead>
                        <tr>
                            <th colspan="2" class="text-center text-success border-end">CALLS (CE)</th>
                            <th class="text-center">STRIKE</th>
                            <th colspan="2" class="text-center text-danger border-start">PUTS (PE)</th>
                        </tr>
                        <tr>
                            <th class="text-end text-sm">OI</th>
                            <th class="text-end text-sm">LTP</th>
                            <th class="text-center strike-col">PRICE</th>
                            <th class="text-start text-sm">LTP</th>
                            <th class="text-start text-sm">OI</th>
                        </tr>
                    </thead>
                    <tbody id="chain-body">
                        <!-- Rows inserted by JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const ATM_STRIKE = {{ atm_strike }};
        let isRunning = false;
        let previousData = {}; 

        document.getElementById('connectForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            
            fetch('/', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('login-form').style.display = 'none';
                    document.getElementById('data-area').style.display = 'block';
                    document.getElementById('expiry-display').innerText = data.expiry;
                    document.getElementById('connection-status').className = "badge bg-success";
                    document.getElementById('connection-status').innerText = "Connected";
                    
                    isRunning = true;
                    fetchData();
                    setInterval(fetchData, 1000); 
                } else {
                    const errDiv = document.getElementById('login-error');
                    errDiv.innerText = data.message;
                    errDiv.style.display = 'block';
                }
            })
            .catch(err => alert("Error: " + err));
        });

        function fetchData() {
            if (!isRunning) return;
            document.getElementById('loading-spinner').style.display = 'inline-block';

            fetch('/api/chain')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error(data.error);
                    return;
                }
                renderTable(data);
            })
            .catch(err => console.error(err))
            .finally(() => {
                document.getElementById('loading-spinner').style.display = 'none';
            });
        }

        function renderTable(data) {
            const tbody = document.getElementById('chain-body');
            const fragment = document.createDocumentFragment();

            data.forEach(row => {
                const tr = document.createElement('tr');
                if (row.strike === ATM_STRIKE) tr.classList.add('atm-row');

                const prev = previousData[row.strike] || { ce_ltp: 0, pe_ltp: 0 };
                const ceFlashClass = row.ce_ltp > prev.ce_ltp ? 'flash-up' : (row.ce_ltp < prev.ce_ltp ? 'flash-down' : '');
                const peFlashClass = row.pe_ltp > prev.pe_ltp ? 'flash-up' : (row.pe_ltp < prev.pe_ltp ? 'flash-down' : '');

                previousData[row.strike] = { ce_ltp: row.ce_ltp, pe_ltp: row.pe_ltp };

                tr.innerHTML = `
                    <td class="text-end text-sm text-muted">${row.ce_oi.toLocaleString()}</td>
                    <td class="text-end ce-color ${ceFlashClass}">${row.ce_ltp.toFixed(2)}</td>
                    <td class="text-center strike-col">${row.strike}</td>
                    <td class="text-start pe-color ${peFlashClass}">${row.pe_ltp.toFixed(2)}</td>
                    <td class="text-start text-sm text-muted">${row.pe_oi.toLocaleString()}</td>
                `;
                fragment.appendChild(tr);
            });

            tbody.innerHTML = '';
            tbody.appendChild(fragment);
        }
    </script>
</body>
</html>
"""

def get_filtered_instruments(full_df, target_exp, atm_strike):
    """Filters DataFrame by Expiry and Strike Range."""
    if full_df is None: return pd.DataFrame()

    # 1. Filter by Expiry
    df_exp = full_df[full_df["expiry"] == target_exp].copy()
    if df_exp.empty: return pd.DataFrame()

    # 2. Filter by Strike Range (ATM +/- 500)
    lower = atm_strike - 500
    upper = atm_strike + 500
    df_range = df_exp[(df_exp["strike"] >= lower) & (df_exp["strike"] <= upper)]
    
    return df_range

@app.route('/', methods=['GET', 'POST'])
def index():
    global trading_client, app_state, MASTER_DF

    if request.method == 'POST':
        try:
            totp_input = request.form.get('totp_code')
            nifty_price = float(request.form.get('nifty_price'))

            # Initialize Client
            trading_client = MConnect()
            trading_client.verify_totp(MY_SECRET_KEY, totp_input)
            
            # Load Master List
            print("Downloading Master Instrument List...")
            res = trading_client.get_instruments()
            csv = io.BytesIO(res)
            MASTER_DF = pd.read_csv(csv, low_memory=False)
            
            # Filter to NIFTY Options to save memory
            MASTER_DF = MASTER_DF[
                (MASTER_DF["segment"] == "OPTIDX") &
                (MASTER_DF["exchange"] == EXCHANGE) &
                (MASTER_DF["tradingsymbol"].str.startswith(SYMBOL))
            ]
            print(f"Master list loaded. {len(MASTER_DF)} symbols found.")

            # Determine Expiry
            exp_list = MASTER_DF["expiry"].dropna().unique().tolist()
            exp_list.sort()
            nearest_exp = exp_list[0] if exp_list else "Unknown"

            # Calculate ATM
            atm_strike = int(round(nifty_price / 50) * 50)

            # Save State
            app_state = {
                "spot_price": nifty_price,
                "atm_strike": atm_strike,
                "expiry": nearest_exp,
                "is_connected": True
            }

            return jsonify({"status": "success", "expiry": nearest_exp})

        except Exception as e:
            logging.error(f"Connection Error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    return render_template_string(HTML_TEMPLATE, 
                                  symbol=SYMBOL,
                                  atm_strike=app_state.get("atm_strike", 0),
                                  spot_price=app_state.get("spot_price", ""))

@app.route('/api/chain', methods=['GET'])
def get_chain_data():
    global trading_client, app_state, MASTER_DF

    if not trading_client or not app_state["is_connected"]:
        return jsonify({"error": "Client not initialized"})

    try:
        df_filtered = get_filtered_instruments(MASTER_DF, app_state["expiry"], app_state["atm_strike"])
        
        if df_filtered.empty:
            return jsonify([])

        # Identify columns dynamically
        price_col = 'last_price' if 'last_price' in df_filtered.columns else 'close'
        oi_col = 'open_interest' if 'open_interest' in df_filtered.columns else 'oi'

        result = []
        strikes = df_filtered["strike"].unique().tolist()
        strikes.sort()

        for s in strikes:
            strike_data = df_filtered[df_filtered["strike"] == s]
            
            # Get CE
            if "option_type" in strike_data.columns:
                ce_row = strike_data[strike_data["option_type"] == "CE"]
                pe_row = strike_data[strike_data["option_type"] == "PE"]
            else:
                ce_row = strike_data[strike_data["tradingsymbol"].str.endswith("CE")]
                pe_row = strike_data[strike_data["tradingsymbol"].str.endswith("PE")]

            # Extract values safely
            ce_ltp = float(ce_row[price_col].values[0]) if not ce_row.empty else 0.0
            pe_ltp = float(pe_row[price_col].values[0]) if not pe_row.empty else 0.0
            
            ce_oi = int(ce_row[oi_col].values[0]) if (not ce_row.empty and oi_col in ce_row.columns) else 0
            pe_oi = int(pe_row[oi_col].values[0]) if (not pe_row.empty and oi_col in pe_row.columns) else 0

            result.append({
                "strike": int(s),
                "ce_ltp": ce_ltp,
                "ce_oi": ce_oi,
                "pe_ltp": pe_ltp,
                "pe_oi": pe_oi
            })

        return jsonify(result)

    except Exception as e:
        logging.error(f"API Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)