from __future__ import annotations

import math
from types import SimpleNamespace

from taiyi_piper_x_collect.config import InitialPoseConfig, RobotConfig
from taiyi_piper_x_collect.devices.piper_x_motion import PiperXInitialPoseController


class FakePiperXArm:
    def __init__(self, joints: list[float], flange_pose: list[float]) -> None:
        self.joints = joints
        self.flange_pose = flange_pose
        self.connected = False
        self.speed: int | None = None
        self.joint_commands: list[list[float]] = []
        self.pose_commands: list[list[float]] = []
        self.tcp_offsets: list[list[float]] = []
        self.emergency_stops = 0

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def enable(self) -> bool:
        return True

    def set_speed_percent(self, speed: int) -> None:
        self.speed = speed

    def move_j(self, joints: list[float]) -> None:
        self.joint_commands.append(joints)

    def set_tcp_offset(self, offset: list[float]) -> None:
        self.tcp_offsets.append(offset)

    def get_tcp2flange_pose(self, pose: list[float]) -> list[float]:
        return [pose[0], pose[1] - 0.1, *pose[2:]]

    def move_p(self, pose: list[float]) -> None:
        self.pose_commands.append(pose)

    def electronic_emergency_stop(self) -> None:
        self.emergency_stops += 1

    def get_joint_angles(self):
        return SimpleNamespace(msg=self.joints)

    def get_flange_pose(self):
        return SimpleNamespace(msg=self.flange_pose)


def test_joint_initial_pose_uses_piper_x_si_api_and_disconnects() -> None:
    target = [0.1, 0.2, -0.2, 0.3, -0.2, 0.5]
    arm = FakePiperXArm(target, [0.3, 0.0, 0.2, 0.0, 0.0, 0.0])
    controller = PiperXInitialPoseController(
        RobotConfig(name="piper_x", driver="piper_x", can_name="can0"),
        InitialPoseConfig(enabled=True, mode="joint", joint_positions_rad=tuple(target)),
        arm_factory=lambda: arm,
    )

    state = controller.move()

    assert arm.speed == 10
    assert arm.joint_commands == [target]
    assert not arm.connected
    assert state.joint_positions.tolist() == target


def test_tcp_initial_pose_uses_sdk_tcp_to_flange_conversion() -> None:
    target = [0.2, 0.2, 0.3, 0.0, 0.0, math.pi / 2]
    arm = FakePiperXArm([0.0] * 6, [0.2, 0.1, 0.3, 0.0, 0.0, math.pi / 2])
    controller = PiperXInitialPoseController(
        RobotConfig(name="piper_x", driver="piper_x", can_name="can0", tool_offset_m=(0.1, 0.0, 0.0)),
        InitialPoseConfig(enabled=True, mode="tcp", tcp_pose=tuple(target)),
        arm_factory=lambda: arm,
    )

    controller.move()

    assert arm.tcp_offsets == [[0.1, 0.0, 0.0, 0.0, 0.0, 0.0]]
    assert arm.pose_commands == [[0.2, 0.1, 0.3, 0.0, 0.0, math.pi / 2]]


def test_joint_timeout_reports_feedback_and_triggers_emergency_stop() -> None:
    arm = FakePiperXArm([0.0] * 6, [0.3, 0.0, 0.2, 0.0, 0.0, 0.0])
    ticks = iter([0.0, 0.0, 0.1, 1.1])
    controller = PiperXInitialPoseController(
        RobotConfig(name="piper_x", driver="piper_x", can_name="can0"),
        InitialPoseConfig(enabled=True, mode="joint", joint_positions_rad=(0.1,) * 6, timeout_s=1),
        arm_factory=lambda: arm,
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: next(ticks),
    )

    try:
        controller.move()
    except Exception as error:
        assert "最后反馈(rad)" in str(error)
        assert "动作前后变化(rad)" in str(error)
        assert "不要直接重复运行" in str(error)
    else:
        raise AssertionError("未到达目标时应报告超时。")

    assert arm.emergency_stops == 1
