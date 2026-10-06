import sys
import json
from pathlib import Path
import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QFileDialog, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal

class ConverterThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, json_files, excel_file):
        super().__init__()
        self.json_files = json_files
        self.excel_file = excel_file

    def run(self):
        try:
            used_sheet_names = set()
            with pd.ExcelWriter(self.excel_file) as writer:
                for json_file in self.json_files:
                    file_name = Path(json_file).name
                    self.progress.emit(f"Loading {file_name}...")
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    self.progress.emit(f"Processing {file_name}...")
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

                    sheet_base = "".join(
                        "_" if char in '[]:*?/\\' else char
                        for char in Path(json_file).stem
                    ).strip("'")[:31] or "Sheet"
                    sheet_name = sheet_base
                    suffix = 2
                    while sheet_name.casefold() in used_sheet_names:
                        suffix_text = f"_{suffix}"
                        sheet_name = f"{sheet_base[:31 - len(suffix_text)]}{suffix_text}"
                        suffix += 1
                    used_sheet_names.add(sheet_name.casefold())

                    self.progress.emit(f"Saving {file_name} to sheet {sheet_name}...")
                    pd.DataFrame(rows).to_excel(
                        writer, sheet_name=sheet_name, index=False
                    )

            self.progress.emit("Conversion completed successfully!")
            self.finished.emit(
                True,
                f"Excel file with {len(self.json_files)} sheets saved to {self.excel_file}"
            )

        except Exception as e:
            self.finished.emit(False, str(e))

class ResultDataConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.json_files = []
        self.excel_file = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ResultData JSON to Excel Converter")
        self.setGeometry(300, 300, 500, 400)

        layout = QVBoxLayout()

        self.label = QLabel("Select JSON files and an output Excel file, then click Convert.")
        layout.addWidget(self.label)

        self.select_json_btn = QPushButton("Select JSON Files")
        self.select_json_btn.clicked.connect(self.select_json)
        layout.addWidget(self.select_json_btn)

        self.json_path_label = QLabel("No JSON files selected")
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
        file_names, _ = QFileDialog.getOpenFileNames(
            self, "Select JSON Files", "", "JSON Files (*.json)"
        )
        if file_names:
            self.json_files = file_names
            self.json_path_label.setText(f"{len(file_names)} JSON files selected")

    def select_excel(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Select Output Excel File", "", "Excel Files (*.xlsx)")
        if file_name:
            self.excel_file = file_name
            self.excel_path_label.setText(f"Excel: {file_name}")

    def convert(self):
        if not self.json_files or not self.excel_file:
            self.log_text.append("Please select JSON files and an Excel output file.")
            return

        self.convert_btn.setEnabled(False)
        self.thread = ConverterThread(self.json_files, self.excel_file)
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