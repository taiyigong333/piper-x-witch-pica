# Piper-X 手动控制工具

在仓库根目录执行：

```bash
python -m tool.piper_x_control.gui
```

工具只使用本仓库 `pyAgxArm` 的 CAN 接口，不启动也不修改 `/home/cv/pika_ros`。

- `停止保持`：调用阻尼电子急停，停止当前运动；
- `失能`：调用 `disable()`；
- `恢复使能`：在二次确认后先调用 `reset()` 清除电子急停，再调用 `enable()`；
- `reset()` 可能造成瞬时失电和机械臂下坠，只有现场确认机械臂已安全支撑后才能点击恢复。
