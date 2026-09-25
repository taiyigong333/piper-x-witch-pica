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
            device = profile.get_device()
            sensors: list[dict[str, Any]] = []
            for sensor in device.query_sensors():
                options: dict[str, Any] = {}
                for option in sensor.get_supported_options():
                    try:
                        options[str(option)] = sensor.get_option(option)
                    except Exception:
                        options[str(option)] = None
                sensors.append({"name": sensor.get_info(rs.camera_info.name) if sensor.supports(rs.camera_info.name) else "", "options": options})
            self._parameters = {
                "name": device.get_info(rs.camera_info.name),
                "serial_number": device.get_info(rs.camera_info.serial_number),
                "firmware_version": device.get_info(rs.camera_info.firmware_version),
                "product_line": device.get_info(rs.camera_info.product_line),
                "sensors": sensors,
                "streams": {
                    "color": {"width": self._config.width, "height": self._config.height, "fps": self._config.fps, "format": "bgr8"},
                    "depth": {"enabled": capture_depth, "width": self._config.depth_width or self._config.width, "height": self._config.depth_height or self._config.height, "fps": self._config.fps, "format": "z16"},
                },
            }
            color_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
            intrinsics = color_profile.get_intrinsics()
            self._calibration = CameraCalibration(
                matrix=np.array(
                    [[intrinsics.fx, 0.0, intrinsics.ppx], [0.0, intrinsics.fy, intrinsics.ppy], [0.0, 0.0, 1.0]],
                    dtype=np.float64,
                ),
                dist_coeffs=np.asarray(intrinsics.coeffs, dtype=np.float64),
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

    def stop(self) -> None:
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            finally:
                self._pipeline = None
                self._align = None
                self._parameters = {}
