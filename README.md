# Piper-X Pika Sense Data Collection

Configuration-driven data collection for one Piper-X arm, its original AGX gripper, Pika Sense teleoperation, and RealSense D405/D435 cameras. It writes HDF5 trajectories plus `quality.json`, `manifest.json`, and SHA-256 checksums.

`code/` is a standalone Git repository. `pyAgxArm/` is a pinned Git submodule and is the only arm SDK used by this project. `pika_ros` is an external ROS workspace; this repository starts its documented commands but never modifies its source or launch files.

## Install

The collector runs only from this repository's uv environment, with Python 3.10. The Pika ROS controller continues to run in the separate `pika` Conda environment.

```bash
cd data_collect/piper_x_with_pica/code
git submodule update --init --recursive
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra dev --extra realsense
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect --help
```

No `pip install` or Conda installation is required for the collector. The uv environment is created at `code/.venv/` and is ignored by Git.

## Offline Check

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect collect \
  --config configs/mock_piper_x.yaml --duration 1
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

The mock command uses no CAN, camera, Pika, or ROS hardware.

## Real Collection

Create local configurations, then fill camera serials, calibration, task metadata, CAN interface, firmware profile, and tool offset. Local files beginning with `configs/现场_` are ignored by Git.

```bash
cp configs/piper_x_d405_d435.example.yaml configs/现场_piper_x.yaml
cp configs/pika_sense_piper_x.example.yaml configs/现场_pika_sense_piper_x.yaml
```

Before collection, ensure `robot.firmware_version` matches the Piper-X firmware profile (`default`, `v183`, `v188`, or `v189`). Preflight and normal collection are read-only for the arm and original gripper: they use `pyAgxArm` feedback APIs but never call arm enable, arm motion, or gripper motion APIs.

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect preflight \
  --config configs/现场_piper_x.yaml
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect read-piper-x-state \
  --config configs/现场_piper_x.yaml
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect collect \
  --config configs/现场_piper_x.yaml
```

Only `robot.initial_pose.enabled: true` allows this project to issue a pre-teleoperation move. It uses `pyAgxArm`'s Piper-X `enable`, `move_j`, or `move_p` API before ROS starts, then disconnects. A move timeout triggers the SDK electronic emergency stop, so the arm must be inspected and reset at the physical site before proceeding.

## Pika Sense Teleoperation

Do not edit `/home/cv/pika_ros`. Start the existing Pika programs in separate terminals. Terminal 1:

```bash
source ~/pika_ros/install/setup.bash
cd ~/pika_ros/scripts && bash start_single_sensor_whit_teleop.bash
```

Terminal 2:

```bash
source ~/pika_ros/install/setup.bash
conda activate pika
export PYTHONPATH=$CONDA_PREFIX/lib/python3.10/site-packages:$PYTHONPATH
ros2 launch pika_remote_agx_arm teleop_single_piper_x.launch.py
```

Quickly open and close the Sense gripper twice to enable teleoperation. The collection orchestrator can start the same commands from `configs/pika_sense_piper_x.example.yaml`; it sanitizes its child environment so ROS keeps using the `pika` Conda environment rather than uv:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect calibrate-base \
  --teleop-config configs/现场_pika_sense_piper_x.yaml --mode force
UV_CACHE_DIR=/tmp/uv-cache uv run piper-x-collect teleop-session \
  --config configs/现场_piper_x.yaml \
  --teleop-config configs/现场_pika_sense_piper_x.yaml --repeat
```

See [docs/使用说明.md](docs/使用说明.md) for the operating sequence and safety boundaries. The complete command-by-command procedure for the corn-to-plate task is in [docs/2026-09-15_01_实际采集逐指令操作说明.md](docs/2026-09-15_01_实际采集逐指令操作说明.md).
