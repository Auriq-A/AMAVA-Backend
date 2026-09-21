import sys
import json
import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QFileDialog, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal

class ConverterThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, json_file, excel_file):
        super().__init__()
        self.json_file = json_file
        self.excel_file = excel_file

    def run(self):
        try:
            self.progress.emit("Loading JSON file...")
            with open(self.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.progress.emit("Processing data...")
            rows = []
            for product, items in data.items():
                if not isinstance(items, list):
                    items = [items]

                for item in items:
                    if isinstance(item, dict):
                        row = {
                            "Product Name": product,
                            "ASIN": item.get("productASIN", ""),
                            "Status": item.get("status", "")
                        }
                    elif isinstance(item, str):
                        row = {
                            "Product Name": product,
                            "ASIN": "",
                            "Status": item
                        }
                    else:
                        row = {
                            "Product Name": product,
                            "ASIN": "",
                            "Status": str(item)
                        }

                    rows.append(row)

            df = pd.DataFrame(rows)

            self.progress.emit("Saving Excel file...")
            df.to_excel(self.excel_file, index=False)
            self.progress.emit("Conversion completed successfully!")
            self.finished.emit(True, f"Excel file saved to {self.excel_file}")

        except Exception as e:
            self.finished.emit(False, str(e))

class ResultDataConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.json_file = None
        self.excel_file = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ResultData JSON to Excel Converter")
        self.setGeometry(300, 300, 500, 400)

        layout = QVBoxLayout()

        self.label = QLabel("Select JSON file and output Excel file, then click Convert.")
        layout.addWidget(self.label)

        self.select_json_btn = QPushButton("Select JSON File")
        self.select_json_btn.clicked.connect(self.select_json)
        layout.addWidget(self.select_json_btn)

        self.json_path_label = QLabel("No JSON file selected")
        layout.addWidget(self.json_path_label)

        self.select_excel_btn = QPushButton("Select Output Excel File")
        self.select_excel_btn.clicked.connect(self.select_excel)
        layout.addWidget(self.select_excel_btn)

        self.excel_path_label = QLabel("No Excel file selected")
        layout.addWidget(self.excel_path_label)

        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self.convert)
        layout.addWidget(self.convert_btn)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def select_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select JSON File", "", "JSON Files (*.json)")
        if file_name:
            self.json_file = file_name
            self.json_path_label.setText(f"JSON: {file_name}")

    def select_excel(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Select Output Excel File", "", "Excel Files (*.xlsx)")
        if file_name:
            self.excel_file = file_name
            self.excel_path_label.setText(f"Excel: {file_name}")

    def convert(self):
        if not self.json_file or not self.excel_file:
            self.log_text.append("Please select both JSON and Excel files.")
            return

        self.convert_btn.setEnabled(False)
        self.thread = ConverterThread(self.json_file, self.excel_file)
        self.thread.progress.connect(self.log_text.append)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, message):
        self.convert_btn.setEnabled(True)
        self.log_text.append(message)
        if success:
            self.log_text.append("Done!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ResultDataConverter()
    window.show()
    sys.exit(app.exec())