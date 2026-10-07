"""预览 configs/camera 中已保存参数对应的 RealSense RGB 画面。"""

from __future__ import annotations

import argparse
import copy
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


def _save_as(payload: dict[str, Any], camera_configs: list[CameraConfig], cameras: dict[str, RealSenseCamera], name: str, purpose: str, source_name: str) -> Path:
    """将当前编辑后的 options 写入新文件，禁止覆盖源参数文件。"""
    if name == source_name:
        raise ValueError("另存为文件名不能与当前参数文件相同")
    target = _parameter_path(name)
    updated = copy.deepcopy(payload)
    by_name = {config.name: config for config in camera_configs}
    for item in updated.get("cameras", []):
        if not isinstance(item, dict) or item.get("name") not in by_name:
            continue
        config = by_name[str(item["name"])]
        item["options"] = dict(config.options)
    updated["purpose"] = purpose
    target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _edit_from_terminal(config: CameraConfig, camera: RealSenseCamera) -> None:
    """允许直接输入数值；空输入保持当前值，输入错误不改变设备。"""
    print(f"正在编辑 {config.name}，直接回车保持当前值。")
    prompts = (
        ("exposure", "曝光"), ("gain", "增益"), ("white_balance", "白平衡"),
        ("enable_auto_exposure", "自动曝光(0/1)"), ("enable_auto_white_balance", "自动白平衡(0/1)"),
    )
    updates: dict[str, float] = {}
    for option_name, label in prompts:
        if option_name not in config.options:
            continue
        raw = input(f"{label} [{config.options[option_name]}]: ").strip()
        if not raw:
            continue
        try:
            value = float(raw)
            if option_name.startswith("enable_") and value not in (0.0, 1.0):
                raise ValueError("自动开关只能输入 0 或 1")
            if value < 0:
                raise ValueError("参数不能为负数")
            updates[option_name] = value
        except ValueError as error:
            print(f"{label} 输入无效：{error}")
    for option_name, value in updates.items():
        try:
            camera.set_option(option_name, value)
            config.options[option_name] = value
        except Exception as error:
            print(f"{option_name} 修改失败：{error}")


def _panel_button(panel: np.ndarray, y: int, label: str, value: str, x: int = 18) -> tuple[int, int, int, int]:
    left, top, right, bottom = x, y, 170, y + 34
    cv2.rectangle(panel, (left, top), (right, bottom), (65, 75, 90), -1)
    cv2.rectangle(panel, (left, top), (right, bottom), (140, 150, 165), 1)
    cv2.putText(panel, label, (left + 10, top + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 240), 1)
    cv2.putText(panel, value, (185, top + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (120, 230, 255), 1)
    return left, top, right, bottom


def _render_window(image: np.ndarray, config: CameraConfig, purpose: str) -> np.ndarray:
    panel_width = 390
    panel = np.full((image.shape[0], panel_width, 3), (30, 35, 45), dtype=np.uint8)
    cv2.putText(panel, config.name, (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (0, 255, 0), 2)
    cv2.putText(panel, "Camera parameters", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    _panel_button(panel, 78, "Exposure", f"{config.options.get('exposure', 0):.1f}")
    _panel_button(panel, 122, "Gain", f"{config.options.get('gain', 0):.1f}")
    _panel_button(panel, 166, "White balance", f"{config.options.get('white_balance', 0):.1f}")
    _panel_button(panel, 220, "Auto exposure", "ON" if config.options.get("enable_auto_exposure", 0) > 0.5 else "OFF")
    _panel_button(panel, 264, "Auto white balance", "ON" if config.options.get("enable_auto_white_balance", 0) > 0.5 else "OFF")
    cv2.rectangle(panel, (18, 320), (300, 362), (35, 115, 75), -1)
    cv2.putText(panel, "Save as new file", (35, 348), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (240, 255, 240), 1)
    cv2.putText(panel, "Click buttons to edit", (18, 405), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 190, 205), 1)
    cv2.putText(panel, "i: direct numeric input", (18, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 190, 205), 1)
    cv2.putText(panel, "q / ESC: quit", (18, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 190, 205), 1)
    if purpose:
        cv2.putText(panel, purpose[:42], (18, image.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (170, 180, 195), 1)
    return np.hstack((image, panel))


def _apply_panel_action(action: str, config: CameraConfig, camera: RealSenseCamera) -> None:
    actions = {
        "exposure_down": ("exposure", -10.0), "exposure_up": ("exposure", 10.0),
        "gain_down": ("gain", -1.0), "gain_up": ("gain", 1.0),
        "white_balance_down": ("white_balance", -100.0), "white_balance_up": ("white_balance", 100.0),
    }
    if action in actions:
        option, delta = actions[action]
        if option not in config.options:
            return
        value = max(0.0, config.options[option] + delta)
    elif action in {"auto_exposure", "auto_white_balance"}:
        option = "enable_auto_exposure" if action == "auto_exposure" else "enable_auto_white_balance"
        value = 0.0 if config.options.get(option, 0.0) > 0.5 else 1.0
    else:
        return
    camera.set_option(option, value)
    config.options[option] = value


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
        config_by_name = {config.name: config for config in camera_configs}
        names = list(cameras)
        save_request: list[str] = []

        def save_from_panel() -> None:
            try:
                output_name = input("请输入另存为文件名（configs/camera/ 下的 JSON）：").strip()
                output_purpose = input("请输入 purpose（直接回车沿用当前用途）：").strip() or purpose
                output = _save_as(payload, camera_configs, cameras, output_name, output_purpose, args.name)
                print(f"已另存为：{output}")
            except (EOFError, KeyboardInterrupt):
                print("已取消另存为。")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                print(f"另存为失败：{error}")

        def on_mouse(camera_name: str, event: int, x: int, y: int, _flags: int, _param: Any) -> None:
            if event != cv2.EVENT_LBUTTONUP:
                return
            config = config_by_name[camera_name]
            camera = cameras[camera_name]
            image_width = config.width
            panel_x = x - image_width
            if panel_x < 0:
                return
            action = None
            if 78 <= y < 112:
                action = "exposure_down" if panel_x < 195 else "exposure_up"
            elif 122 <= y < 156:
                action = "gain_down" if panel_x < 195 else "gain_up"
            elif 166 <= y < 200:
                action = "white_balance_down" if panel_x < 195 else "white_balance_up"
            elif 220 <= y < 254:
                action = "auto_exposure"
            elif 264 <= y < 298:
                action = "auto_white_balance"
            elif 320 <= y < 362:
                save_request.append("save")
            try:
                if action:
                    _apply_panel_action(action, config, camera)
            except Exception as error:
                print(f"{camera_name} 参数修改失败：{error}")
        for name in names:
            cv2.namedWindow(name, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(name, on_mouse, name)
        while True:
            for name, camera in cameras.items():
                image = np.asarray(camera.read().color).copy()
                config = config_by_name[name]
                cv2.imshow(name, _render_window(image, config, purpose))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("i") and names:
                try:
                    name = names[0]
                    _edit_from_terminal(config_by_name[name], cameras[name])
                except (EOFError, KeyboardInterrupt):
                    print("已取消直接输入。"); print()
                continue
            if key == ord("s"):
                save_request.append("save")
            if save_request:
                save_request.clear()
                save_from_panel()
                continue
            if key in (ord("q"), 27):
                break
    finally:
        cv2.destroyAllWindows()
        for camera in cameras.values():
            camera.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
