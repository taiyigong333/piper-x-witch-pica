"""预览 configs/camera 中已保存参数对应的 RealSense RGB 画面。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from taiyi_piper_x_collect.config import CameraConfig
from taiyi_piper_x_collect.devices.realsense import RealSenseCamera


def _parameter_path(name: str) -> Path:
    path = Path(name)
    if path.name != name or path.suffix.lower() != ".json":
        raise ValueError("参数文件必须是 configs/camera/ 下的 JSON 文件名")
    return Path(__file__).resolve().parents[2] / "configs" / "camera" / name


def _load_cameras(name: str) -> tuple[dict[str, Any], list[CameraConfig]]:
    path = _parameter_path(name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cameras = payload.get("cameras")
    if not isinstance(raw_cameras, list) or not raw_cameras:
        raise ValueError("参数文件必须包含非空 cameras 列表")
    cameras: list[CameraConfig] = []
    for index, raw in enumerate(raw_cameras):
        if not isinstance(raw, dict):
            raise ValueError(f"cameras[{index}] 必须是对象")
        if str(raw.get("driver", "realsense")) != "realsense":
            continue
        try:
            cameras.append(
                CameraConfig(
                    name=str(raw["name"]), driver="realsense", model=str(raw.get("model", "RealSense")),
                    serial_number=str(raw["serial_number"]) if raw.get("serial_number") else None,
                    width=int(raw["width"]), height=int(raw["height"]), fps=float(raw["fps"]),
                    color_order=str(raw.get("color_order", "bgr")), enabled=bool(raw.get("enabled", True)),
                    align_depth_to_color=bool(raw.get("align_depth_to_color", True)),
                    depth_width=int(raw["depth_width"]) if raw.get("depth_width") is not None else None,
                    depth_height=int(raw["depth_height"]) if raw.get("depth_height") is not None else None,
                    options={str(key): float(value) for key, value in dict(raw.get("options", {})).items()},
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"cameras[{index}] 字段无效：{error}") from error
    enabled = [camera for camera in cameras if camera.enabled]
    if not enabled:
        raise ValueError("参数文件没有 enabled 的 RealSense 相机")
    return payload, enabled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="预览已保存 RealSense 参数对应的相机画面")
    parser.add_argument("--name", required=True, help="configs/camera/ 下的 JSON 文件名")
    args = parser.parse_args(argv)
    payload, camera_configs = _load_cameras(args.name)
    cameras: dict[str, RealSenseCamera] = {}
    try:
        for config in camera_configs:
            camera = RealSenseCamera(config)
            camera.start(capture_depth=False, apply_options=True)
            cameras[config.name] = camera
        purpose = str(payload.get("purpose", ""))
        while True:
            for name, camera in cameras.items():
                image = np.asarray(camera.read().color).copy()
                cv2.putText(image, name, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
                if purpose:
                    cv2.putText(image, purpose[:90], (12, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                cv2.imshow(f"{name} | saved parameters | q: quit", image)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        cv2.destroyAllWindows()
        for camera in cameras.values():
            camera.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
