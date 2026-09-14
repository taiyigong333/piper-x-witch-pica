from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from taiyi_piper_x_collect.config import GripperConfig, RobotConfig
from taiyi_piper_x_collect.devices.factory import create_gripper
from taiyi_piper_x_collect.devices.piper_x import PiperXGripper, PiperXRobot, euler_xyz_to_xyzw, rotate_vector_xyzw
from taiyi_piper_x_collect.errors import DeviceError


def test_euler_xyz_to_xyzw_identity() -> None:
    assert np.allclose(euler_xyz_to_xyzw(np.zeros(3)), [0.0, 0.0, 0.0, 1.0])


def test_tool_offset_follows_end_effector_orientation() -> None:
    quaternion = euler_xyz_to_xyzw(np.asarray([0.0, 0.0, math.pi / 2]))
    assert np.allclose(rotate_vector_xyzw(quaternion, np.asarray([1.0, 0.0, 0.0])), [0.0, 1.0, 0.0])


def test_piper_x_reads_pyagxarm_si_feedback_and_applies_tool_offset() -> None:
    robot = PiperXRobot(
        RobotConfig(name="piper_x", driver="piper_x", can_name="can0", tool_offset_m=(0.1, 0.0, 0.0)),
        "xyz_rxryrz",
    )
    robot._arm = SimpleNamespace(
        get_joint_angles=lambda: SimpleNamespace(msg=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5]),
        get_flange_pose=lambda: SimpleNamespace(msg=[0.35, -0.1, 0.25, 0.0, 0.0, math.pi / 2]),
    )

    state = robot.read()

    assert state.tcp_pose is not None
    assert np.allclose(state.joint_positions, [0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    assert np.allclose(state.tcp_pose, [0.35, 0.0, 0.25, 0.0, 0.0, math.pi / 2])


def test_piper_x_gripper_reads_original_width_in_meters() -> None:
    robot = PiperXRobot(RobotConfig(name="piper_x", driver="piper_x", can_name="can0"), "xyz_xyzw")
    robot._arm = SimpleNamespace(
        OPTIONS=SimpleNamespace(EFFECTOR=SimpleNamespace(AGX_GRIPPER="agx_gripper")),
        init_effector=lambda _: SimpleNamespace(
            get_gripper_status=lambda: SimpleNamespace(msg=SimpleNamespace(mode="width", value=0.0425))
        ),
    )

    gripper = create_gripper(GripperConfig(enabled=True, driver="piper_x"), robot)

    assert isinstance(gripper, PiperXGripper)
    gripper.start()
    assert gripper.read_position() == pytest.approx(0.0425)


def test_piper_x_gripper_rejects_angle_mode() -> None:
    robot = PiperXRobot(RobotConfig(name="piper_x", driver="piper_x", can_name="can0"), "xyz_xyzw")
    robot._arm = SimpleNamespace(
        OPTIONS=SimpleNamespace(EFFECTOR=SimpleNamespace(AGX_GRIPPER="agx_gripper")),
        init_effector=lambda _: SimpleNamespace(
            get_gripper_status=lambda: SimpleNamespace(msg=SimpleNamespace(mode="angle", value=42.5))
        ),
    )

    with pytest.raises(DeviceError, match="width"):
        robot.read_gripper_position()
