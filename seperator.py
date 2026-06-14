import cv2
import pytesseract
import numpy as np
from PIL import Image
import os

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def split_english_arabic(image_path, save_dir="debug_output"):
    os.makedirs(save_dir, exist_ok=True)
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Image not found or unreadable")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    results = pytesseract.image_to_data(
        gray, output_type=pytesseract.Output.DICT, lang="ara+eng", config="--psm 6"
    )

    arabic_img = image.copy()
    english_img = image.copy()

    for i in range(len(results["text"])):
        text = results["text"][i].strip()
        if not text:
            continue

        x, y, w, h = (
            results["left"][i],
            results["top"][i],
            results["width"][i],
            results["height"][i],
        )

        # Detect if contains Arabic script
        if any("\u0600" <= ch <= "\u06ff" for ch in text):
            cv2.rectangle(arabic_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            cv2.rectangle(english_img, (x, y), (x + w, y + h), (255, 0, 0), 2)

    cv2.imwrite(os.path.join(save_dir, "arabic_detected.jpg"), arabic_img)
    cv2.imwrite(os.path.join(save_dir, "english_detected.jpg"), english_img)
    print("✅ Saved both debug images in:", save_dir)


if __name__ == "__main__":
    split_english_arabic("sample text.png")
