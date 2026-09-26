"""YAML 配置加载与启动前校验。

配置是采集行为的唯一入口：频率、模态、硬件和坐标变换不应散落在运行代码中。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

import yaml

from .errors import ConfigurationError

PoseRepresentation = Literal["xyz_xyzw", "xyz_rxryrz"]
InitialPoseMode = Literal["joint", "tcp"]


@dataclass(frozen=True)
class ModalityConfig:
    rgb: bool = True
    depth: bool = False
    arm_joint_positions: bool = True
    tcp_pose: bool = True
    gripper_position: bool = False


@dataclass(frozen=True)
class Hdf5Config:
    queue_size: int = 256
    batch_size: int = 16
    flush_every_batches: int = 10
    queue_put_timeout_s: float = 2.0
    jpeg_quality: int = 95


@dataclass(frozen=True)
class SessionConfig:
    output_root: Path
    data_type: Literal["real", "sim", "synthetic"]
    language_instruction: str
    collector_hash: str
    format_version: str = "1.0.0"
    trajectory_id: str | None = None
    batch_tag: int = 1
    camera_parameters_file: Path | None = None
    reverse_recording_enabled: bool = True
    duration_s: float | None = None
    sim_assets: str | None = None
    pose_representation: PoseRepresentation = "xyz_xyzw"
    hdf5: Hdf5Config = field(default_factory=Hdf5Config)


@dataclass(frozen=True)
class AcquisitionConfig:
    robot_hz: float = 60.0
    camera_rig_hz: float = 30.0
    max_alignment_age_ms: float = 100.0


@dataclass(frozen=True)
class CameraConfig:
    name: str
    driver: str
    model: str
    width: int
    height: int
    fps: float
    serial_number: str | None = None
    color_order: Literal["rgb", "bgr"] = "bgr"
    enabled: bool = True
    align_depth_to_color: bool = True
    depth_width: int | None = None
    depth_height: int | None = None
    base_to_camera: tuple[tuple[float, ...], ...] | None = None
    options: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class InitialPoseConfig:
    """遥操开始前的 Piper 起始位姿控制参数。"""

    enabled: bool = False
    mode: InitialPoseMode = "joint"
    joint_positions_rad: tuple[float, ...] | None = None
    tcp_pose: tuple[float, ...] | None = None
    speed_percent: int = 10
    timeout_s: float = 30.0
    joint_tolerance_rad: float = 0.035
    position_tolerance_m: float = 0.01
    orientation_tolerance_rad: float = 0.1


@dataclass(frozen=True)
class RobotConfig:
    name: str
    driver: str
    joint_count: int = 6
    can_name: str | None = None
    firmware_version: str = "default"
    tool_offset_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    base_to_robot: tuple[tuple[float, ...], ...] | None = None
    initial_pose: InitialPoseConfig = field(default_factory=InitialPoseConfig)


@dataclass(frozen=True)
class GripperConfig:
    enabled: bool = False
    driver: str = "none"


@dataclass(frozen=True)
class CollectConfig:
    session: SessionConfig
    modalities: ModalityConfig
    acquisition: AcquisitionConfig
    cameras: tuple[CameraConfig, ...]
    robot: RobotConfig
    gripper: GripperConfig
    source_path: Path

    @property
    def enabled_cameras(self) -> tuple[CameraConfig, ...]:
        return tuple(camera for camera in self.cameras if camera.enabled)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} 必须是对象。")
    return value


def _required(mapping: dict[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise ConfigurationError(f"缺少必填配置：{path}.{key}")
    return mapping[key]


def _positive_number(value: Any, path: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{path} 必须为正数。") from error
    if number <= 0:
        raise ConfigurationError(f"{path} 必须为正数。")
    return number


def _matrix(value: Any, path: str) -> tuple[tuple[float, ...], ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise ConfigurationError(f"{path} 必须为 4×4 数组或 null。")
    try:
        rows = tuple(tuple(float(item) for item in row) for row in value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{path} 必须为数值 4×4 数组。") from error
    if any(len(row) != 4 for row in rows):
        raise ConfigurationError(f"{path} 必须为 4×4 数组。")
    return rows


def _vector(value: Any, length: int, path: str) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != length:
        raise ConfigurationError(f"{path} 必须是含 {length} 个数值的数组或 null。")
    try:
        vector = tuple(float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{path} 必须是含 {length} 个数值的数组或 null。") from error
    if any(not math.isfinite(item) for item in vector):
        raise ConfigurationError(f"{path} 不能包含 NaN 或 Inf。")
    return vector


def _camera(value: Any, index: int) -> CameraConfig:
    path = f"cameras[{index}]"
    raw = _mapping(value, path)
    name = str(_required(raw, "name", path))
    if not name.startswith("camera_"):
        raise ConfigurationError(f"{path}.name 必须以 camera_ 开头。")
    color_order = str(raw.get("color_order", "bgr"))
    if color_order not in {"rgb", "bgr"}:
        raise ConfigurationError(f"{path}.color_order 只支持 rgb 或 bgr。")
    raw_options = raw.get("options", {})
    if not isinstance(raw_options, dict):
        raise ConfigurationError(f"{path}.options 必须是对象。")
    options: dict[str, float] = {}
    for option_name, option_value in raw_options.items():
        try:
            numeric_value = float(option_value)
        except (TypeError, ValueError) as error:
            raise ConfigurationError(f"{path}.options.{option_name} 必须是数值。") from error
        if not math.isfinite(numeric_value):
            raise ConfigurationError(f"{path}.options.{option_name} 不能是 NaN 或 Inf。")
        options[str(option_name)] = numeric_value
    return CameraConfig(
        name=name,
        driver=str(_required(raw, "driver", path)),
        model=str(_required(raw, "model", path)),
        width=int(_positive_number(_required(raw, "width", path), f"{path}.width")),
        height=int(_positive_number(_required(raw, "height", path), f"{path}.height")),
        fps=_positive_number(_required(raw, "fps", path), f"{path}.fps"),
        serial_number=str(raw["serial_number"]) if raw.get("serial_number") else None,
        color_order=color_order,  # type: ignore[arg-type]
        enabled=bool(raw.get("enabled", True)),
        align_depth_to_color=bool(raw.get("align_depth_to_color", True)),
        depth_width=int(raw["depth_width"]) if raw.get("depth_width") is not None else None,
        depth_height=int(raw["depth_height"]) if raw.get("depth_height") is not None else None,
        base_to_camera=_matrix(raw.get("base_to_camera"), f"{path}.base_to_camera"),
        options=options,
    )


def _initial_pose(value: Any, path: str) -> InitialPoseConfig:
    raw = _mapping(value, path)
    enabled = bool(raw.get("enabled", False))
    mode = str(raw.get("mode", "joint"))
    if mode not in {"joint", "tcp"}:
        raise ConfigurationError(f"{path}.mode 只支持 joint 或 tcp。")
    try:
        speed_percent = int(raw.get("speed_percent", 10))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{path}.speed_percent 必须是 1 到 100 的整数。") from error
    if not 1 <= speed_percent <= 100:
        raise ConfigurationError(f"{path}.speed_percent 必须是 1 到 100 的整数。")
    initial_pose = InitialPoseConfig(
        enabled=enabled,
        mode=mode,  # type: ignore[arg-type]
        joint_positions_rad=_vector(raw.get("joint_positions_rad"), 6, f"{path}.joint_positions_rad"),
        tcp_pose=_vector(raw.get("tcp_pose"), 6, f"{path}.tcp_pose"),
        speed_percent=speed_percent,
        timeout_s=_positive_number(raw.get("timeout_s", 30.0), f"{path}.timeout_s"),
        joint_tolerance_rad=_positive_number(
            raw.get("joint_tolerance_rad", 0.035), f"{path}.joint_tolerance_rad"
        ),
        position_tolerance_m=_positive_number(
            raw.get("position_tolerance_m", 0.01), f"{path}.position_tolerance_m"
        ),
        orientation_tolerance_rad=_positive_number(
            raw.get("orientation_tolerance_rad", 0.1), f"{path}.orientation_tolerance_rad"
        ),
    )
    if enabled:
        selected_target = (
            initial_pose.joint_positions_rad if initial_pose.mode == "joint" else initial_pose.tcp_pose
        )
        if selected_target is None:
            target_key = "joint_positions_rad" if initial_pose.mode == "joint" else "tcp_pose"
            raise ConfigurationError(f"启用 {path} 时必须填写 {path}.{target_key}。")
    return initial_pose


def load_config(path: str | Path) -> CollectConfig:
    """读取 YAML，并在接触真实设备前拒绝不完整或不安全配置。"""

    source_path = Path(path).expanduser().resolve()
    try:
        with source_path.open("r", encoding="utf-8") as file:
            raw = _mapping(yaml.safe_load(file), "根配置")
    except OSError as error:
        raise ConfigurationError(f"无法读取配置 {source_path}：{error}") from error

    session_raw = _mapping(_required(raw, "session", "根配置"), "session")
    hdf5_raw = _mapping(session_raw.get("hdf5", {}), "session.hdf5")
    data_type = str(_required(session_raw, "data_type", "session"))
    if data_type not in {"real", "sim", "synthetic"}:
        raise ConfigurationError("session.data_type 只支持 real、sim 或 synthetic。")
    pose_representation = str(session_raw.get("pose_representation", "xyz_xyzw"))
    if pose_representation not in {"xyz_xyzw", "xyz_rxryrz"}:
        raise ConfigurationError("session.pose_representation 只支持 xyz_xyzw 或 xyz_rxryrz。")
    output_root = Path(str(_required(session_raw, "output_root", "session")))
    if not output_root.is_absolute():
        output_root = (source_path.parent / output_root).resolve()
    batch_tag_value = _positive_number(session_raw.get("batch_tag", 1), "session.batch_tag")
    if not batch_tag_value.is_integer():
        raise ConfigurationError("session.batch_tag 必须是正整数。")
    session = SessionConfig(
        output_root=output_root,
        data_type=data_type,  # type: ignore[arg-type]
        language_instruction=str(_required(session_raw, "language_instruction", "session")),
        collector_hash=str(_required(session_raw, "collector_hash", "session")),
        format_version=str(session_raw.get("format_version", "1.0.0")),
        trajectory_id=str(session_raw["trajectory_id"]) if session_raw.get("trajectory_id") else None,
        batch_tag=int(batch_tag_value),
        camera_parameters_file=(
            (source_path.parent / str(session_raw["camera_parameters_file"])).resolve()
            if session_raw.get("camera_parameters_file") and not Path(str(session_raw["camera_parameters_file"])).is_absolute()
            else (Path(str(session_raw["camera_parameters_file"])).expanduser().resolve() if session_raw.get("camera_parameters_file") else None)
        ),
        reverse_recording_enabled=bool(session_raw.get("reverse_recording_enabled", True)),
        duration_s=_positive_number(session_raw["duration_s"], "session.duration_s") if session_raw.get("duration_s") is not None else None,
        sim_assets=str(session_raw["sim_assets"]) if session_raw.get("sim_assets") else None,
        pose_representation=pose_representation,  # type: ignore[arg-type]
        hdf5=Hdf5Config(
            queue_size=int(_positive_number(hdf5_raw.get("queue_size", 256), "session.hdf5.queue_size")),
            batch_size=int(_positive_number(hdf5_raw.get("batch_size", 16), "session.hdf5.batch_size")),
            flush_every_batches=int(_positive_number(hdf5_raw.get("flush_every_batches", 10), "session.hdf5.flush_every_batches")),
            queue_put_timeout_s=_positive_number(hdf5_raw.get("queue_put_timeout_s", 2.0), "session.hdf5.queue_put_timeout_s"),
            jpeg_quality=int(_positive_number(hdf5_raw.get("jpeg_quality", 95), "session.hdf5.jpeg_quality")),
        ),
    )
    if session.data_type == "sim" and not session.sim_assets:
        raise ConfigurationError("仿真数据必须配置 session.sim_assets。")
    if not 1 <= session.hdf5.jpeg_quality <= 100:
        raise ConfigurationError("session.hdf5.jpeg_quality 必须在 1 到 100 之间。")

    modalities_raw = _mapping(raw.get("modalities", {}), "modalities")
    modalities = ModalityConfig(
        **{key: bool(modalities_raw.get(key, getattr(ModalityConfig(), key))) for key in ModalityConfig.__dataclass_fields__}
    )
    if not modalities.rgb and not modalities.depth:
        raise ConfigurationError("采集系统以相机时间轴对齐，至少需要启用 RGB 或深度模态。")

    acquisition_raw = _mapping(raw.get("acquisition", {}), "acquisition")
    acquisition = AcquisitionConfig(
        robot_hz=_positive_number(acquisition_raw.get("robot_hz", 60.0), "acquisition.robot_hz"),
        camera_rig_hz=_positive_number(acquisition_raw.get("camera_rig_hz", 30.0), "acquisition.camera_rig_hz"),
        max_alignment_age_ms=_positive_number(
            acquisition_raw.get("max_alignment_age_ms", 100.0), "acquisition.max_alignment_age_ms"
        ),
    )

    cameras_raw = raw.get("cameras", [])
    if not isinstance(cameras_raw, list):
        raise ConfigurationError("cameras 必须为列表。")
    cameras = tuple(_camera(value, index) for index, value in enumerate(cameras_raw))
    if data_type == "real" and any(camera.driver == "realsense" for camera in cameras) and not session_raw.get("camera_parameters_file"):
        raise ConfigurationError("真实采集必须配置 session.camera_parameters_file，拒绝使用内嵌相机参数。")
    if session_raw.get("camera_parameters_file"):
        camera_path = session.camera_parameters_file
        try:
            parameter_payload = json.loads(camera_path.read_text(encoding="utf-8")) if camera_path else {}
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(f"无法读取相机参数文件 {camera_path}：{error}") from error
        parameter_cameras = parameter_payload.get("cameras") if isinstance(parameter_payload, dict) else None
        if not isinstance(parameter_cameras, list):
            raise ConfigurationError("相机参数文件必须包含 cameras 列表。")
        parameter_by_name = {str(item.get("name")): item for item in parameter_cameras if isinstance(item, dict) and item.get("name")}
        configured_names = {camera.name for camera in cameras}
        if set(parameter_by_name) != configured_names:
            raise ConfigurationError(
                "相机参数文件与 YAML 相机名称不一致："
                f"YAML={sorted(configured_names)}，JSON={sorted(parameter_by_name)}。"
            )
        for camera in cameras:
            item = parameter_by_name[camera.name]
            mismatches = []
            for field_name in ("driver", "model", "serial_number", "width", "height", "depth_width", "depth_height", "fps", "color_order", "enabled", "align_depth_to_color"):
                if field_name in item and item[field_name] != getattr(camera, field_name):
                    mismatches.append(f"{field_name}: YAML={getattr(camera, field_name)!r}, JSON={item[field_name]!r}")
            if mismatches:
                raise ConfigurationError(f"相机 {camera.name} 的 YAML 与参数文件不一致：{'；'.join(mismatches)}")
            options = item.get("options")
            if not isinstance(options, dict) or not options:
                raise ConfigurationError(f"相机参数文件必须为 {camera.name} 提供确定的 options。")
        cameras = tuple(
            replace(camera, options={str(k): float(v) for k, v in parameter_by_name[camera.name]["options"].items()})
            for camera in cameras
        )
    enabled_cameras = tuple(camera for camera in cameras if camera.enabled)
    if not enabled_cameras:
        raise ConfigurationError("启用图像模态时至少需要一台 enabled 相机。")
    names = [camera.name for camera in cameras]
    if len(names) != len(set(names)):
        raise ConfigurationError("相机名称不能重复。")
    slow = [camera.name for camera in enabled_cameras if camera.fps < acquisition.camera_rig_hz]
    if slow:
        raise ConfigurationError(
            f"相机标称 fps 低于 acquisition.camera_rig_hz：{', '.join(slow)}；会产生不可控重帧。"
        )

    robot_raw = _mapping(_required(raw, "robot", "根配置"), "robot")
    tool_offset = _vector(robot_raw.get("tool_offset_m", [0.0, 0.0, 0.0]), 3, "robot.tool_offset_m")
    if tool_offset is None:
        raise ConfigurationError("robot.tool_offset_m 必须为三个数值（m）。")
    robot = RobotConfig(
        name=str(_required(robot_raw, "name", "robot")),
        driver=str(_required(robot_raw, "driver", "robot")),
        joint_count=int(_positive_number(robot_raw.get("joint_count", 6), "robot.joint_count")),
        can_name=str(robot_raw["can_name"]) if robot_raw.get("can_name") else None,
        firmware_version=str(robot_raw.get("firmware_version", "default")).strip(),
        tool_offset_m=tool_offset,  # type: ignore[arg-type]
        base_to_robot=_matrix(robot_raw.get("base_to_robot"), "robot.base_to_robot"),
        initial_pose=_initial_pose(robot_raw.get("initial_pose", {}), "robot.initial_pose"),
    )
    if robot.driver == "piper_x":
        if robot.joint_count != 6:
            raise ConfigurationError("Piper-X 当前必须配置 robot.joint_count=6。")
        if not robot.can_name:
            raise ConfigurationError("Piper-X 需要配置 robot.can_name。")
        if robot.firmware_version not in {"default", "v183", "v188", "v189"}:
            raise ConfigurationError("robot.firmware_version 只支持 default、v183、v188 或 v189。")
        if robot.initial_pose.enabled and robot.initial_pose.mode == "tcp" and session.pose_representation != "xyz_rxryrz":
            raise ConfigurationError("Piper-X 的 robot.initial_pose.mode=tcp 需要 session.pose_representation=xyz_rxryrz。")
    elif robot.initial_pose.enabled:
        raise ConfigurationError("robot.initial_pose.enabled=true 当前仅支持 robot.driver=piper_x。")

    gripper_raw = _mapping(raw.get("gripper", {}), "gripper")
    gripper = GripperConfig(enabled=bool(gripper_raw.get("enabled", False)), driver=str(gripper_raw.get("driver", "none")))
    if modalities.gripper_position and not gripper.enabled:
        raise ConfigurationError("启用 gripper_position 时必须配置 gripper.enabled=true。")
    if gripper.enabled and gripper.driver == "none":
        raise ConfigurationError("启用夹爪时必须指定 gripper.driver。")
    if gripper.driver == "piper_x" and robot.driver != "piper_x":
        raise ConfigurationError("gripper.driver=piper_x 必须与 robot.driver=piper_x 一起使用。")

    return CollectConfig(session, modalities, acquisition, cameras, robot, gripper, source_path)


def camera_parameters_payload(config: CollectConfig) -> dict[str, Any]:
    """读取本次采集声明的相机参数文件，缺失时使用配置快照。"""
    path = config.session.camera_parameters_file
    if path is None:
        return {"cameras": [{key: value for key, value in camera.__dict__.items()} for camera in config.cameras]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"无法读取相机参数文件 {path}：{error}") from error
    if not isinstance(payload, dict):
        raise ConfigurationError(f"相机参数文件必须是 JSON 对象：{path}")
    return payload


def camera_parameters_digest(payload: dict[str, Any]) -> str:
    # 运行时设备快照会同步写回相机 JSON，不应改变静态采集配置的批次身份。
    stable_payload = {key: value for key, value in payload.items() if key not in {"devices", "runtime_snapshot"}}
    canonical = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_camera_runtime_parameters(path: Path | None, devices: dict[str, Any]) -> None:
    """将实机读取值同步保存到相机配置，静态配置字段保持不变。"""
    if path is None:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON 根节点必须是对象")
        payload["devices"] = devices
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ConfigurationError(f"无法保存相机运行参数到 {path}：{error}") from error
