"""显示 RealSense 画面，启用自动曝光/白平衡后可保存当前参数。"""

from __future__ import annotations

import argparse
import time
from collections import deque

import cv2
import numpy as np

from .common import load_realsense_config, parameter_payload, save_payload, start_cameras, stop_cameras


def _image_metrics(image: np.ndarray) -> tuple[float, float, float]:
    """返回中心区域亮度、欠曝比例和过曝比例，避开边缘黑框影响自动调参判断。"""
    height, width = image.shape[:2]
    y0, y1 = height // 10, max(height // 10 + 1, height * 9 // 10)
    x0, x1 = width // 10, max(width // 10 + 1, width * 9 // 10)
    gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(np.mean(gray <= 8)), float(np.mean(gray >= 247))


def _stable(history: deque[tuple[float, float, float]], stable_frames: int) -> bool:
    if len(history) < stable_frames:
        return False
    values = np.asarray([item[0] for item in history], dtype=np.float32)
    dark = float(np.mean([item[1] for item in history]))
    bright = float(np.mean([item[2] for item in history]))
    # Viewer 的自动曝光也需要数帧收敛；亮度变化小且没有大面积饱和才认为可保存。
    return float(values.max() - values.min()) <= 4.0 and dark < 0.35 and bright < 0.35


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RealSense 预览和自动调参")
    parser.add_argument("--config", required=True, help="采集 YAML")
    parser.add_argument("--name", required=True, help="按 s 保存到 configs/camera/ 的 JSON 文件名")
    parser.add_argument("--purpose", required=True, help="保存到 JSON 的 purpose 字段")
    parser.add_argument("--warmup-s", type=float, default=2.0, help="启动后的预热秒数（默认 2）")
    parser.add_argument("--stable-frames", type=int, default=30, help="连续稳定帧数（默认 30）")
    args = parser.parse_args(argv)
    if args.warmup_s < 0 or args.stable_frames < 1:
        parser.error("--warmup-s 必须非负，--stable-frames 必须为正数")
    config = load_realsense_config(args.config)
    cameras = start_cameras(config, apply_options=False)
    histories = {name: deque(maxlen=args.stable_frames) for name in cameras}
    started_at = time.monotonic()
    try:
        # 自动调参由相机硬件持续完成；预览工具不改输入采集配置。
        for camera in cameras.values():
            for option, value in (("enable_auto_exposure", 1.0), ("enable_auto_white_balance", 1.0)):
                try:
                    camera.set_option(option, value)
                except Exception:
                    pass
        while True:
            warming = time.monotonic() - started_at < args.warmup_s
            for name, camera in cameras.items():
                frame = camera.read().color
                image = np.asarray(frame).copy()
                metrics = _image_metrics(image)
                if not warming:
                    histories[name].append(metrics)
                stable = not warming and _stable(histories[name], args.stable_frames)
                state = "预热中" if warming else ("稳定，可按 s 保存" if stable else "自动调参中")
                color = (0, 255, 0) if stable else (0, 200, 255)
                cv2.putText(image, f"{name} | {state}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
                cv2.putText(
                    image,
                    f"亮度 {metrics[0]:.1f}  欠曝 {metrics[1]:.1%}  过曝 {metrics[2]:.1%}  稳定帧 {len(histories[name])}/{args.stable_frames}",
                    (12, 55),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )
                cv2.imshow(f"{name} | s: save | q: quit", image)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                if warming or not all(_stable(history, args.stable_frames) for history in histories.values()):
                    print("自动调参尚未稳定，继续预览；稳定后再按 s 保存。")
                    continue
                for camera in cameras.values():
                    camera.refresh_parameters(config.modalities.depth)
                output = save_payload(args.name, parameter_payload(config, cameras, args.purpose))
                print(f"已保存 RealSense 当前参数：{output}")
            elif key == ord("q") or key == 27:
                break
    finally:
        cv2.destroyAllWindows()
        stop_cameras(cameras)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
