import json
import pandas as pd

# 🟩 Recursive flatten function
def flatten_json(y, parent_key='', sep='_'):
    items = []
    if isinstance(y, dict):
        for k, v in y.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(flatten_json(v, new_key, sep=sep).items())
    elif isinstance(y, list):
        # Join lists into string (you can customize this)
        items.append((parent_key, ", ".join(map(str, y))))
    else:
        items.append((parent_key, y))
    return dict(items)

# 🟦 Load JSON
# for i in range(1, 11):
    
with open(f"doba_home_products(500 scrolls).json", "r", encoding="utf-8") as f:
    data = json.load(f)

products = data.get("products", [])

# 🟩 Flatten all products dynamically
flattened_data = [flatten_json(product) for product in products]

# 🟦 Convert to DataFrame (auto columns)
df = pd.DataFrame(flattened_data)

# 🟦 Optional cleaning (light, still dynamic)
if "brand" in df.columns:
    df["brand"] = df["brand"].astype(str).str.split("\n").str[0]

if "price" in df.columns:
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

if "stock_available" in df.columns:
    df["in_stock"] = df["stock_available"].apply(lambda x: "Yes" if x and x > 0 else "No")

# 🟦 Save to Excel
output_file = f"products_dynamic_scroll(500).xlsx"
df.to_excel(output_file, index=False)

print(f"✅ Dynamic Excel created: {output_file}")
    
# Merge all Excel files into one
# all_dfs = []
# for i in range(1, 11):
#     df = pd.read_excel(f"products_dynamic_page{i}.xlsx")
#     all_dfs.append(df)

# Concatenate all DataFrames
# final_df = pd.concat(all_dfs, ignore_index=True)

# Save the merged DataFrame to a new Excel file
# final_df.to_excel("merged_products_dynamic.xlsx", index=False)
# print("✅ Merged Excel created: merged_products_dynamic.xlsx")