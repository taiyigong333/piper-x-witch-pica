"""Piper-X 起始位姿控制，仅由遥操会话在 ROS 启动前显式调用。"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

import numpy as np

from ..config import InitialPoseConfig, RobotConfig
from ..errors import DeviceError, HardwareDependencyError
from ..models import RobotState
from .piper_x import read_piper_x_robot_state


_COMMAND_INTERVAL_S = 0.05


class PiperXInitialPoseController:
    """使用 pyAgxArm 的 Piper-X 运动 API 移至显式配置的安全起始位姿。"""

    def __init__(
        self,
        robot_config: RobotConfig,
        initial_pose: InitialPoseConfig,
        *,
        arm_factory: Callable[[], Any] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._robot_config = robot_config
        self._initial_pose = initial_pose
        self._arm_factory = arm_factory
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._arm: Any | None = None

    def move(self) -> RobotState:
        if not self._initial_pose.enabled:
            raise DeviceError("robot.initial_pose.enabled=false，拒绝发送 Piper-X 起始位姿控制指令。")
        target = self._target()
        self._connect()
        target_sent = False
        try:
            self._wait_until_enabled()
            assert self._arm is not None
            self._arm.set_speed_percent(self._initial_pose.speed_percent)
            if self._initial_pose.mode == "joint":
                self._arm.move_j(target.tolist())
            else:
                self._arm.set_tcp_offset([*self._robot_config.tool_offset_m, 0.0, 0.0, 0.0])
                self._arm.move_p(self._arm.get_tcp2flange_pose(target.tolist()))
            target_sent = True
            deadline = self._monotonic() + self._initial_pose.timeout_s
            while self._monotonic() < deadline:
                state = self._read_state()
                if self._reached_target(state, target):
                    return state
                self._sleep(_COMMAND_INTERVAL_S)
            raise DeviceError(f"Piper-X 未在 {self._initial_pose.timeout_s:.1f} 秒内到达配置的起始位姿。")
        except DeviceError:
            if target_sent:
                self._emergency_stop()
            raise
        except Exception as error:
            if target_sent:
                self._emergency_stop()
            raise DeviceError(f"Piper-X 起始位姿控制失败：{error}") from error
        finally:
            self.stop()

    def stop(self) -> None:
        if self._arm is not None:
            try:
                self._arm.disconnect()
            finally:
                self._arm = None

    def _connect(self) -> None:
        try:
            if self._arm_factory is not None:
                arm = self._arm_factory()
            else:
                from pyAgxArm import AgxArmFactory, ArmModel, create_agx_arm_config

                config = create_agx_arm_config(
                    robot=ArmModel.PIPER_X,
                    firmeware_version=self._robot_config.firmware_version,
                    interface="socketcan",
                    channel=self._robot_config.can_name,
                )
                arm = AgxArmFactory.create_arm(config)
            arm.connect()
            self._arm = arm
        except ImportError as error:
            raise HardwareDependencyError("缺少 pyAgxArm；请执行 uv sync 安装项目依赖。") from error
        except Exception as error:
            self.stop()
            raise DeviceError(f"Piper-X CAN 接口 {self._robot_config.can_name} 控制连接失败：{error}") from error

    def _wait_until_enabled(self) -> None:
        assert self._arm is not None
        deadline = self._monotonic() + min(self._initial_pose.timeout_s, 10.0)
        while self._monotonic() < deadline:
            if bool(self._arm.enable()):
                return
            self._sleep(_COMMAND_INTERVAL_S)
        raise DeviceError("Piper-X 使能超时，未发送起始位姿目标。")

    def _target(self) -> np.ndarray:
        values = self._initial_pose.joint_positions_rad if self._initial_pose.mode == "joint" else self._initial_pose.tcp_pose
        if values is None:
            key = "joint_positions_rad" if self._initial_pose.mode == "joint" else "tcp_pose"
            raise DeviceError(f"缺少 robot.initial_pose.{key}。")
        return np.asarray(values, dtype=np.float64)

    def _emergency_stop(self) -> None:
        """目标发送后发生超时或错误时停止本次主动运动，不执行会导致下坠的 disable。"""

        if self._arm is None:
            return
        try:
            self._arm.electronic_emergency_stop()
        except Exception:
            pass

    def _read_state(self) -> RobotState:
        assert self._arm is not None
        return read_piper_x_robot_state(self._arm, self._robot_config, "xyz_rxryrz")

    def _reached_target(self, state: RobotState, target: np.ndarray) -> bool:
        if self._initial_pose.mode == "joint":
            return bool(np.max(np.abs(state.joint_positions - target)) <= self._initial_pose.joint_tolerance_rad)
        assert state.tcp_pose is not None
        position_error = float(np.linalg.norm(state.tcp_pose[:3] - target[:3]))
        orientation_error = _wrapped_angle_error(state.tcp_pose[3:] - target[3:])
        return (
            position_error <= self._initial_pose.position_tolerance_m
            and orientation_error <= self._initial_pose.orientation_tolerance_rad
        )


def _wrapped_angle_error(delta: np.ndarray) -> float:
    wrapped = (np.asarray(delta, dtype=np.float64) + math.pi) % (2.0 * math.pi) - math.pi
    return float(np.max(np.abs(wrapped)))
