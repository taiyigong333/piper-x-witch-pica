"""RealSense 工具共用的配置、设备启动和参数文件逻辑。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from taiyi_piper_x_collect.config import CollectConfig, load_config
from taiyi_piper_x_collect.devices.realsense import RealSenseCamera


def load_realsense_config(path: str | Path) -> CollectConfig:
    config = load_config(path)
    cameras = config.enabled_cameras
    if not cameras or any(camera.driver != "realsense" for camera in cameras):
        raise ValueError("输入采集配置必须包含至少一台 enabled 的 RealSense 相机。")
    return config


def start_cameras(config: CollectConfig, *, apply_options: bool) -> dict[str, RealSenseCamera]:
    cameras: dict[str, RealSenseCamera] = {}
    try:
        for camera_config in config.enabled_cameras:
            camera = RealSenseCamera(camera_config)
            camera.start(config.modalities.depth, apply_options=apply_options)
            cameras[camera_config.name] = camera
        return cameras
    except Exception:
        stop_cameras(cameras)
        raise


def stop_cameras(cameras: dict[str, RealSenseCamera]) -> None:
    for camera in cameras.values():
        try:
            camera.stop()
        except Exception:
            pass


def parameter_payload(config: CollectConfig, cameras: dict[str, RealSenseCamera], purpose: str) -> dict[str, Any]:
    """只保存输入采集配置涉及的相机和当前设备实际参数。"""

    camera_items = []
    for camera in config.cameras:
        running_camera = cameras.get(camera.name)
        item = {
            "name": camera.name,
            "driver": camera.driver,
            "model": camera.model,
            "serial_number": camera.serial_number,
            "width": camera.width,
            "height": camera.height,
            "fps": camera.fps,
            "color_order": camera.color_order,
            "enabled": camera.enabled,
            "align_depth_to_color": camera.align_depth_to_color,
            "options": (
                running_camera.parameters().get("configured_options", camera.options)
                if running_camera is not None
                else camera.options
            ),
        }
        if camera.depth_width is not None:
            item["depth_width"] = camera.depth_width
        if camera.depth_height is not None:
            item["depth_height"] = camera.depth_height
        if camera.base_to_camera is not None:
            item["base_to_camera"] = camera.base_to_camera
        camera_items.append(item)
    return {"purpose": purpose, "cameras": camera_items, "devices": {name: camera.parameters() for name, camera in cameras.items()}}


def parameter_output_path(name: str) -> Path:
    filename = Path(name)
    if filename.name != name or filename.suffix.lower() != ".json" or filename.name in {".", ".."}:
        raise ValueError("--name 必须是 configs/camera/ 下的 JSON 文件名，不能包含目录。")
    repository_root = Path(__file__).resolve().parents[2]
    return repository_root / "configs" / "camera" / filename.name


def save_payload(name: str, payload: dict[str, Any]) -> Path:
    output = parameter_output_path(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
