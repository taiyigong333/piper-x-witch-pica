"""Piper-X 的 pyAgxArm 反馈适配器。

采集连接只读取 CAN 广播反馈，不调用 enable、move 或夹爪控制 API。pyAgxArm 已经
将 Piper-X 的关节、法兰与原装夹爪宽度转换为 rad / m，适配器只负责 TCP 偏移和
采集格式转换。
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from ..config import RobotConfig
from ..errors import DeviceError, HardwareDependencyError
from ..models import RobotState
from .base import GripperDevice, RobotDevice


def euler_xyz_to_xyzw(euler_rad: np.ndarray) -> np.ndarray:
    """按 pyAgxArm 的 `Rz * Ry * Rx` 约定将 XYZ 欧拉角转四元数。"""

    rx, ry, rz = (float(value) for value in euler_rad)
    cx, sx = math.cos(rx / 2), math.sin(rx / 2)
    cy, sy = math.cos(ry / 2), math.sin(ry / 2)
    cz, sz = math.cos(rz / 2), math.sin(rz / 2)
    return np.asarray(
        [
            sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz,
        ],
        dtype=np.float64,
    )


def rotate_vector_xyzw(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """将 J6 坐标系中的工具偏移旋转至机器人基坐标系。"""

    x, y, z, w = (float(value) for value in quaternion)
    rotation = np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    return rotation @ vector


def read_piper_x_robot_state(arm: Any, config: RobotConfig, pose_representation: str) -> RobotState:
    """把 pyAgxArm 的 Piper-X 反馈转成数据集标准状态。"""

    joints_feedback = arm.get_joint_angles()
    flange_feedback = arm.get_flange_pose()
    if joints_feedback is None or flange_feedback is None:
        raise DeviceError("尚未收到完整 Piper-X 关节与法兰反馈。")
    joints_rad = np.asarray(joints_feedback.msg, dtype=np.float64)
    flange_pose = np.asarray(flange_feedback.msg, dtype=np.float64)
    if joints_rad.shape != (6,) or flange_pose.shape != (6,):
        raise DeviceError("Piper-X 反馈维度无效，期望六关节和六维法兰位姿。")
    position_m = flange_pose[:3]
    euler_rad = flange_pose[3:]
    quaternion = euler_xyz_to_xyzw(euler_rad)
    position_m = position_m + rotate_vector_xyzw(quaternion, np.asarray(config.tool_offset_m, dtype=np.float64))
    orientation = euler_rad if pose_representation == "xyz_rxryrz" else quaternion
    tcp_pose = np.concatenate((position_m, orientation))
    if not np.isfinite(joints_rad).all() or not np.isfinite(tcp_pose).all():
        raise DeviceError("Piper-X 返回 NaN 或 Inf。")
    return RobotState(timestamp=time.time(), joint_positions=joints_rad, tcp_pose=tcp_pose)


class PiperXRobot(RobotDevice):
    """通过 pyAgxArm 读取 Piper-X CAN 反馈，严格不下发运动或使能指令。"""

    def __init__(self, config: RobotConfig, pose_representation: str) -> None:
        if pose_representation not in {"xyz_xyzw", "xyz_rxryrz"}:
            raise DeviceError("Piper-X 仅支持 xyz_xyzw 或 xyz_rxryrz。")
        self._config = config
        self._pose_representation = pose_representation
        self._arm: Any | None = None
        self._gripper: Any | None = None

    def start(self) -> None:
        if self._arm is not None:
            return
        try:
            from pyAgxArm import AgxArmFactory, ArmModel, create_agx_arm_config
        except ImportError as error:
            raise HardwareDependencyError("缺少 pyAgxArm；请执行 uv sync --extra dev --extra realsense。") from error
        try:
            arm_config = create_agx_arm_config(
                robot=ArmModel.PIPER_X,
                firmeware_version=self._config.firmware_version,
                interface="socketcan",
                channel=self._config.can_name,
            )
            arm = AgxArmFactory.create_arm(arm_config)
            arm.connect()
            self._arm = arm
        except Exception as error:
            self.stop()
            raise DeviceError(f"Piper-X CAN 接口 {self._config.can_name} 启动失败：{error}") from error

    def read(self) -> RobotState:
        if self._arm is None:
            raise DeviceError("Piper-X 尚未启动。")
        try:
            return read_piper_x_robot_state(self._arm, self._config, self._pose_representation)
        except DeviceError:
            raise
        except Exception as error:
            raise DeviceError(f"Piper-X 反馈读取失败：{error}") from error

    def read_gripper_position(self) -> float:
        """读取 Piper-X 原装 AGX 夹爪开口宽度（m），不发送夹爪控制帧。"""

        gripper = self._require_gripper()
        try:
            feedback = gripper.get_gripper_status()
            if feedback is None:
                raise DeviceError("尚未收到 Piper-X 原装夹爪反馈。")
            if getattr(feedback.msg, "mode", None) != "width":
                raise DeviceError("Piper-X 原装夹爪未处于 width 反馈模式，不能将角度写成米。")
            position_m = float(feedback.msg.value)
            if not math.isfinite(position_m) or position_m < 0:
                raise DeviceError("Piper-X 原装夹爪反馈返回无效开口宽度。")
            return position_m
        except DeviceError:
            raise
        except Exception as error:
            raise DeviceError(f"Piper-X 原装夹爪反馈读取失败：{error}") from error

    def wait_for_gripper_feedback(self, timeout_s: float = 1.0) -> float:
        """等待原装夹爪首帧，避免在启动时写入不存在的反馈。"""

        deadline = time.monotonic() + timeout_s
        last_error: DeviceError | None = None
        while time.monotonic() < deadline:
            try:
                return self.read_gripper_position()
            except DeviceError as error:
                last_error = error
                time.sleep(0.005)
        raise DeviceError(f"等待 Piper-X 原装夹爪反馈超时（{timeout_s:.1f} 秒）。") from last_error

    def stop(self) -> None:
        self._gripper = None
        if self._arm is not None:
            try:
                self._arm.disconnect()
            finally:
                self._arm = None

    def _require_gripper(self) -> Any:
        if self._arm is None:
            raise DeviceError("Piper-X 尚未启动。")
        if self._gripper is None:
            try:
                self._gripper = self._arm.init_effector(self._arm.OPTIONS.EFFECTOR.AGX_GRIPPER)
            except Exception as error:
                raise DeviceError(f"Piper-X 原装夹爪初始化失败：{error}") from error
        return self._gripper


class PiperXGripper(GripperDevice):
    """复用 PiperXRobot 的单一 CAN 连接读取原装夹爪状态。"""

    def __init__(self, robot: PiperXRobot) -> None:
        self._robot = robot
        self._started = False

    def start(self) -> None:
        self._robot.wait_for_gripper_feedback()
        self._started = True

    def read_position(self) -> float:
        if not self._started:
            raise DeviceError("Piper-X 原装夹爪尚未启动。")
        return self._robot.read_gripper_position()

    def stop(self) -> None:
        self._started = False
