"""单台 RealSense 相机适配器，D405/D435 等型号共用此实现。"""

from __future__ import annotations

import numpy as np
from typing import Any

from ..config import CameraConfig
from ..errors import DeviceError, HardwareDependencyError
from ..models import CameraCalibration, CameraFrame
from .base import CameraDevice


class RealSenseCamera(CameraDevice):
    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._pipeline = None
        self._align = None
        self._calibration = CameraCalibration()
        self._parameters: dict[str, Any] = {}

    @staticmethod
    def _sdk():
        try:
            import pyrealsense2 as rs
        except ImportError as error:
            raise HardwareDependencyError("缺少 pyrealsense2；请执行 uv sync --extra realsense。") from error
        return rs

    def start(self, capture_depth: bool) -> None:
        rs = self._sdk()
        try:
            pipeline = rs.pipeline()
            stream_config = rs.config()
            if self._config.serial_number:
                stream_config.enable_device(self._config.serial_number)
            stream_config.enable_stream(
                rs.stream.color, self._config.width, self._config.height, rs.format.bgr8, int(self._config.fps)
            )
            if capture_depth:
                stream_config.enable_stream(
                    rs.stream.depth,
                    self._config.depth_width or self._config.width,
                    self._config.depth_height or self._config.height,
                    rs.format.z16,
                    int(self._config.fps),
                )
            profile = pipeline.start(stream_config)
            self._pipeline = pipeline
            device = profile.get_device()
            configured_options: dict[str, Any] = {}
            for option_name, option_value in self._config.options.items():
                option = self._resolve_option(rs, option_name)
                supported = False
                errors: list[str] = []
                for sensor in device.query_sensors():
                    if not sensor.supports(option):
                        continue
                    supported = True
                    try:
                        if sensor.is_option_read_only(option):
                            errors.append("option 只读")
                            continue
                        sensor.set_option(option, float(option_value))
                        configured_options[option_name] = float(sensor.get_option(option))
                    except Exception as error:
                        errors.append(str(error))
                if not supported or errors:
                    raise DeviceError(f"{self._config.name} 相机参数设置失败：{option_name}: {errors or ['sensor 不支持该 option']}")
            # 只保存本次配置实际使用的 options，避免快照写入 SDK 的完整能力目录。
            sensors = self._read_sensor_parameters(rs, device, configured_options)
            color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
            color_intrinsics = color_stream.get_intrinsics()
            calibration: dict[str, Any] = {
                "color_intrinsics": self._intrinsics_payload(color_intrinsics),
            }
            if capture_depth:
                depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
                calibration["depth_intrinsics"] = self._intrinsics_payload(depth_stream.get_intrinsics())
                calibration["depth_to_color_extrinsics"] = self._extrinsics_payload(
                    depth_stream.get_extrinsics_to(color_stream)
                )
            self._parameters = self._make_runtime_snapshot(
                rs, device, capture_depth, sensors, configured_options, calibration
            )
            self._calibration = CameraCalibration(
                matrix=np.array(
                    [[color_intrinsics.fx, 0.0, color_intrinsics.ppx], [0.0, color_intrinsics.fy, color_intrinsics.ppy], [0.0, 0.0, 1.0]],
                    dtype=np.float64,
                ),
                dist_coeffs=np.asarray(color_intrinsics.coeffs, dtype=np.float64),
            )
            self._pipeline = pipeline
            self._align = rs.align(rs.stream.color) if capture_depth and self._config.align_depth_to_color else None
        except Exception as error:
            self.stop()
            raise DeviceError(f"RealSense {self._config.name} 启动失败：{error}") from error

    def read(self) -> CameraFrame:
        if self._pipeline is None:
            raise DeviceError(f"RealSense {self._config.name} 尚未启动。")
        try:
            frames = self._pipeline.wait_for_frames(timeout_ms=1000)
            if self._align is not None:
                frames = self._align.process(frames)
            color_frame = frames.get_color_frame()
            if not color_frame:
                raise DeviceError(f"RealSense {self._config.name} 未获得 RGB 帧。")
            color = np.asanyarray(color_frame.get_data()).copy()
            depth_frame = frames.get_depth_frame()
            depth = np.asanyarray(depth_frame.get_data()).copy() if depth_frame else None
            return CameraFrame(color=color, depth=depth)
        except DeviceError:
            raise
        except Exception as error:
            raise DeviceError(f"RealSense {self._config.name} 取帧失败：{error}") from error

    def calibration(self) -> CameraCalibration:
        return self._calibration

    def parameters(self) -> dict[str, Any]:
        return dict(self._parameters)

    def _make_runtime_snapshot(
        self,
        rs: Any,
        device: Any,
        capture_depth: bool,
        sensors: list[dict[str, Any]],
        configured_options: dict[str, float],
        calibration: dict[str, Any],
    ) -> dict[str, Any]:
        streams: dict[str, Any] = {
            "color": {
                "width": self._config.width,
                "height": self._config.height,
                "fps": self._config.fps,
                "format": "bgr8",
            }
        }
        if capture_depth:
            streams["depth"] = {
                "width": self._config.depth_width or self._config.width,
                "height": self._config.depth_height or self._config.height,
                "fps": self._config.fps,
                "format": "z16",
            }
        result = {
            "device_info": self._device_info(rs, device),
            "sdk_version": getattr(rs, "__version__", None),
            "sensors": sensors,
            "streams": streams,
            "configured_options": configured_options,
            "calibration": calibration,
        }
        if capture_depth:
            result["depth_scale"] = self._depth_scale(rs, device)
        return result

    @staticmethod
    def _resolve_option(rs: Any, name: str) -> Any:
        """允许 JSON 使用 exposure/white_balance 或其大写拼写。"""
        normalized = name.strip().lower()
        option = getattr(rs.option, normalized, None)
        if option is None:
            raise DeviceError(f"未知 RealSense option：{name}")
        return option

    def _read_sensor_parameters(
        self, rs: Any, device: Any, configured_options: dict[str, float]
    ) -> list[dict[str, Any]]:
        """只读取本次采集配置中实际应用的传感器 option。"""
        records: list[dict[str, Any]] = []
        for sensor in device.query_sensors():
            options: dict[str, Any] = {}
            for name in configured_options:
                option = self._resolve_option(rs, name)
                if not sensor.supports(option):
                    continue
                item: dict[str, Any] = {"value": None}
                try:
                    item["value"] = float(sensor.get_option(option))
                except Exception:
                    pass
                options[name] = item
            if options:
                records.append({"info": self._selected_info_fields(rs, sensor, ("name",)), "options": options})
        return records

    @staticmethod
    def _device_info(rs: Any, device: Any) -> dict[str, Any]:
        return RealSenseCamera._selected_info_fields(
            rs, device, ("name", "serial_number", "firmware_version", "product_line")
        )

    @staticmethod
    def _selected_info_fields(rs: Any, info_provider: Any, fields: tuple[str, ...]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields:
            key = getattr(rs.camera_info, field, None)
            if key is None or callable(key):
                continue
            try:
                if info_provider.supports(key):
                    result[field] = info_provider.get_info(key)
            except Exception:
                continue
        return result

    @staticmethod
    def _depth_scale(rs: Any, device: Any) -> float | None:
        try:
            sensor = device.first_depth_sensor()
            if sensor and sensor.supports(rs.option.depth_units):
                return float(sensor.get_depth_scale())
        except Exception:
            pass
        return None

    @staticmethod
    def _intrinsics_payload(intrinsics: Any) -> dict[str, Any]:
        return {
            "width": int(intrinsics.width), "height": int(intrinsics.height),
            "fx": float(intrinsics.fx), "fy": float(intrinsics.fy),
            "ppx": float(intrinsics.ppx), "ppy": float(intrinsics.ppy),
            "model": str(intrinsics.model), "coeffs": [float(value) for value in intrinsics.coeffs],
        }

    @staticmethod
    def _extrinsics_payload(extrinsics: Any) -> dict[str, Any]:
        return {
            "rotation": [float(value) for value in extrinsics.rotation],
            "translation": [float(value) for value in extrinsics.translation],
        }

    def stop(self) -> None:
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            finally:
                self._pipeline = None
                self._align = None
                self._parameters = {}
