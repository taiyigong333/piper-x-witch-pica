"""Tkinter 图形界面：预览并调整 configs/camera 中保存的 RealSense 参数。"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk
from typing import Any

import numpy as np

from taiyi_piper_x_collect.config import CameraConfig
from taiyi_piper_x_collect.devices.realsense import RealSenseCamera
from taiyi_piper_x_collect.errors import DeviceError


PARAMETERS = (
    ("exposure", "曝光时间", 10.0),
    ("gain", "增益", 1.0),
    ("white_balance", "白平衡", 100.0),
    ("brightness", "亮度", 1.0),
    ("contrast", "对比度", 1.0),
    ("saturation", "饱和度", 1.0),
    ("sharpness", "锐度", 1.0),
    ("gamma", "Gamma", 1.0),
    ("hue", "色调", 1.0),
    ("power_line_frequency", "电源频率", 1.0),
)


def _parameter_file(name: str) -> Path:
    path = Path(name)
    if path.name != name or path.suffix.lower() != ".json":
        raise ValueError("请选择 configs/camera/ 下的 JSON 参数文件名")
    return Path(__file__).resolve().parents[2] / "configs" / "camera" / name


def _load(name: str) -> tuple[dict[str, Any], list[CameraConfig]]:
    payload = json.loads(_parameter_file(name).read_text(encoding="utf-8"))
    raw_cameras = payload.get("cameras")
    if not isinstance(raw_cameras, list):
        raise ValueError("参数文件缺少 cameras 列表")
    cameras = []
    for raw in raw_cameras:
        if not isinstance(raw, dict) or raw.get("driver", "realsense") != "realsense" or not raw.get("enabled", True):
            continue
        cameras.append(CameraConfig(
            name=str(raw["name"]), driver="realsense", model=str(raw.get("model", "RealSense")),
            serial_number=str(raw["serial_number"]) if raw.get("serial_number") else None,
            width=int(raw["width"]), height=int(raw["height"]), fps=float(raw["fps"]),
            color_order=str(raw.get("color_order", "bgr")), enabled=True,
            align_depth_to_color=bool(raw.get("align_depth_to_color", True)),
            depth_width=int(raw["depth_width"]) if raw.get("depth_width") is not None else None,
            depth_height=int(raw["depth_height"]) if raw.get("depth_height") is not None else None,
            options={str(k): float(v) for k, v in dict(raw.get("options", {})).items()},
        ))
    if not cameras:
        raise ValueError("参数文件中没有启用的 RealSense 相机")
    return payload, cameras


def _ppm_data(bgr: np.ndarray) -> str:
    rgb = np.ascontiguousarray(bgr[..., ::-1])
    height, width = rgb.shape[:2]
    ppm = f"P6 {width} {height} 255\n".encode("ascii") + rgb.tobytes()
    return base64.b64encode(ppm).decode("ascii")


class CameraPreview:
    def __init__(self, app: "PreviewApp", config: CameraConfig) -> None:
        self.app = app
        self.config = config
        self.camera = RealSenseCamera(config)
        self.camera.start(capture_depth=False, apply_options=True)
        self.config.options.update(self.camera.color_options(tuple(name for name, _, _ in PARAMETERS) + (
            "enable_auto_exposure", "enable_auto_white_balance"
        )))
        self.frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self.closed = threading.Event()
        self.status = tk.StringVar(value="相机已连接")
        self.window = tk.Toplevel(app.root)
        self.window.title(f"RealSense 参数预览 | {config.name}")
        self.window.protocol("WM_DELETE_WINDOW", app.close)
        self._build()
        self.worker = threading.Thread(target=self._read_frames, name=f"frame-{config.name}", daemon=True)
        self.worker.start()
        self.window.after(15, self._refresh)

    def _build(self) -> None:
        self.window.configure(bg="#20252d")
        self.window.geometry(f"{self.config.width + 440}x{max(self.config.height, 660)}")
        root = ttk.Frame(self.window, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.image = ttk.Label(root, text="等待 RealSense RGB 图像…", anchor="center")
        self.image.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        panel = ttk.Frame(root, width=400)
        panel.grid(row=0, column=1, sticky="ns")
        panel.grid_propagate(False)
        ttk.Label(panel, text=self.config.name, font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(panel, text=f"{self.config.model}  |  {self.config.serial_number or '未指定序列号'}").pack(anchor="w")

        resolution = ttk.LabelFrame(panel, text="彩色流", padding=8)
        resolution.pack(fill="x", pady=(12, 6))
        self.width_var = tk.StringVar(value=str(self.config.width))
        self.height_var = tk.StringVar(value=str(self.config.height))
        ttk.Label(resolution, text="宽").grid(row=0, column=0, padx=4)
        ttk.Entry(resolution, textvariable=self.width_var, width=7).grid(row=0, column=1)
        ttk.Label(resolution, text="高").grid(row=0, column=2, padx=4)
        ttk.Entry(resolution, textvariable=self.height_var, width=7).grid(row=0, column=3)
        ttk.Button(resolution, text="应用并重启流", command=self._apply_resolution).grid(row=0, column=4, padx=8)
        ttk.Label(resolution, text=f"帧率 {self.config.fps:g} fps").grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        switches = ttk.LabelFrame(panel, text="自动控制", padding=8)
        switches.pack(fill="x", pady=6)
        self.ae_var = tk.BooleanVar(value=self.config.options.get("enable_auto_exposure", 0) > 0.5)
        self.awb_var = tk.BooleanVar(value=self.config.options.get("enable_auto_white_balance", 0) > 0.5)
        ttk.Checkbutton(switches, text="自动曝光", variable=self.ae_var, command=lambda: self._toggle("enable_auto_exposure", self.ae_var)).pack(anchor="w")
        ttk.Checkbutton(switches, text="自动白平衡", variable=self.awb_var, command=lambda: self._toggle("enable_auto_white_balance", self.awb_var)).pack(anchor="w")

        values = ttk.LabelFrame(panel, text="RGB 参数（滑块实时应用到相机）", padding=8)
        values.pack(fill="x", pady=6)
        values.columnconfigure(1, weight=1)
        self.scales: dict[str, tk.Scale] = {}
        ranges = self.camera.color_option_ranges(tuple(name for name, _, _ in PARAMETERS))
        for row, (name, label, step) in enumerate(PARAMETERS):
            if name not in self.config.options or name not in ranges:
                continue
            minimum, maximum, sdk_step = ranges[name]
            ttk.Label(values, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8))
            scale = tk.Scale(values, from_=minimum, to=maximum, resolution=max(sdk_step, step), orient="horizontal", showvalue=True,
                             command=lambda raw, option=name: self._set_parameter(option, float(raw)))
            scale.set(self.config.options[name])
            scale.grid(row=row, column=1, sticky="ew")
            self.scales[name] = scale

        ttk.Button(panel, text="另存为新参数文件…", command=self._save_as).pack(fill="x", pady=(12, 6))
        ttk.Label(panel, textvariable=self.status, wraplength=380).pack(fill="x", anchor="w")

    def _read_frames(self) -> None:
        while not self.closed.is_set():
            try:
                frame = self.camera.read().color
                try:
                    self.frames.put_nowait(frame)
                except queue.Full:
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass
                    self.frames.put_nowait(frame)
            except DeviceError as error:
                self.status.set(f"相机取帧异常：{error}")

    def _refresh(self) -> None:
        if self.closed.is_set():
            return
        try:
            frame = self.frames.get_nowait()
        except queue.Empty:
            self.window.after(30, self._refresh)
            return
        try:
            photo = tk.PhotoImage(data=_ppm_data(frame), format="PPM")
            self.image.configure(image=photo, text="")
            self.image.image = photo
            self.window.after(15, self._refresh)
        except tk.TclError as error:
            self.status.set(f"图像显示失败：{error}")
            self.window.after(100, self._refresh)

    def _set_parameter(self, name: str, value: float) -> None:
        try:
            self.camera.set_color_option(name, value)
            self.config.options[name] = value
            self.status.set(f"已应用 {name} = {value:g}")
        except Exception as error:
            self.status.set(f"设置 {name} 失败：{error}")

    def _toggle(self, name: str, variable: tk.BooleanVar) -> None:
        value = 1.0 if variable.get() else 0.0
        try:
            self.camera.set_color_option(name, value)
            self.config.options[name] = value
            self.status.set(f"{name}: {'开启' if value else '关闭'}")
        except Exception as error:
            variable.set(not variable.get())
            messagebox.showerror("相机参数设置失败", str(error), parent=self.window)

    def _apply_resolution(self) -> None:
        try:
            width, height = int(self.width_var.get()), int(self.height_var.get())
            if width < 160 or height < 120:
                raise ValueError("分辨率过小")
            self.camera.stop()
            object.__setattr__(self.config, "width", width)
            object.__setattr__(self.config, "height", height)
            self.camera.start(capture_depth=False, apply_options=True)
            self.config.options.update(self.camera.color_options(tuple(self.config.options)))
            self.status.set(f"已切换到 {width}x{height}")
        except Exception as error:
            messagebox.showerror("分辨率切换失败", str(error), parent=self.window)

    def _save_as(self) -> None:
        name = filedialog.asksaveasfilename(
            parent=self.window, title="另存相机参数", initialdir=str(_parameter_file(self.app.source_name).parent),
            initialfile=f"camera_tuned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            defaultextension=".json", filetypes=[("JSON 参数文件", "*.json")],
        )
        if not name:
            return
        target = Path(name)
        camera_dir = _parameter_file(self.app.source_name).parent.resolve()
        if target.suffix.lower() != ".json" or target.parent.resolve() != camera_dir:
            messagebox.showerror("保存失败", "新文件必须保存到项目 configs/camera/ 目录，并使用 .json 扩展名。", parent=self.window)
            return
        if target.name == self.app.source_name:
            messagebox.showerror("保存失败", "不能覆盖当前源参数文件。", parent=self.window)
            return
        if target.exists():
            messagebox.showerror("保存失败", "目标文件已存在；请使用新文件名。", parent=self.window)
            return
        purpose = simpledialog.askstring("参数用途", "purpose：", initialvalue=str(self.app.payload.get("purpose", "")), parent=self.window)
        if purpose is None:
            return
        updated = copy.deepcopy(self.app.payload)
        by_name = {item.name: item for item in self.app.cameras}
        for item in updated["cameras"]:
            config = by_name.get(item.get("name")) if isinstance(item, dict) else None
            if config is not None:
                item["width"], item["height"] = config.width, config.height
                item["options"] = dict(config.options)
        updated["purpose"] = purpose
        try:
            target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.status.set(f"已另存为 {target.name}")
            messagebox.showinfo("保存成功", f"参数已保存到 {target.name}", parent=self.window)
        except OSError as error:
            messagebox.showerror("保存失败", str(error), parent=self.window)

    def stop(self) -> None:
        self.closed.set()
        self.camera.stop()


class PreviewApp:
    def __init__(self, root: tk.Tk, source_name: str) -> None:
        self.root = root
        self.source_name = source_name
        self.payload, self.cameras = _load(source_name)
        self.previews: list[CameraPreview] = []
        root.withdraw()
        root.title("RealSense 参数预览")
        root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            for config in self.cameras:
                self.previews.append(CameraPreview(self, config))
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        for preview in self.previews:
            preview.stop()
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tkinter RealSense GUI，不使用 OpenCV HighGUI 或 Linux 视频设备")
    parser.add_argument("--name", required=True, help="configs/camera/ 下的 JSON 参数文件")
    args = parser.parse_args(argv)
    root = tk.Tk()
    try:
        PreviewApp(root, args.name)
        root.mainloop()
    except Exception as error:
        messagebox.showerror("RealSense GUI 启动失败", str(error), parent=root)
        root.destroy()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
