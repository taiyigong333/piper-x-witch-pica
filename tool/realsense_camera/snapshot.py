"""读取当前 RealSense 参数并保存为独立参数文件。"""

from __future__ import annotations

import argparse
from .common import load_realsense_config, parameter_payload, save_payload, start_cameras, stop_cameras


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取采集配置涉及的 RealSense 当前参数")
    parser.add_argument("--config", required=True, help="采集 YAML，用于确定相机、流和需要保存的 option")
    parser.add_argument("--name", required=True, help="写入 configs/camera/ 的 JSON 文件名")
    parser.add_argument("--purpose", required=True, help="写入 JSON 的 purpose 字段")
    args = parser.parse_args(argv)
    config = load_realsense_config(args.config)
    cameras = start_cameras(config, apply_options=False)
    try:
        for camera in cameras.values():
            camera.refresh_parameters(config.modalities.depth)
        output = save_payload(args.name, parameter_payload(config, cameras, args.purpose))
    finally:
        stop_cameras(cameras)
    print(f"已保存 RealSense 当前参数：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
