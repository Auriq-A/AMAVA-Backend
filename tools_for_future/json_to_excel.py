import sys
import json
import pandas as pd

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QLabel,
    QMessageBox,
)


class JsonToExcelApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JSON → Excel Converter")
        self.setGeometry(400, 200, 400, 200)

        self.json_path = None

        layout = QVBoxLayout()

        self.label = QLabel("Upload JSON file")
        layout.addWidget(self.label)

        self.upload_btn = QPushButton("Upload JSON")
        self.upload_btn.clicked.connect(self.upload_json)
        layout.addWidget(self.upload_btn)

        self.convert_btn = QPushButton("Convert & Save Excel")
        self.convert_btn.clicked.connect(self.convert_to_excel)
        layout.addWidget(self.convert_btn)

        self.setLayout(layout)

    def upload_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON file", "", "JSON Files (*.json)"
        )

        if file_path:
            self.json_path = file_path
            self.label.setText(f"Loaded: {file_path}")

    def convert_to_excel(self):
        if not self.json_path:
            QMessageBox.warning(self, "Error", "Upload JSON first.")
            return

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            rows = []

            for asin, info in data.items():
                restrictions = info.get("restrictions", [])

                # If no restrictions → eligible
                if not restrictions:
                    rows.append(
                        {
                            "ASIN": asin,
                            "Status": "ELIGIBLE",
                            "Reason Code": "",
                            "Message": "",
                        }
                    )
                else:
                    for r in restrictions:
                        reasons = r.get("reasons", [])

                        if not reasons:
                            rows.append(
                                {
                                    "ASIN": asin,
                                    "Status": "RESTRICTED",
                                    "Reason Code": "",
                                    "Message": "",
                                }
                            )
                        else:
                            for reason in reasons:
                                rows.append(
                                    {
                                        "ASIN": asin,
                                        "Status": "RESTRICTED",
                                        "Reason Code": reason.get("reasonCode", ""),
                                        "Message": reason.get("message", ""),
                                    }
                                )

            df = pd.DataFrame(rows)

            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Excel File", "output.xlsx", "Excel Files (*.xlsx)"
            )

            if save_path:
                df.to_excel(save_path, index=False)
                QMessageBox.information(self, "Success", "Excel file saved!")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JsonToExcelApp()
    window.show()
    sys.exit(app.exec())
