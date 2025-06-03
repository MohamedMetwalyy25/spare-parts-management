
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret_key'

inventory_file = "inventory.xlsx"
transactions_file = "transactions.xlsx"

USERNAME = "admin"
PASSWORD = "1234"

def load_inventory():
    if os.path.exists(inventory_file):
        return pd.read_excel(inventory_file).fillna("")
    return pd.DataFrame(columns=["Part Number", "Part Name", "Quantity", "Min Stock", "Unit", "Machine", "Note"])

def save_inventory(df):
    df.to_excel(inventory_file, index=False)

def log_transaction(action, part_number, part_name, quantity, machine, note):
    row = {
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Action": action,
        "Part Number": part_number,
        "Part Name": part_name,
        "Quantity": quantity,
        "Machine": machine,
        "Note": note
    }
    df = pd.read_excel(transactions_file) if os.path.exists(transactions_file) else pd.DataFrame(columns=row.keys())
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_excel(transactions_file, index=False)

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

    if not result.empty:
        row = result.iloc[0]
        return {
            "part_name": row["Part Name"],
            "quantity": row["Quantity"],
            "min_stock": row["Min Stock"],
            "unit": row["Unit"],
            "machine": row["Machine"],
            "note": row["Note"]
        }
    return {}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "error")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    df = load_inventory()
    df.fillna('', inplace=True)
    df["Low Stock"] = pd.to_numeric(df["Quantity"], errors='coerce') < pd.to_numeric(df["Min Stock"], errors='coerce')
    autofill_cols = ['Part Number', 'Part Name', 'Unit', 'Machine', 'Note', 'Min Stock']
    autofill_data = df[autofill_cols].drop_duplicates().to_dict(orient='records')
    return render_template("index.html", data=[], autofill_data=json.dumps(autofill_data))

@app.route('/search')
def search():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
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
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    df = load_inventory()
    part_number = request.form['part_number']
    part_name = request.form['part_name']
    quantity = int(request.form['quantity'])
    min_stock = request.form.get('min_stock', '')
    unit = request.form['unit']
    machine = request.form['machine']
    note = request.form['note']

    new_row = {
        "Part Number": part_number,
        "Part Name": part_name,
        "Quantity": quantity,
        "Min Stock": min_stock,
        "Unit": unit,
        "Machine": machine,
        "Note": note
    }

    index = df[df["Part Number"] == part_number].index
    if not index.empty:
        df.loc[index[0], "Quantity"] += quantity
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    save_inventory(df)
    log_transaction("Add", part_number, part_name, quantity, machine, note)
    flash("Part added successfully!", "success")
    return redirect(url_for('index'))

@app.route('/issue', methods=['POST'])
def issue_part():
    part_number = request.form.get('part_number')
    qty = request.form.get('quantity')

    if not part_number or not qty:
        flash("Please enter both Part Number and Quantity.", "warning")
        return redirect(url_for('index'))

    try:
        qty = int(qty)
    except ValueError:
        flash("Quantity must be a number.", "warning")
        return redirect(url_for('index'))

    df = load_inventory()
    df["Part Number"] = df["Part Number"].astype(str)

    if part_number in df["Part Number"].values:
        idx = df[df["Part Number"] == part_number].index[0]
        current_qty = int(df.at[idx, "Quantity"])

        if qty > current_qty:
            flash("Not enough quantity in stock!", "danger")
            return redirect(url_for('index'))

        df.at[idx, "Quantity"] = current_qty - qty
        save_inventory(df)

        part_name = df.at[idx, "Part Name"]
        machine = df.at[idx, "Machine"]
        note = df.at[idx, "Note"]
        log_transaction("Issue", part_number, part_name, qty, machine, note)

        flash("Part issued successfully!", "success")
    else:
        flash("Part number not found!", "danger")

    return redirect(url_for('index'))

@app.route('/top-issued')
def top_issued():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
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
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    df = load_inventory()
    df.fillna('', inplace=True)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce')
    df["Min Stock"] = pd.to_numeric(df["Min Stock"], errors='coerce')
    low_stock = df[df["Quantity"] < df["Min Stock"]]
    return render_template("to_order.html", data=low_stock.to_dict(orient='records'))

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
            "part_name": str(row["Part Name"]),
            "quantity": int(row["Quantity"]),
            "min_stock": int(row["Min Stock"]),
            "unit": str(row["Unit"]),
            "machine": str(row["Machine"]),
            "note": str(row["Note"])
        }
    return {}
if __name__ == '__main__':
    app.run(debug=True)
