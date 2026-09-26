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
            status_value = vars(status.msg) if status is not None and hasattr(status, "msg") else None
        except Exception:
            status_value = None
        return {
            "joints_rad": list(joints.msg) if joints is not None and hasattr(joints, "msg") else None,
            "enabled": enabled,
            "arm_status": status_value,
        }

    def stop_hold(self) -> None:
        """以 pyAgxArm 的阻尼急停停止当前运动，保持当前位置，不发送 reset。"""

        self._require_arm().electronic_emergency_stop()

    def disable(self) -> None:
        self._require_arm().disable()

    def enable(self) -> bool:
        arm = self._require_arm()
        # 电子急停后的控制器仍处于 motion stop 状态，必须先由操作员确认安全再复位。
        arm.reset()
        return bool(arm.enable())
