"""Piper-X 控制层；只调用本仓库 pyAgxArm，不依赖或修改 pika_ros。"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any


def _load_pyagxarm():
    """优先加载仓库内 SDK，避免 ROS 工作空间的同名命名空间遮蔽它。"""

    repository_sdk = Path(__file__).resolve().parents[2] / "pyAgxArm"
    sdk_path = str(repository_sdk)
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)
    existing = sys.modules.get("pyAgxArm")
    if existing is not None and not hasattr(existing, "AgxArmFactory"):
        del sys.modules["pyAgxArm"]
    from pyAgxArm import AgxArmFactory, ArmModel, create_agx_arm_config

    return AgxArmFactory, ArmModel, create_agx_arm_config


class PiperXControl:
    def __init__(self, *, can_name: str = "can0", firmware_version: str = "default") -> None:
        self.can_name = can_name
        self.firmware_version = firmware_version
        self.arm: Any | None = None
        self.gripper: Any | None = None

    def connect(self, *, wait_timeout_s: float = 5.0) -> None:
        if self.arm is not None:
            self.close()
        AgxArmFactory, ArmModel, create_agx_arm_config = _load_pyagxarm()

        config = create_agx_arm_config(
            robot=ArmModel.PIPER_X,
            firmeware_version=self.firmware_version,
            interface="socketcan",
            channel=self.can_name,
        )
        try:
            self.arm = AgxArmFactory.create_arm(config)
            self.arm.connect()
            # 夹爪反馈与机械臂共用同一条 CAN 连接，只初始化读取驱动，不发送控制帧。
            try:
                self.gripper = self.arm.init_effector(self.arm.OPTIONS.EFFECTOR.AGX_GRIPPER)
            except Exception:
                # 夹爪不可用时仍允许读取机械臂状态，GUI 会将夹爪状态显示为 None。
                self.gripper = None
            deadline = time.monotonic() + wait_timeout_s
            while time.monotonic() < deadline:
                feedback = self.arm.get_joint_angles()
                if feedback is not None and getattr(feedback, "msg", None) is not None:
                    return
                time.sleep(0.05)
            raise RuntimeError(
                f"CAN 已打开但 {self.can_name} 未收到 Piper-X 关节反馈；"
                "请检查 CAN 接口、终端电阻、线缆、机械臂电源和固件版本。"
            )
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.arm is not None:
            self.arm.disconnect()
            self.arm = None
            self.gripper = None

    def _require_arm(self) -> Any:
        if self.arm is None:
            raise RuntimeError("尚未连接 Piper-X")
        return self.arm

    def read_status(self) -> dict[str, Any]:
        arm = self._require_arm()
        joints = arm.get_joint_angles()
        if joints is None or not hasattr(joints, "msg"):
            raise RuntimeError(f"{self.can_name} 未收到 Piper-X 关节反馈，请检查 CAN 总线和机械臂电源。")
        try:
            enabled = list(arm.get_joints_enable_status_list())
        except Exception:
            enabled = None
        try:
            status = arm.get_arm_status()
            status_value = _to_value(status.msg) if status is not None and hasattr(status, "msg") else None
        except Exception:
            status_value = None
        try:
            flange = arm.get_flange_pose()
            flange_value = _to_value(flange.msg) if flange is not None and hasattr(flange, "msg") else None
        except Exception:
            flange_value = None
        try:
            gripper = self.gripper or arm.init_effector(arm.OPTIONS.EFFECTOR.AGX_GRIPPER)
            self.gripper = gripper
            feedback = gripper.get_gripper_status()
            gripper_value = _to_value(feedback.msg) if feedback is not None and hasattr(feedback, "msg") else None
        except Exception:
            gripper_value = None
        return {
            "joints_rad": _to_value(joints.msg) if joints is not None and hasattr(joints, "msg") else None,
            "flange_pose": flange_value,
            "gripper": gripper_value,
            "enabled": enabled,
            "arm_status": status_value,
        }

    def stop_hold(self) -> None:
        """以阻尼急停停止当前运动并保持当前位置，不使能/失能电机。"""

        self._require_arm().electronic_emergency_stop()

    def disable(self) -> None:
        self._require_arm().disable()

    def enable(self) -> bool:
        arm = self._require_arm()
        # 电子急停后的控制器仍处于 motion stop 状态，必须先由操作员确认安全再复位。
        arm.reset()
        return bool(arm.enable())


def _to_value(value: Any) -> Any:
    """把 SDK 反馈对象转换为 GUI 可显示的基础 Python 值。"""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_to_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_value(item) for key, item in value.items()}
    try:
        return {str(key): _to_value(item) for key, item in vars(value).items() if not key.startswith("_")}
    except TypeError:
        return str(value)
