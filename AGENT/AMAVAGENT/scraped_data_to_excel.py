import sys
import json
import csv
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class JsonConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dynamic JSON to CSV Converter")
        self.setGeometry(300, 200, 600, 400)

        self.layout = QVBoxLayout()

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.load_button = QPushButton("Load JSON Files")
        self.load_button.clicked.connect(self.load_files)

        self.export_button = QPushButton("Export to CSV")
        self.export_button.clicked.connect(self.export_csv)
        self.export_button.setEnabled(False)

        self.layout.addWidget(self.load_button)
        self.layout.addWidget(self.export_button)
        self.layout.addWidget(self.log)

        self.setLayout(self.layout)

        self.all_products = []
        self.all_keys = set()

    # ---- Flatten nested dictionary ----
    def flatten_dict(self, d, parent_key="", sep="_"):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, dict):
                items.update(self.flatten_dict(v, new_key, sep=sep))
            elif isinstance(v, list):
                items[new_key] = ", ".join(str(x) for x in v)
            else:
                items[new_key] = v

        return items

    # ---- Load JSON files ----
    def load_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select JSON Files", "", "JSON Files (*.json)"
        )

        if not files:
            return

        self.all_products.clear()
        self.all_keys.clear()

        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    # Case 1: Wrapped structure
                    if isinstance(data, dict) and "products" in data:
                        products = data["products"]

                    # Case 2: Single product dict
                    elif isinstance(data, dict):
                        products = [data]

                    # Case 3: List of products
                    elif isinstance(data, list):
                        products = data
                    else:
                        continue

                    for product in products:
                        flat_product = self.flatten_dict(product)
                        self.all_products.append(flat_product)
                        self.all_keys.update(flat_product.keys())

                self.log.append(f"Loaded: {file_path}")

            except Exception as e:
                self.log.append(f"Error loading {file_path}: {str(e)}")

        if self.all_products:
            self.export_button.setEnabled(True)
            self.log.append(f"\nTotal Products Loaded: {len(self.all_products)}")
            self.log.append(f"Total Unique Fields Detected: {len(self.all_keys)}")
        else:
            QMessageBox.warning(self, "No Data", "No valid products found.")

    # ---- Export CSV ----
    def export_csv(self):
        if not self.all_products:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV File", "", "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=sorted(self.all_keys))
                writer.writeheader()

                for product in self.all_products:
                    writer.writerow(product)

            QMessageBox.information(self, "Success", "CSV exported successfully!")
            self.log.append(f"Exported to: {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JsonConverter()
    window.show()
    sys.exit(app.exec())
