import json

# Load files
with open("avasam_office_products(215 scrolls).json", "r", encoding="utf-8") as f:
    supplier_data = json.load(f)

with open("resultData.json", "r", encoding="utf-8") as f:
    amazon_data = json.load(f)

# Extract supplier products list
supplier_products = supplier_data.get("products", [])

merged_results = []

for product in supplier_products:
    title = product.get("title", "").strip()

    # 100% exact match
    if title in amazon_data:
        amazon_entries = amazon_data[title]

        # Remove duplicates (optional but useful)
        seen = set()
        unique_entries = []
        for entry in amazon_entries:
            key = (entry.get("productASIN"), entry.get("status"))
            if key not in seen:
                seen.add(key)
                unique_entries.append(entry)

        # Merge
        merged_product = {
            **product,  # supplier data
            "amazon_data": unique_entries  # attach amazon results
        }

        merged_results.append(merged_product)

# Save output
with open("merged_output.json", "w", encoding="utf-8") as f:
    json.dump(merged_results, f, indent=4, ensure_ascii=False)

print(f"✅ Merged {len(merged_results)} products (100% exact matches only)")