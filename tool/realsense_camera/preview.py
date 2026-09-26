"""显示 RealSense 画面，启用自动曝光/白平衡后可保存当前参数。"""

from __future__ import annotations

import argparse
import cv2
import numpy as np

from .common import load_realsense_config, parameter_payload, save_payload, start_cameras, stop_cameras


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RealSense 预览和自动调参")
    parser.add_argument("--config", required=True, help="采集 YAML")
    parser.add_argument("--name", required=True, help="按 s 保存到 configs/camera/ 的 JSON 文件名")
    parser.add_argument("--purpose", required=True, help="保存到 JSON 的 purpose 字段")
    args = parser.parse_args(argv)
    config = load_realsense_config(args.config)
    cameras = start_cameras(config, apply_options=False)
    try:
        # 自动调参由相机硬件持续完成；预览工具不改输入采集配置。
        for camera in cameras.values():
            for option, value in (("enable_auto_exposure", 1.0), ("enable_auto_white_balance", 1.0)):
                try:
                    camera.set_option(option, value)
                except Exception:
                    pass
        while True:
            for name, camera in cameras.items():
                frame = camera.read().color
                image = np.asarray(frame).copy()
                cv2.putText(image, name, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow(f"{name} | s: save | q: quit", image)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
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
