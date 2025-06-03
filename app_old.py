
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

@app.route('/')
def index():
    try:
        df = pd.read_excel(inventory_file)
        df.fillna('', inplace=True)
        df["Low Stock"] = pd.to_numeric(df["Quantity"], errors='coerce') < pd.to_numeric(df["Min Stock"], errors='coerce')
        autofill_cols = ['Part Number', 'Part Name', 'Unit', 'Machine', 'Note', 'Min Stock']
        autofill_data = df[autofill_cols].drop_duplicates().to_dict(orient='records')
        return render_template("index.html", data=df.to_dict(orient="records"), autofill_data=json.dumps(autofill_data))
    except Exception as e:
        return f"Error: {e}"

@app.route('/add', methods=['POST'])
def add():
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
def issue():
    df = load_inventory()
    part_number = request.form['part_number']
    quantity = int(request.form['quantity'])

    index = df[df["Part Number"] == part_number].index
    if not index.empty:
        if df.loc[index[0], "Quantity"] >= quantity:
            df.loc[index[0], "Quantity"] -= quantity
            save_inventory(df)
            log_transaction("Issue", part_number, df.loc[index[0], "Part Name"], quantity, df.loc[index[0], "Machine"], df.loc[index[0], "Note"])
            flash("Part issued successfully!", "success")
        else:
            flash("Not enough stock to issue.", "error")
    else:
        flash("Part not found.", "error")

    return redirect(url_for('index'))

@app.route('/search')
def search():
    keyword = request.args.get('keyword', '').strip().lower()
    df = load_inventory()
    df["Low Stock"] = pd.to_numeric(df["Quantity"], errors='coerce') < pd.to_numeric(df["Min Stock"], errors='coerce')
    results = df[df.apply(lambda row: keyword in str(row["Part Number"]).lower() or keyword in str(row["Part Name"]).lower() or keyword in str(row["Machine"]).lower(), axis=1)]
    return render_template("index.html", data=results.to_dict(orient="records"), autofill_data="[]")

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

if __name__ == '__main__':
    app.run(debug=True)
