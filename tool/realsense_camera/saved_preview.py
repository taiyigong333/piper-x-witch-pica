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
        selected = 0
        config_by_name = {config.name: config for config in camera_configs}
        names = list(cameras)
        while True:
            for index, (name, camera) in enumerate(cameras.items()):
                image = np.asarray(camera.read().color).copy()
                config = config_by_name[name]
                marker = "[selected]" if index == selected else ""
                cv2.putText(image, f"{name} {marker}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                if purpose:
                    cv2.putText(image, purpose[:90], (12, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                options = config.options
                cv2.putText(
                    image,
                    f"exp={options.get('exposure', 0):.1f} gain={options.get('gain', 0):.1f} wb={options.get('white_balance', 0):.1f} AE={int(options.get('enable_auto_exposure', 0))} AWB={int(options.get('enable_auto_white_balance', 0))}",
                    (12, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1,
                )
                if index == selected:
                    cv2.putText(image, "Tab camera | i input | e/E exp | g/G gain | w/W WB | a AE | b AWB | s save | q quit", (12, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1)
                cv2.imshow(f"{name} | saved parameters | q: quit", image)
            key = cv2.waitKey(1) & 0xFF
            if key == 9 and names:
                selected = (selected + 1) % len(names)
                continue
            name = names[selected]
            config = config_by_name[name]
            camera = cameras[name]
            if key == ord("i"):
                try:
                    _edit_from_terminal(config, camera)
                except (EOFError, KeyboardInterrupt):
                    print("已取消直接输入。"); print()
                continue
            option_actions = {
                ord("e"): ("exposure", -10.0), ord("E"): ("exposure", 10.0),
                ord("g"): ("gain", -1.0), ord("G"): ("gain", 1.0),
                ord("w"): ("white_balance", -100.0), ord("W"): ("white_balance", 100.0),
            }
            if key in option_actions:
                option_name, delta = option_actions[key]
                if option_name not in config.options:
                    print(f"{name} 未保存 {option_name}，无法调整。")
                    continue
                value = max(0.0, config.options[option_name] + delta)
                try:
                    camera.set_option(option_name, value)
                    config.options[option_name] = value
                except Exception as error:
                    print(f"{name} 修改 {option_name} 失败：{error}")
                continue
            if key == ord("a") or key == ord("b"):
                option_name = "enable_auto_exposure" if key == ord("a") else "enable_auto_white_balance"
                value = 0.0 if config.options.get(option_name, 0.0) > 0.5 else 1.0
                try:
                    camera.set_option(option_name, value)
                    config.options[option_name] = value
                except Exception as error:
                    print(f"{name} 修改 {option_name} 失败：{error}")
                continue
            if key == ord("s"):
                try:
                    output_name = input("请输入另存为文件名（configs/camera/ 下的 JSON）：").strip()
                    output_purpose = input("请输入 purpose（直接回车沿用当前用途）：").strip() or purpose
                    output = _save_as(payload, camera_configs, cameras, output_name, output_purpose, args.name)
                    print(f"已另存为：{output}")
                except (EOFError, KeyboardInterrupt):
                    print("已取消另存为。")
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    print(f"另存为失败：{error}")
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
