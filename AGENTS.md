# Repository Guidelines

## Project Structure & Module Organization

- `src/taiyi_piper_x_collect/` contains the Python package, CLI commands, collection orchestration, device adapters, HDF5 writer, validation, and trajectory viewer.
- `tool/piper_x_control/` contains the Piper-X manual control GUI; `tool/realsense_camera/` contains RealSense snapshot, preview, and RGB auto-tuning tools.
- `configs/` stores camera, teleoperation, task, and example/pass configurations. Keep hardware-specific values in configuration files rather than source code.
- `tests/` contains unit and integration-style regression tests. `docs/` contains operating procedures, handoff notes, and the data storage specification.
- `pyAgxArm/` is an editable local SDK source used by uv.

## Build, Test, and Development Commands

Use Python 3.10 and uv:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra dev --extra realsense
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev python -m pytest -q
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q src tool
```

Run a preflight or collection session with the task YAML:

```bash
uv run piper-x-collect preflight --config configs/tasks/grab_rotating_red_square_into_blue_plate.yaml
```

Do not start real hardware collection without completing the safety preflight.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints for public interfaces, focused functions, and Chinese comments where they explain hardware or data-flow decisions. Follow `snake_case` for functions and variables, `PascalCase` for classes, and descriptive configuration filenames such as `piper_x_balanced_fixed.parameters.json`. Run `git diff --check` before committing.

## Testing Guidelines

Tests use `pytest`; files are named `tests/test_<module>.py` and test functions start with `test_`. Add regression coverage for configuration, device, writer, or trajectory changes. Hardware-dependent behavior should be tested with fakes/mocks when possible; clearly document anything requiring a physical RealSense or Piper-X.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects, for example `feat: add RGB sensor auto tuning workflow`, `fix: ...`, or `docs: ...`. Keep commits focused and include tests in the same change. Pull requests should describe behavior changes, affected configs or data formats, validation commands and results, and hardware limitations; include screenshots for GUI or preview changes when useful.

## Configuration & Safety Notes

Never commit SSH keys, secrets, or unreviewed captured data. Preserve existing user-local configuration changes unless explicitly asked to replace them. Changes to HDF5 names, collection directories, camera parameters, or trajectory formats must update the relevant docs and viewer/validation logic together.
