from types import SimpleNamespace

from tool.realsense_camera.rgb_auto_tune import _find_rgb_sensor


class _Sensor:
    def __init__(self, name: str, options: set[str]) -> None:
        self.name = name
        self.options = options

    def supports(self, option: str) -> bool:
        return option in self.options or option == "name"

    def get_info(self, key: str) -> str:
        return self.name


class _Device:
    def __init__(self, sensors: list[_Sensor]) -> None:
        self.sensors = sensors

    def query_sensors(self) -> list[_Sensor]:
        return self.sensors


def test_rgb_sensor_selection_does_not_choose_stereo_sensor() -> None:
    rs = SimpleNamespace(
        option=SimpleNamespace(
            enable_auto_exposure="ae",
            enable_auto_white_balance="awb",
            exposure="exposure",
        ),
        camera_info=SimpleNamespace(name="name"),
    )
    stereo = _Sensor("Stereo Module", {"ae", "exposure"})
    color = _Sensor("RGB Camera", {"ae", "awb", "exposure"})

    assert _find_rgb_sensor(rs, _Device([stereo, color])) is color
