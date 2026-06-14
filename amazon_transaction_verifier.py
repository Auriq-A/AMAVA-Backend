import pandas as pd
import tkinter as tk
from tkinter import messagebox, ttk

def reconcile_inputs():
    text1 = input1.get("1.0", tk.END).strip()
    text2 = input2.get("1.0", tk.END).strip()

    if not text1 or not text2:
        messagebox.showerror("Error", "Both inputs must have data!")
        return

    # Parse input into DataFrames
    df1 = pd.DataFrame([line.split("\t") for line in text1.splitlines()], columns=["order_id","amount"])
    df2 = pd.DataFrame([line.split("\t") for line in text2.splitlines()], columns=["order_id","amount"])
    df1["amount"] = pd.to_numeric(df1["amount"], errors="coerce").fillna(0.0)
    df2["amount"] = pd.to_numeric(df2["amount"], errors="coerce").fillna(0.0)

    # Merge on Order ID
    merged = pd.merge(df1, df2, on="order_id", how="outer", suffixes=("_first","_second"))
    merged["difference"] = merged["amount_first"] - merged["amount_second"]

    # Clear previous results
    for widget in result_frame.winfo_children():
        widget.destroy()

    # Show in table
    cols = list(merged.columns)
    tree = ttk.Treeview(result_frame, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=100, anchor="center")
    for _, row in merged.iterrows():
        tree.insert("", "end", values=list(row))
    tree.pack(fill="both", expand=True)

def sort_inputs():
    # Sort by Order ID and put back in text widgets
    for text_widget in [input1, input2]:
        lines = [line.strip() for line in text_widget.get("1.0", tk.END).splitlines() if line.strip()]
        df = pd.DataFrame([line.split("\t") for line in lines], columns=["order_id","amount"])
        df = df.sort_values("order_id")
        text_widget.delete("1.0", tk.END)
        text_widget.insert(tk.FIRST, "\n".join(df["order_id"] + "\t" + df["amount"].astype(str)))

# GUI
root = tk.Tk()
root.title("Order Reconciliation Tool")
root.geometry("1000x800")

tk.Label(root, text="Input 1").pack()
input1 = tk.Text(root, height=10)
input1.pack(fill="x", padx=10)

tk.Label(root, text="Input 2").pack()
input2 = tk.Text(root, height=10)
input2.pack(fill="x", padx=10)

btn_frame = tk.Frame(root)
btn_frame.pack(pady=10) 
tk.Button(btn_frame, text="Reconcile & Show Differences", command=reconcile_inputs).pack(side="left", padx=5)
tk.Button(btn_frame, text="Sort Both Inputs by OrderID", command=sort_inputs).pack(side="left", padx=5)

result_frame = tk.Frame(root)
result_frame.pack(fill="both", expand=True, padx=10, pady=10)

root.mainloop()