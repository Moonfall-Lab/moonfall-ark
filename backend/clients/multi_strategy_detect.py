"""多策略 QR 码检测 DEMO
对同一张截图尝试多种预处理方法，看哪种能检测到 QR 码"""
import cv2
import numpy as np
from pathlib import Path

PHOTO = Path(__file__).resolve().parent / "capture_camera.png"
OUT_DIR = Path(__file__).resolve().parent


def preprocess_strategies(frame):
    """返回多种预处理结果，每种都是灰度图"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    strategies = {}

    # 原始灰度
    strategies["gray"] = gray

    # CLAHE 自适应直方图均衡化（增强对比度）
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    strategies["clahe"] = clahe.apply(gray)

    # 自适应阈值
    strategies["adaptive_thresh"] = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # OTSU 阈值
    _, strategies["otsu"] = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 高斯模糊 + 边缘
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    strategies["blurred"] = blurred

    # 放大 2x
    h, w = gray.shape
    big = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    strategies["upscale_2x"] = big

    # CLAHE + OTSU
    enhanced = clahe.apply(gray)
    _, strategies["clahe_otsu"] = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return strategies


def try_detect(img, detector, label):
    """尝试检测，返回 (found, points, decoded)"""
    results = []

    # 1. detect() — 只找位置
    have, pts = detector.detect(img)
    if have:
        results.append(f"{label} detect() OK, points shape={np.asarray(pts).shape}")

    # 2. detectAndDecode()
    text, pts2, straight = detector.detectAndDecode(img)
    if text:
        results.append(f"{label} decode='{text}'")

    # 3. detectAndDecodeMulti()
    ok, texts, pts3, straights = detector.detectAndDecodeMulti(img)
    if ok:
        real_texts = [t for t in texts if t]
        if real_texts:
            results.append(f"{label} multi={real_texts}")

    return results


def main():
    frame = cv2.imdecode(np.fromfile(str(PHOTO), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        print("cannot read photo")
        return

    h, w = frame.shape[:2]
    print(f"photo: {w}x{h}")

    detector = cv2.QRCodeDetector()
    strategies = preprocess_strategies(frame)

    all_results = []
    for name, img in strategies.items():
        results = try_detect(img, detector, name)
        all_results.extend(results)
        # 保存每个策略的结果图
        vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
        have, pts = detector.detect(img)
        if have and pts is not None:
            pts_int = np.asarray(pts, dtype=np.int32).reshape(-1, 2)
            cv2.polylines(vis, [pts_int], True, (0, 255, 0), 2)
            cv2.putText(vis, f"DETECTED: {name}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(vis, f"NOT FOUND: {name}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        out = OUT_DIR / f"strategy_{name}.png"
        cv2.imencode(".png", vis)[1].tofile(str(out))

    print(f"\n=== 检测结果 ===")
    if all_results:
        for r in all_results:
            print(f"  [OK] {r}")
    else:
        print("  [FAIL] 所有策略均未检测到 QR 码")
        print("\n  可能原因:")
        print("    1. QR 码在画面中太小 → 请靠近摄像头")
        print("    2. QR 码角度太大 → 请正对摄像头")
        print("    3. 光线不足或反光 → 请调整光线")
        print("    4. 对焦模糊 → 请按 'f' 重新对焦")

    print(f"\n策略结果图保存在: {OUT_DIR}\nstrategy_*.png")


if __name__ == "__main__":
    main()
