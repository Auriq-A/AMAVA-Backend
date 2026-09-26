import sys
import os
import json
import requests
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QMessageBox,
)
from urllib.parse import urlparse


def sanitize_filename(name: str) -> str:
    """Clean title to be a safe filename"""
    invalid_chars = r'\/:*?"<>|'
    for ch in invalid_chars:
        name = name.replace(ch, "_")
    return name.strip()


class ImageDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JSON Image Downloader")
        self.setGeometry(200, 200, 400, 200)

        layout = QVBoxLayout()

        self.label = QLabel("Upload a JSON file with product data.")
        layout.addWidget(self.label)

        self.btn_upload = QPushButton("Upload JSON File")
        self.btn_upload.clicked.connect(self.upload_file)
        layout.addWidget(self.btn_upload)

        self.setLayout(layout)

    def upload_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self, "Open JSON File", "", "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not isinstance(data, list):
                    raise ValueError("JSON must be a list of objects")

                self.download_images(data)

            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to read JSON file:\n{str(e)}"
                )

    def download_images(self, data):
        save_dir = "downloads"
        os.makedirs(save_dir, exist_ok=True)

        downloaded = 0
        for item in data:
            image_url = item.get("image")
            title = item.get("title", "untitled")

            if not image_url:
                continue

            try:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()

                # detect extension from url or response header
                parsed = urlparse(image_url)
                ext = os.path.splitext(parsed.path)[1]
                if not ext:
                    ext = ".jpg"

                filename = sanitize_filename(title)[:100] + ext
                filepath = os.path.join(save_dir, filename)

                with open(filepath, "wb") as f:
                    f.write(response.content)

                downloaded += 1

            except Exception as e:
                print(f"Failed to download {image_url}: {e}")

        QMessageBox.information(
            self, "Done", f"Downloaded {downloaded} images into '{save_dir}' folder."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageDownloader()
    window.show()
    sys.exit(app.exec())
