from pathlib import Path
from types import SimpleNamespace

import pytest

from tool.realsense_camera.common import (
    _create_missing_camera_parameters,
    parameter_output_path,
    parameter_payload,
    save_payload,
)


class _FakeCamera:
    def parameters(self) -> dict[str, object]:
        return {"configured_options": {"exposure": 80.0}, "streams": {"color": {"fps": 30}}}


def test_parameter_payload_uses_selected_camera_and_current_options() -> None:
    camera_config = SimpleNamespace(
        name="camera_front",
        driver="realsense",
        model="RealSense_D435",
        serial_number="123",
        width=640,
        height=480,
        fps=30,
        color_order="rgb",
        enabled=True,
        align_depth_to_color=True,
        options={"exposure": 100.0},
        depth_width=None,
        depth_height=None,
        base_to_camera=None,
    )
    disabled_camera_config = SimpleNamespace(**vars(camera_config))
    disabled_camera_config.name = "camera_disabled"
    disabled_camera_config.enabled = False
    disabled_camera_config.options = {"exposure": 55.0}
    config = SimpleNamespace(cameras=(camera_config, disabled_camera_config))

    payload = parameter_payload(config, {"camera_front": _FakeCamera()}, "test camera")

    assert payload["purpose"] == "test camera"
    assert payload["cameras"][0]["options"] == {"exposure": 80.0}
    assert payload["cameras"][1]["options"] == {"exposure": 55.0}
    assert payload["devices"]["camera_front"]["streams"]["color"]["fps"] == 30


def test_parameter_output_requires_a_filename_and_saves_under_camera_dir(tmp_path: Path) -> None:
    output = parameter_output_path("camera_test.json")

    assert output.name == "camera_test.json"
    assert output.parent.name == "camera"
    with pytest.raises(ValueError, match="JSON 文件名"):
        parameter_output_path("../camera_test.json")


def test_missing_camera_parameters_file_is_created_from_collection_yaml(tmp_path: Path) -> None:
    import json

    config_path = tmp_path / "task.yaml"
    output_path = tmp_path / "configs" / "camera" / "new_parameters.json"
    config_path.write_text(
        "session:\n  camera_parameters_file: " + str(output_path) + "\n"
        "cameras:\n  - name: camera_front\n    driver: realsense\n    width: 640\n",
        encoding="utf-8",
    )

    _create_missing_camera_parameters(config_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["cameras"][0]["name"] == "camera_front"
    assert payload["cameras"][0]["options"]["enable_auto_exposure"] == 1.0
