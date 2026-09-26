from types import SimpleNamespace

from taiyi_piper_x_collect.devices.realsense import RealSenseCamera


class _FakeSensor:
    def __init__(self, name: str, values: dict[str, float]) -> None:
        self.name = name
        self.values = values

    def supports(self, option: str) -> bool:
        return option == "name" or option in self.values

    def get_option(self, option: str) -> float:
        return self.values[option]

    def get_info(self, key: str) -> str:
        return self.name if key == "name" else ""


class _FakeDevice:
    def __init__(self, sensors: list[_FakeSensor]) -> None:
        self.sensors = sensors

    def query_sensors(self) -> list[_FakeSensor]:
        return self.sensors


def test_realsense_snapshot_keeps_only_configured_options() -> None:
    rs = SimpleNamespace(
        option=SimpleNamespace(exposure="exposure", white_balance="white_balance"),
        camera_info=SimpleNamespace(name="name"),
    )
    camera = object.__new__(RealSenseCamera)
    device = _FakeDevice([_FakeSensor("RGB Camera", {"exposure": 120.0, "gain": 16.0})])

    # gain 虽可读取，但本次配置未使用，不应进入运行快照。
    sensors = camera._read_sensor_parameters(rs, device, {"exposure": 120.0})

    assert sensors == [{"info": {"name": "RGB Camera"}, "options": {"exposure": {"value": 120.0}}}]


def test_runtime_snapshot_omits_disabled_depth_stream() -> None:
    camera = object.__new__(RealSenseCamera)
    camera._config = SimpleNamespace(width=640, height=480, fps=30, depth_width=640, depth_height=480)
    camera._device_info = lambda *_: {"serial_number": "test"}
    camera._read_sensor_parameters = lambda *_: []
    camera._depth_scale = lambda *_: 0.001
    camera._intrinsics_payload = lambda _: {"width": 640, "height": 480}

    rs = SimpleNamespace(stream=SimpleNamespace(color="color"))
    # 深度未启用时，快照不应出现深度流或深度比例字段。
    camera._parameters = camera._make_runtime_snapshot(
        rs,
        object(),
        capture_depth=False,
        sensors=[],
        configured_options={},
        calibration={"color_intrinsics": {"width": 640, "height": 480}},
    )

    assert camera.parameters()["streams"] == {
        "color": {"width": 640, "height": 480, "fps": 30, "format": "bgr8"}
    }
    assert "depth_scale" not in camera.parameters()
