# Camarilla Pivot Backtester

**A powerful web-based tool for backtesting trading strategies based on Camarilla pivot points.**

This application, developed by Quantway Consulting LLP, allows financial analysts and traders to define complex, multi-month patterns using Camarilla pivot levels and analyze their historical performance across individual stocks or entire market universes.

## License & Copyright

**This is proprietary software and is not free for commercial or educational use.**

Copyright (c) 2024 Quantway Consulting LLP. All Rights Reserved.

The use of this software is governed by a specific license agreement.

-   **Permitted Use:** You are granted a limited license for **personal, non-commercial, and evaluation purposes only.**

-   **Restricted Use:** A separate, paid commercial license is **required** for any of the following uses:
    -   Use for any commercial purpose or for financial gain (e.g., trading, investment analysis).
    -   Use within any commercial or non-profit organization (including brokerage houses, funds, etc.).
    -   Use in any educational capacity (e.g., courses, seminars, tutorials).
    -   Redistribution of the software or its outputs.

**For all commercial licensing inquiries, please contact: `quantwayconsulting@gmail.com`**

Please see the `LICENSE` file in this repository for the full legal terms and conditions.

---

## Features

-   **Advanced Pattern Definition:** Define intricate, multi-month patterns. For example, "Find all instances where the market touched R4 last month and then touched S3 this month."
-   **Single Ticker Analysis:** Run a detailed backtest on a single stock to see historical occurrences and subsequent market behavior.
-   **Market-Wide Analysis (Camarilla Mind):** Scan an entire universe of stocks (e.g., Nifty 50, All Tickers) for your defined pattern to find high-probability setups across the market.
-   **Detailed Outcome Probabilities:** Results are broken down into overall probabilities, singular vs. path outcomes, and powerful conditional probabilities based on the starting price zone.
-   **Interactive Visualizations:** Clear bar charts provide an intuitive view of all outcome probabilities.
-   **Full History Tracking:** All backtests are saved and can be reviewed, shared, or re-loaded from the History page.
-   **Professional PDF Reports:** Export any backtest result into a clean, professional PDF document for sharing or archiving.
-   **Customizable Themes:** Switch between Light, Bloomberg Dark, and Tokyo Night UI themes.

---

## Technical Stack

-   **Backend:** Python with Flask
-   **Data Processing:** Pandas, NumPy
-   **Database:** SQLite
-   **Frontend:** HTML, CSS, JavaScript
--   **Charting:** Chart.js
-   **PDF Generation:** FPDF, Pillow

---

## Installation & Setup

Follow these steps to get the Camarilla Backtester running on your local machine.

### Prerequisites

-   Python 3.8 or newer
-   `pip` (Python package installer)

### 1. Clone the Repository
https://github.com/quantwayconsutling/CamarillaPivotBacktester

### 2. Create a Virtual Environment (Recommended)


### For Windows
python -m venv venv
venv\Scripts\activate

### For macOS/Linux
python3 -m venv venv
source venv/bin/activate

### 3. Install Dependencies
Install all the required Python packages using the requirements.txt file.
pip install -r requirements.txt 
or
pip install Flask pandas numpy scipy fpdf2 Pillow

### 5. Data Setup
The backtester relies on historical price data in CSV format.
Place your .csv data files inside the /data directory.
Each file should be named after the ticker symbol (e.g., RELIANCE.csv, TCS.csv).
The CSV files must contain at least the following columns: datetime, open, high, low, close.

### 6. Stock Universe Setup (Optional)
To use the "Market-Wide Analysis" with predefined universes (like Nifty 50):
Edit the StockList.csv file in the root directory.
Ensure it has at least two columns: Symbol and Type.
The Symbol must match the CSV filename in the /data directory (without the .csv extension).
The Type column is used to group stocks into universes (e.g., "Nifty 50", "Bank Nifty").

### 7. Run the Application
Once the setup is complete, run the Flask application:

python app.py

### Open your web browser and navigate to http://127.0.0.1:5000 to start using the tool.

How to Use the Backtester
Please refer to the "Guide" tab within the application for detailed instructions on pattern definition and interpreting results.
