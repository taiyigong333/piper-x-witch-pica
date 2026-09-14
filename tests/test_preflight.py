from __future__ import annotations

import numpy as np

from taiyi_piper_x_collect.errors import DeviceError
from taiyi_piper_x_collect.models import RobotState
from taiyi_piper_x_collect.preflight import _read_robot_state_with_retry


class EventuallyReadyRobot:
    def __init__(self) -> None:
        self.read_count = 0

    def read(self) -> RobotState:
        self.read_count += 1
        if self.read_count < 3:
            raise DeviceError("尚未收到完整 Piper-X 关节与法兰反馈。")
        return RobotState(
            timestamp=1.0,
            joint_positions=np.zeros(6, dtype=np.float64),
            tcp_pose=np.zeros(6, dtype=np.float64),
        )


def test_preflight_waits_for_piper_x_can_feedback() -> None:
    robot = EventuallyReadyRobot()

    state = _read_robot_state_with_retry(robot)

    assert robot.read_count == 3
    assert state.joint_positions is not None
