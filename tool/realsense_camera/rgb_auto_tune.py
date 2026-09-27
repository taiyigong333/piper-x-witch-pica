"""接近 RealSense Viewer 的 RGB 自动调参流程。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import load_realsense_config, parameter_output_path


def _option(rs: Any, name: str) -> Any:
    value = getattr(rs.option, name, None)
    if value is None:
        raise RuntimeError(f"当前 SDK 不提供 RealSense option：{name}")
    return value


def _sensor_name(rs: Any, sensor: Any) -> str:
    try:
        key = getattr(rs.camera_info, "name")
        if sensor.supports(key):
            return str(sensor.get_info(key))
    except Exception:
        pass
    return ""


def _find_rgb_sensor(rs: Any, device: Any) -> Any:
    """优先按 RGB Camera 名称选择，并用 RGB 专属 option 能力做最终确认。"""
    sensors = list(device.query_sensors())
    color_option = _option(rs, "enable_auto_exposure")
    awb_option = _option(rs, "enable_auto_white_balance")
    exposure_option = _option(rs, "exposure")
    named = [sensor for sensor in sensors if "rgb" in _sensor_name(rs, sensor).lower() or "color" in _sensor_name(rs, sensor).lower()]
    candidates = named + [sensor for sensor in sensors if sensor not in named]
    for sensor in candidates:
        # 深度 Stereo Module 可能也暴露 exposure；AWB 是 RGB sensor 的额外能力。
        if sensor.supports(color_option) and sensor.supports(awb_option) and sensor.supports(exposure_option):
            return sensor
    raise RuntimeError("未找到支持 RGB 自动曝光和曝光读取的 color sensor")


def _set(sensor: Any, option: Any, value: float) -> float:
    if sensor.is_option_read_only(option):
        raise RuntimeError("目标 option 只读")
    sensor.set_option(option, float(value))
    return float(sensor.get_option(option))


def initialize_realsense_rgb_auto_tuning(
    *,
    serial_number: str | None = None,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    convergence_frames: int = 60,
    lock_after_tuning: bool = False,
    sdk: Any | None = None,
) -> dict[str, Any]:
    """启动 RGB pipeline，执行 AE/AWB 收敛并返回稳定状态。

    返回值包含仍在运行的 ``pipeline``，调用方完成预览或保存后必须调用其 ``stop``。
    ``lock_after_tuning`` 会在读取稳定值后关闭 AE/AWB，并把稳定值写回 sensor。
    """
    if convergence_frames < 1:
        raise ValueError("convergence_frames 必须为正数")
    if sdk is None:
        try:
            import pyrealsense2 as sdk
        except ImportError as error:
            raise RuntimeError("缺少 pyrealsense2；请执行 uv sync --extra realsense。") from error

    pipeline = sdk.pipeline()
    stream_config = sdk.config()
    if serial_number:
        stream_config.enable_device(serial_number)
    stream_config.enable_stream(sdk.stream.color, int(width), int(height), sdk.format.bgr8, int(fps))
    profile = pipeline.start(stream_config)
    try:
        device = profile.get_device()
        sensor = _find_rgb_sensor(sdk, device)
        ae = _option(sdk, "enable_auto_exposure")
        awb = _option(sdk, "enable_auto_white_balance")
        exposure = _option(sdk, "exposure")
        gain = _option(sdk, "gain")
        white_balance = _option(sdk, "white_balance")
        _set(sensor, ae, 1.0)
        _set(sensor, awb, 1.0)
        for _ in range(convergence_frames):
            frames = pipeline.wait_for_frames(timeout_ms=1000)
            if not frames.get_color_frame():
                raise RuntimeError("自动调参阶段未获得 RGB frame")
        values = {
            "exposure": float(sensor.get_option(exposure)),
            "gain": float(sensor.get_option(gain)),
            "white_balance": float(sensor.get_option(white_balance)),
        }
        locked = False
        if lock_after_tuning:
            _set(sensor, ae, 0.0)
            _set(sensor, awb, 0.0)
            values["exposure"] = _set(sensor, exposure, values["exposure"])
            values["gain"] = _set(sensor, gain, values["gain"])
            values["white_balance"] = _set(sensor, white_balance, values["white_balance"])
            locked = True
        return {
            "pipeline": pipeline,
            "device": device,
            "sensor": sensor,
            "sensor_name": _sensor_name(sdk, sensor),
            "frames": convergence_frames,
            "locked": locked,
            "options": values,
            "enable_auto_exposure": float(sensor.get_option(ae)),
            "enable_auto_white_balance": float(sensor.get_option(awb)),
        }
    except Exception:
        pipeline.stop()
        raise


def _save_results(config: Any, results: dict[str, dict[str, Any]], name: str, purpose: str) -> Path:
    cameras = []
    for camera in config.cameras:
        item = {
            "name": camera.name, "driver": camera.driver, "model": camera.model,
            "serial_number": camera.serial_number, "width": camera.width, "height": camera.height,
            "fps": camera.fps, "color_order": camera.color_order, "enabled": camera.enabled,
            "align_depth_to_color": camera.align_depth_to_color,
            "options": results.get(camera.name, {}).get("config_options", camera.options),
        }
        if camera.depth_width is not None:
            item["depth_width"] = camera.depth_width
        if camera.depth_height is not None:
            item["depth_height"] = camera.depth_height
        cameras.append(item)
    output = parameter_output_path(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"purpose": purpose, "cameras": cameras}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RealSense RGB AE/AWB 自动收敛和可选锁定")
    parser.add_argument("--config", required=True, help="采集 YAML")
    parser.add_argument("--name", help="保存到 configs/camera/ 的 JSON 文件名")
    parser.add_argument("--purpose", default="RGB 自动调参结果")
    parser.add_argument("--frames", type=int, default=60, help="AE/AWB 收敛帧数，默认 60")
    parser.add_argument("--lock", action="store_true", help="读取稳定值后关闭 AE/AWB 并固定参数")
    args = parser.parse_args(argv)
    config = load_realsense_config(args.config)
    results: dict[str, dict[str, Any]] = {}
    try:
        for camera in config.enabled_cameras:
            result = initialize_realsense_rgb_auto_tuning(
                serial_number=camera.serial_number, width=camera.width, height=camera.height,
                fps=int(camera.fps), convergence_frames=args.frames, lock_after_tuning=args.lock,
            )
            result["config_options"] = ({"exposure": result["options"]["exposure"], "gain": result["options"]["gain"], "white_balance": result["options"]["white_balance"], "enable_auto_exposure": 0.0, "enable_auto_white_balance": 0.0} if args.lock else {"enable_auto_exposure": 1.0, "enable_auto_white_balance": 1.0})
            results[camera.name] = result
            print(f"{camera.name}: RGB={result['sensor_name'] or 'unknown'}, frames={args.frames}, options={result['options']}, locked={result['locked']}")
    finally:
        for result in results.values():
            result["pipeline"].stop()
    if args.name:
        print(f"已保存：{_save_results(config, results, args.name, args.purpose)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
