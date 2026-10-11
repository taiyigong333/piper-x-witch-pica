# 连续采集期间 USB 设备断连排查

日期：2026-10-11

## 问题与范围

运行以下单向连续采集命令时，曾出现 USB 设备全部断开；用户反馈双向 `--reverse-recording` 运行正常：

```bash
uv run piper-x-collect teleop-session \
  --config configs/tasks/grab_rotating_red_square.yaml \
  --teleop-config configs/teleop/pika_sense_piper_x.example.yaml \
  --continuous-recording
```

本次只检查项目代码、任务配置和提供的错误报告，并修正代码中的相机生命周期差异；没有在真实机械臂/相机上复现，也没有修改系统 USB、电源管理、内核或固件设置。

## 报告证据

检查了 `/home/cv/gcj/test/docs/系统崩溃简短报告.md` 和 `/home/cv/gcj/test/docs/系统崩溃详细报告.md`。报告记录的关键现象是：

- 内核先记录 RealSense UVC 通信错误（`-71`、`-110`），随后 Intel xHCI `0000:00:14.0` 出现 `host controller not responding`、`HC died` 和停止端点超时，多个 USB 设备继而同时断开。
- 2026-10-11 拆除 GTX 1050 Ti 后仍出现相似 xHCI 故障，因此现有报告不支持把 USB 断连归因于 `nouveau` 显卡驱动。
- 报告指出多台 RealSense、Hub 和其他 USB 外设共享同一 xHCI 控制器；线缆、Hub、供电、信号质量、带宽、自动挂起和主板/固件仍是待验证因素。
- 当前提供的是整理后的 Markdown 报告，不含可与按键操作逐秒对齐的原始日志。因此无法确认每次 `pipeline.stop/start` 是否紧邻 xHCI 故障，也不能仅凭时间先后证明代码是硬件控制器失效的唯一原因。

## 配置与代码对比

`grab_rotating_red_square.yaml` 和 `grab_rotating_red_square_into_blue_plate.yaml` 使用相同的相机参数文件、相机序列号、分辨率、帧率、RGB/深度模态和采样频率。两者主要不同是任务语言、batch tag 和 `reverse_recording_enabled`，没有发现单向任务额外启用相机流或提高采集负载的配置差异。

代码中双向模式在每段调用 `DataCollector.run(..., keep_cameras_open=True)`，整轮结束时才关闭相机。连续模式此前却在每段结束后关闭相机，并在下一段开始时重新调用 `camera.start()`。因此它会不必要地反复停止、重建 RealSense pipeline 和 USB 视频流。

`capture_stopped` 在采样 worker 已退出且机器人/夹爪停止后置位；HDF5 writer 随后仍可异步完成收尾。故连续模式可以保留相机 pipeline，在确认采样 worker 停止后启动下一段，同时让上一段 HDF5/质检文件收尾，不需要为并行写入而重启相机。

## 结论与修正

代码中确实存在连续模式特有、且没有必要的相机 stop/start 生命周期差异。这是一个应修复的高风险触发因素，但现有证据不足以认定它单独造成了 xHCI 控制器死亡；USB 线缆、拓扑、供电/信号质量、控制器或固件等因素仍需分开排查。

连续模式现已调整为：相机预热后由整个会话持有；每条轨迹只停止采样线程并复用 pipeline；会话退出时统一停止相机。回归测试使用假相机验证相机只启动一次、只在会话结束时停止，并确认各段 `DataCollector` 保持相机打开。

## 验证与后续

- 软件验证：使用无硬件假对象和 mock 采集器运行连续会话及数据管线测试；结果记录在本次提交说明/交接文档中。
- 硬件验证：当前未执行。后续如需验证，应在安全预检通过后进行受控短时采集，并同步记录每次采集开始/结束时间、USB 拓扑及 `journalctl -k`；不建议为了复现而反复触发全控制器断连。
- 若复现，应保留完整原始内核日志并逐项控制相机、物理端口和线缆变量。不要在采集中重置/重新绑定 xHCI，也不要在缺少备份和回退方案时批量更改系统省电、内核或固件设置。
