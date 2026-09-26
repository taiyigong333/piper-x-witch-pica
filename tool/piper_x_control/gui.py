"""Piper-X 手动控制 GUI：python -m tool.piper_x_control.gui。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .control import PiperXControl


class ControlWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.control = PiperXControl()
        self.status = tk.StringVar(value="未连接")
        self.output = tk.StringVar(value="")
        self.can_name = tk.StringVar(value="can0")
        self.firmware = tk.StringVar(value="default")
        root.title("Piper-X 控制")
        form = ttk.Frame(root)
        form.pack(padx=12, pady=4, fill="x")
        ttk.Label(form, text="CAN 接口").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.can_name, width=16).grid(row=0, column=1, padx=6)
        ttk.Label(form, text="固件版本").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.firmware, width=16).grid(row=0, column=3, padx=6)
        ttk.Label(root, textvariable=self.status).pack(padx=12, pady=8)
        buttons = ttk.Frame(root)
        buttons.pack(padx=12, pady=4)
        ttk.Button(buttons, text="连接", command=self.connect).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="读取状态", command=self.read_status).grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="停止保持", command=self.stop_hold).grid(row=1, column=0, padx=4, pady=6)
        ttk.Button(buttons, text="失能", command=self.disable).grid(row=1, column=1, padx=4, pady=6)
        ttk.Button(buttons, text="恢复使能", command=self.enable).grid(row=1, column=2, padx=4, pady=6)
        ttk.Label(root, textvariable=self.output, wraplength=560).pack(padx=12, pady=8)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _run(self, action, confirm: bool = False) -> None:
        if confirm and not messagebox.askyesno("确认危险操作", "请确认现场安全后继续。"):
            return
        try:
            result = action()
            self.output.set(str(result) if result is not None else "完成")
            return True
        except Exception as error:
            self.output.set(f"失败：{error}")
            return False

    def connect(self) -> None:
        self.control.can_name = self.can_name.get().strip() or "can0"
        self.control.firmware_version = self.firmware.get().strip() or "default"
        if self._run(self.control.connect):
            self.status.set(f"已连接：{self.control.can_name}")
        else:
            self.status.set("连接失败")

    def read_status(self) -> None:
        self._run(self.control.read_status)

    def stop_hold(self) -> None:
        self._run(self.control.stop_hold, True)

    def disable(self) -> None:
        self._run(self.control.disable, True)

    def enable(self) -> None:
        self._run(self.control.enable, True)

    def close(self) -> None:
        self.control.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ControlWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
