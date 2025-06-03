
from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret_key'

inventory_file = "inventory.xlsx"
transactions_file = "transactions.xlsx"

def load_inventory():
    if os.path.exists(inventory_file):
        return pd.read_excel(inventory_file).fillna("")
    return pd.DataFrame(columns=["Part Number", "Part Name", "Quantity", "Min Stock", "Unit", "Machine", "Note"])

@app.route('/')
def index():
    df = load_inventory()
    df.fillna('', inplace=True)
    df["Low Stock"] = pd.to_numeric(df["Quantity"], errors='coerce') < pd.to_numeric(df["Min Stock"], errors='coerce')
    autofill_cols = ['Part Number', 'Part Name', 'Unit', 'Machine', 'Note', 'Min Stock']
    autofill_data = df[autofill_cols].drop_duplicates().to_dict(orient='records')
    return render_template("index.html", data=[], autofill_data=json.dumps(autofill_data))

@app.route('/search')
def search():
    keyword = request.args.get('keyword', '').strip().lower()
    df = load_inventory()
    df["Low Stock"] = pd.to_numeric(df["Quantity"], errors='coerce') < pd.to_numeric(df["Min Stock"], errors='coerce')
    if keyword:
        results = df[df.apply(lambda row: keyword in str(row["Part Number"]).lower() or keyword in str(row["Part Name"]).lower() or keyword in str(row["Machine"]).lower(), axis=1)]
    else:
        results = pd.DataFrame()
    return render_template("index.html", data=results.to_dict(orient="records"), autofill_data="[]")

@app.route('/add', methods=['POST'])
def add():
    flash("🚫 لا يمكنك الإضافة في وضع العرض فقط", "warning")
    return redirect(url_for('index'))

@app.route('/issue', methods=['POST'])
def issue_part():
    flash("🚫 لا يمكنك الصرف في وضع العرض فقط", "warning")
    return redirect(url_for('index'))

@app.route('/get_part_info', methods=['POST'])
def get_part_info():
    data = request.json
    part_number = data.get('part_number')
    part_name = data.get('part_name')

    df = load_inventory()

    result = None
    if part_number:
        result = df[df["Part Number"] == part_number]
    elif part_name:
        result = df[df["Part Name"] == part_name]

    if result is not None and not result.empty:
        row = result.iloc[0]
        return {
            "part_name": row["Part Name"],
            "quantity": int(row["Quantity"]) if pd.notnull(row["Quantity"]) else 0,
            "min_stock": int(row["Min Stock"]) if pd.notnull(row["Min Stock"]) else 0,
            "unit": row["Unit"],
            "machine": row["Machine"],
            "note": row["Note"]
        }
    return {}

@app.route('/top-issued')
def top_issued():
    if not os.path.exists(transactions_file):
        flash("No transactions file found.", "error")
        return redirect(url_for('index'))

    df = pd.read_excel(transactions_file)
    df = df[df["Action"] == "Issue"]

    if df.empty:
        flash("No issued transactions found.", "error")
        return redirect(url_for('index'))

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    summary = df.groupby(["Part Number", "Part Name"])['Quantity'].sum().reset_index()
    summary.columns = ["Part Number", "Part Name", "Total Issued"]
    latest_dates = df.groupby(["Part Number", "Part Name"])["Date"].max().reset_index()
    latest_dates.columns = ["Part Number", "Part Name", "Last Issued Date"]
    result = pd.merge(summary, latest_dates, on=["Part Number", "Part Name"])

    return render_template("top_issued.html", data=result.to_dict(orient="records"))

@app.route('/to-order')
def to_order():
    df = load_inventory()
    df.fillna('', inplace=True)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce')
    df["Min Stock"] = pd.to_numeric(df["Min Stock"], errors='coerce')
    low_stock = df[df["Quantity"] < df["Min Stock"]]
    return render_template("to_order.html", data=low_stock.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

