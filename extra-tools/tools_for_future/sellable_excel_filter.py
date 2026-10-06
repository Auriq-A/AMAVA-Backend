import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


SELLABLE_STATUS = "you can sell this item!"


def normalize_key(value):
    normalized = unicodedata.normalize("NFKC", str(value)).upper()
    return re.sub(r"[^A-Z0-9]", "", normalized)


def get_sellable_keys(json_file):
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("The JSON file must contain an object keyed by product/ASIN.")

    sellable_keys = {}
    for key, items in data.items():
        if not isinstance(items, list):
            items = [items]

        for item in items:
            if isinstance(item, dict):
                status = str(item.get("status", "")).strip().casefold()
                if SELLABLE_STATUS in status:
                    normalized_key = normalize_key(key)
                    sellable_keys.setdefault(normalized_key, str(key).strip())
                    break

    return sellable_keys


def filter_workbook(json_file, excel_file, output_file):
    output_path = Path(output_file)
    if output_path.resolve() == Path(excel_file).resolve():
        raise ValueError("The output file must be different from the source workbook.")
    if output_path.resolve() == Path(json_file).resolve():
        raise ValueError("The output file must be different from the JSON file.")

    sellable_keys = get_sellable_keys(json_file)
    output_rows = []
    source_columns = []

    with pd.ExcelFile(excel_file) as workbook:
        for sheet_name in workbook.sheet_names:
            table = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
            for column in table.columns:
                if column not in source_columns:
                    source_columns.append(column)

            for _, row in table.iterrows():
                matched_keys = set()
                for value in row:
                    if pd.isna(value):
                        continue
                    normalized_value = normalize_key(value)
                    for key in sellable_keys:
                        if key and key in normalized_value:
                            matched_keys.add(key)

                if matched_keys:
                    output_rows.append({
                        "Source Worksheet": sheet_name,
                        "Matched JSON Keys": ", ".join(
                            sorted(sellable_keys[key] for key in matched_keys)
                        ),
                        "Source Values": row.to_dict(),
                    })

    metadata_columns = ["Source Worksheet", "Matched JSON Keys"]
    used_column_names = {column.casefold() for column in metadata_columns}
    output_column_names = {}
    for column in source_columns:
        base_name = str(column)
        output_name = base_name
        suffix = 2
        while output_name.casefold() in used_column_names:
            output_name = f"{base_name} (source data {suffix})"
            suffix += 1
        used_column_names.add(output_name.casefold())
        output_column_names[column] = output_name

    normalized_rows = []
    for row in output_rows:
        normalized_row = {
            "Source Worksheet": row["Source Worksheet"],
            "Matched JSON Keys": row["Matched JSON Keys"],
        }
        for column in source_columns:
            normalized_row[output_column_names[column]] = row["Source Values"].get(column)
        normalized_rows.append(normalized_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(
        normalized_rows,
        columns=metadata_columns + list(output_column_names.values()),
    )
    result.to_excel(output_path, sheet_name="Filtered Data", index=False)
    return len(output_rows), len(sellable_keys), str(output_path)


class FilterThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, json_file, excel_file, output_file):
        super().__init__()
        self.json_file = json_file
        self.excel_file = excel_file
        self.output_file = output_file

    def run(self):
        try:
            row_count, key_count, output_path = filter_workbook(
                self.json_file, self.excel_file, self.output_file
            )
            self.finished.emit(
                True,
                f"Saved {row_count} matching rows from {key_count} sellable keys to {output_path}",
            )
        except Exception as error:
            self.finished.emit(False, str(error))


class SellableExcelFilter(QWidget):
    def __init__(self):
        super().__init__()
        self.json_file = None
        self.excel_file = None
        self.output_file = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Filter Sellable Products from Excel")
        self.setGeometry(300, 300, 560, 400)

        layout = QVBoxLayout()
        layout.addWidget(
            QLabel("Choose a result JSON file, an Excel workbook, and an output file.")
        )

        self.json_button = QPushButton("Select Result JSON")
        self.json_button.clicked.connect(self.select_json)
        layout.addWidget(self.json_button)
        self.json_label = QLabel("No JSON file selected")
        layout.addWidget(self.json_label)

        self.excel_button = QPushButton("Select Excel Workbook")
        self.excel_button.clicked.connect(self.select_excel)
        layout.addWidget(self.excel_button)
        self.excel_label = QLabel("No Excel workbook selected")
        layout.addWidget(self.excel_label)

        self.output_button = QPushButton("Select Output File")
        self.output_button.clicked.connect(self.select_output)
        layout.addWidget(self.output_button)
        self.output_label = QLabel("No output file selected")
        layout.addWidget(self.output_label)

        self.convert_button = QPushButton("Filter Rows")
        self.convert_button.clicked.connect(self.convert)
        layout.addWidget(self.convert_button)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.setLayout(layout)

    def select_json(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Result JSON", "", "JSON Files (*.json)"
        )
        if file_name:
            self.json_file = file_name
            self.json_label.setText(Path(file_name).name)

    def select_excel(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel Workbook",
            "",
            "Excel Workbooks (*.xlsx *.xlsm *.xls *.xlsb)",
        )
        if file_name:
            self.excel_file = file_name
            self.excel_label.setText(Path(file_name).name)

    def select_output(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Filtered Workbook", "filtered_sellable.xlsx", "Excel Files (*.xlsx)"
        )
        if file_name:
            if Path(file_name).suffix.casefold() != ".xlsx":
                file_name += ".xlsx"
            self.output_file = file_name
            self.output_label.setText(Path(file_name).name)

    def convert(self):
        if not self.json_file or not self.excel_file or not self.output_file:
            self.log.append("Please select the JSON, source workbook, and output file.")
            return

        self.convert_button.setEnabled(False)
        self.thread = FilterThread(self.json_file, self.excel_file, self.output_file)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, message):
        self.convert_button.setEnabled(True)
        self.log.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SellableExcelFilter()
    window.show()
    sys.exit(app.exec())