import cv2
import numpy as np
from ultralytics import YOLO

# Load YOLO model (use a custom trained one ideally)
model = YOLO("yolov8n.pt")  # replace with your trained doc model for best results

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def four_point_transform(image, pts):
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = int(max(widthA, widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = int(max(heightA, heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (maxWidth, maxHeight))

def detect_document(image):
    results = model(image)[0]

    if len(results.boxes) == 0:
        return None

    # Take largest box
    boxes = results.boxes.xyxy.cpu().numpy()
    areas = [(x2-x1)*(y2-y1) for x1,y1,x2,y2 in boxes]
    best = boxes[np.argmax(areas)]

    x1, y1, x2, y2 = map(int, best)
    return x1, y1, x2, y2

def refine_corners(image, box):
    x1, y1, x2, y2 = box
    roi = image[y1:y2, x1:x2]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    edged = cv2.Canny(blur, 50, 150)

    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        if len(approx) == 4:
            pts = approx.reshape(4,2)
            pts[:,0] += x1
            pts[:,1] += y1
            return pts

    # fallback to box corners
    return np.array([
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2]
    ], dtype="float32")

def scan(image_path, output_path="yolo_scan.png"):
    image = cv2.imread(image_path)
    if image is None:
        print("❌ Image not found")
        return

    box = detect_document(image)

    if box is None:
        print("⚠️ YOLO failed → fallback to full image")
        pts = np.array([
            [0,0],
            [image.shape[1],0],
            [image.shape[1],image.shape[0]],
            [0,image.shape[0]]
        ], dtype="float32")
    else:
        pts = refine_corners(image, box)

    warped = four_point_transform(image, pts)

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    scanned = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15, 3
    )

    cv2.imwrite(output_path, scanned)
    print(f"✅ Saved: {output_path}")

if __name__ == "__main__":
    scan(r"D:\AMAVA\AGENT\AMAVAGENT\input.webp")