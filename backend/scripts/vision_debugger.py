import cv2
import time
import os

IMAGE_PATH = "../latest_vision_input.jpg"  # backend/latest_vision_input.jpg

print(f"Watching {IMAGE_PATH} for changes...")

last_mtime = 0

cv2.namedWindow("Vision Debugger", cv2.WINDOW_NORMAL)

while True:
    try:
        if os.path.exists(IMAGE_PATH):
            mtime = os.path.getmtime(IMAGE_PATH)
            if mtime != last_mtime:
                img = cv2.imread(IMAGE_PATH)
                if img is not None:
                    raw_h, raw_w = img.shape[:2]
                    print(f"[Vision Debugger] loaded image: {raw_w}x{raw_h}")
                    # Resize if too large
                    h, w = img.shape[:2]
                    max_w, max_h = 1000, 600
                    if w > max_w or h > max_h:
                        scale = min(max_w / w, max_h / h)
                        img = cv2.resize(img, (int(w * scale), int(h * scale)))
                    cv2.imshow("Vision Debugger", img)
                last_mtime = mtime

        # 100ms wait
        if cv2.waitKey(100) & 0xFF == ord("q"):
            break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(1)

cv2.destroyAllWindows()
