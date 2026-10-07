"""本地网页 RealSense 预览与参数调整工具。"""

from __future__ import annotations

import argparse
import copy
import json
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import cv2

from taiyi_piper_x_collect.config import CameraConfig
from taiyi_piper_x_collect.devices.realsense import RealSenseCamera
from taiyi_piper_x_collect.errors import DeviceError

from .saved_preview_gui import PARAMETERS, _load, _parameter_file


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RealSense 参数预览</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#111827;color:#e5e7eb}
*{box-sizing:border-box}body{margin:0;background:#111827}header{position:sticky;top:0;z-index:2;padding:14px 20px;background:#1f2937;border-bottom:1px solid #374151}
h1{font-size:20px;margin:0 0 4px}.hint{color:#9ca3af;font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(620px,1fr));gap:16px;padding:16px}
.card{min-width:0;background:#1f2937;border:1px solid #374151;border-radius:10px;overflow:hidden}.card h2{font-size:17px;margin:0}.card-head{padding:14px 16px;border-bottom:1px solid #374151}.meta,.status{color:#9ca3af;font-size:13px;margin-top:4px}.status.error{color:#fca5a5}.body{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px;padding:14px}.preview{width:100%;min-height:240px;object-fit:contain;background:#030712;border-radius:6px}.controls{max-height:70vh;overflow-y:auto;padding-right:4px}.section{border:1px solid #374151;border-radius:7px;padding:10px;margin-bottom:10px}.section h3{font-size:14px;margin:0 0 9px;color:#d1d5db}.row{display:grid;grid-template-columns:1fr 100px 78px;gap:7px;align-items:center;margin:9px 0}.row label{font-size:13px}.range{display:block;color:#9ca3af;font-size:11px}.number{width:100%;background:#111827;color:#f9fafb;border:1px solid #4b5563;border-radius:4px;padding:6px}.range-input{width:100%;accent-color:#60a5fa}.btn{border:0;border-radius:5px;padding:7px 10px;background:#2563eb;color:white;cursor:pointer}.btn:hover{background:#1d4ed8}.btn.secondary{background:#4b5563}.btn:disabled{opacity:.5;cursor:wait}.line{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:7px 0}.line input{width:90px}.save{display:flex;gap:7px;flex-wrap:wrap}.save input{flex:1;min-width:180px}.notice{padding:10px 16px;color:#fbbf24;font-size:13px}
@media(max-width:900px){.body{grid-template-columns:1fr}.controls{max-height:none}}
</style></head><body>
<header><h1>RealSense 参数预览</h1><div class="hint">浏览器页面直接读取 RealSense；参数修改立即应用到 RGB sensor。可滚动右侧参数面板。</div></header>
<div id="app" class="grid"><div class="notice">正在连接相机…</div></div>
<script>
const app=document.querySelector('#app');let state=null;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:4});
async function api(path,options={}){const r=await fetch(path,options);const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data}
function card(c){const params=c.parameters.map(p=>`<div class="row"><label>${esc(p.label)}<span class="range">当前值 / Current: <b data-current="${esc(p.name)}">${fmt(p.value)}</b> · 范围: ${fmt(p.minimum)} – ${fmt(p.maximum)}</span></label><input class="number" type="number" step="${p.step}" min="${p.minimum}" max="${p.maximum}" value="${p.value}" data-name="${esc(p.name)}"><button class="btn" data-apply="${esc(p.name)}">应用</button><input class="range-input" type="range" step="${p.step}" min="${p.minimum}" max="${p.maximum}" value="${p.value}" data-slider="${esc(p.name)}"></div>`).join('');return `<article class="card" data-camera="${esc(c.name)}"><div class="card-head"><h2>${esc(c.name)}</h2><div class="meta">${esc(c.model)} | ${esc(c.serial_number||'未指定序列号')} | ${c.width}×${c.height} @ ${c.fps} fps</div><div class="status" data-status>${esc(c.status)}</div></div><div class="body"><img class="preview" src="/stream/${encodeURIComponent(c.name)}" alt="${esc(c.name)} RGB"><div class="controls"><section class="section"><h3>彩色流 / Color stream</h3><div class="line"><label>宽 <input class="number" data-width value="${c.width}"></label><label>高 <input class="number" data-height value="${c.height}"></label><button class="btn" data-resolution>应用并重启流</button></div></section><section class="section"><h3>自动控制 / Auto control</h3><label class="line"><input type="checkbox" data-option="enable_auto_exposure" ${c.auto_exposure?'checked':''}> 自动曝光 / Auto exposure</label><label class="line"><input type="checkbox" data-option="enable_auto_white_balance" ${c.auto_white_balance?'checked':''}> 自动白平衡 / Auto white balance</label></section><section class="section"><h3>RGB 参数 / RGB options</h3>${params}</section><section class="section"><h3>另存为 / Save as</h3><div class="save"><input data-save-name placeholder="new_parameters.json"><input data-save-purpose placeholder="purpose"><button class="btn" data-save>保存</button></div></section></div></div></article>`}
function render(){app.innerHTML=state.cameras.map(card).join('');document.querySelectorAll('[data-slider]').forEach(s=>s.addEventListener('input',e=>{const row=e.target.closest('.row');row.querySelector('.number').value=e.target.value}));document.querySelectorAll('[data-apply]').forEach(b=>b.addEventListener('click',()=>applyOption(b.closest('.card'),b.dataset.apply)));document.querySelectorAll('[data-slider]').forEach(s=>s.addEventListener('change',()=>applyOption(s.closest('.card'),s.dataset.slider)));document.querySelectorAll('[data-option]').forEach(x=>x.addEventListener('change',()=>applyOption(x.closest('.card'),x.dataset.option,x.checked?1:0)));document.querySelectorAll('[data-resolution]').forEach(b=>b.addEventListener('click',()=>applyResolution(b.closest('.card'))));document.querySelectorAll('[data-save]').forEach(b=>b.addEventListener('click',()=>save(b.closest('.card'))))}
function status(card,message,error=false){const x=card.querySelector('[data-status]');x.textContent=message;x.classList.toggle('error',error)}
async function applyOption(card,name,forced){const input=card.querySelector(`[data-name="${CSS.escape(name)}"]`);const value=forced===undefined?Number(input.value):forced;try{const r=await api(`/api/cameras/${encodeURIComponent(card.dataset.camera)}/option`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,value})});input.value=r.value;card.querySelector(`[data-slider="${CSS.escape(name)}"]`)?.setAttribute('value',r.value);status(card,`已应用 ${name} = ${fmt(r.value)}`)}catch(e){status(card,e.message,true)}}
async function applyResolution(card){try{const width=Number(card.querySelector('[data-width]').value),height=Number(card.querySelector('[data-height]').value);const r=await api(`/api/cameras/${encodeURIComponent(card.dataset.camera)}/resolution`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({width,height})});status(card,`已切换到 ${r.width}×${r.height}`)}catch(e){status(card,e.message,true)}}
async function save(card){const name=card.querySelector('[data-save-name]').value,purpose=card.querySelector('[data-save-purpose]').value;try{const r=await api('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,purpose})});status(card,`已保存 ${r.name}`)}catch(e){status(card,e.message,true)}}
async function refresh(){try{state=await api('/api/state');if(!document.querySelector('.card'))render();else state.cameras.forEach(c=>{const card=document.querySelector(`[data-camera="${CSS.escape(c.name)}"]`);if(!card)return;card.querySelector('[data-status]').textContent=c.status;c.parameters.forEach(p=>{const input=card.querySelector(`[data-name="${CSS.escape(p.name)}"]`);const slider=card.querySelector(`[data-slider="${CSS.escape(p.name)}"]`);const current=card.querySelector(`[data-current="${CSS.escape(p.name)}"]`);if(input&&document.activeElement!==input)input.value=p.value;if(slider)slider.value=p.value;if(current)current.textContent=fmt(p.value)})})}catch(e){app.innerHTML=`<div class="notice">连接失败：${esc(e.message)}</div>`}setTimeout(refresh,1000)}refresh();
</script></body></html>"""


class CameraSession:
    def __init__(self, payload: dict[str, Any], config: CameraConfig) -> None:
        self.payload = payload
        self.config = config
        self.camera = RealSenseCamera(config)
        self.camera.start(capture_depth=False, apply_options=True)
        self.config.options.update(self.camera.color_options(tuple(name for name, _, _ in PARAMETERS) + ("enable_auto_exposure", "enable_auto_white_balance")))
        self.ranges = self.camera.color_option_ranges(tuple(name for name, _, _ in PARAMETERS))
        self.latest_jpeg: bytes | None = None
        self.status = "相机已连接，等待 RGB 帧"
        self.closed = threading.Event()
        self.io_lock = threading.RLock()
        self.condition = threading.Condition()
        self.worker = threading.Thread(target=self._read_frames, name=f"web-frame-{config.name}", daemon=True)
        self.worker.start()

    def _read_frames(self) -> None:
        while not self.closed.is_set():
            try:
                with self.io_lock:
                    frame = self.camera.read().color
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    raise DeviceError(f"{self.config.name} RGB 帧 JPEG 编码失败")
                with self.condition:
                    self.latest_jpeg = encoded.tobytes()
                    self.status = "RGB 画面正常"
                    self.condition.notify_all()
            except Exception as error:
                with self.condition:
                    self.status = f"取帧异常：{error}"
                    self.condition.notify_all()
                time.sleep(0.2)

    def frame(self, timeout: float = 2.0) -> bytes | None:
        with self.condition:
            if self.latest_jpeg is None:
                self.condition.wait(timeout)
            return self.latest_jpeg

    def stop(self) -> None:
        self.closed.set()
        with self.io_lock:
            self.camera.stop()

    def state(self) -> dict[str, Any]:
        # 自动曝光/白平衡开启后，硬件会持续改变这些值；侧边栏必须读取 sensor 当前值而不是只显示输入配置。
        try:
            with self.io_lock:
                self.config.options.update(self.camera.color_options(tuple(name for name, _, _ in PARAMETERS)))
        except Exception as error:
            self.status = f"读取当前参数失败：{error}"
        parameters = []
        for name, label, default_step in PARAMETERS:
            if name not in self.config.options or name not in self.ranges:
                continue
            minimum, maximum, sdk_step = self.ranges[name]
            parameters.append({"name": name, "label": label, "value": self.config.options[name], "minimum": minimum, "maximum": maximum, "step": max(sdk_step, default_step)})
        return {"name": self.config.name, "model": self.config.model, "serial_number": self.config.serial_number, "width": self.config.width, "height": self.config.height, "fps": self.config.fps, "status": self.status, "auto_exposure": self.config.options.get("enable_auto_exposure", 0) > .5, "auto_white_balance": self.config.options.get("enable_auto_white_balance", 0) > .5, "parameters": parameters}

    def set_option(self, name: str, value: float) -> float:
        if name not in self.ranges and name not in {"enable_auto_exposure", "enable_auto_white_balance"}:
            raise ValueError(f"不支持参数：{name}")
        if name in self.ranges:
            minimum, maximum, _ = self.ranges[name]
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} 有效范围为 {minimum:g} – {maximum:g}")
        with self.io_lock:
            self.camera.set_color_option(name, value)
        self.config.options[name] = float(value)
        return float(value)

    def set_resolution(self, width: int, height: int) -> None:
        if width < 160 or height < 120:
            raise ValueError("分辨率过小")
        with self.io_lock:
            self.camera.stop()
            object.__setattr__(self.config, "width", width)
            object.__setattr__(self.config, "height", height)
            self.camera.start(capture_depth=False, apply_options=True)
            self.config.options.update(self.camera.color_options(tuple(self.config.options)))


class PreviewState:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.payload, configs = _load(source_name)
        self.sessions = {config.name: CameraSession(self.payload, config) for config in configs}
        self.lock = threading.RLock()

    def close(self) -> None:
        for session in self.sessions.values():
            session.stop()

    def session(self, name: str) -> CameraSession:
        try:
            return self.sessions[name]
        except KeyError as error:
            raise ValueError(f"未知相机：{name}") from error

    def save(self, name: str, purpose: str) -> Path:
        source = _parameter_file(self.source_name)
        target = source.parent / Path(name).name
        if target.name != name or target.suffix.lower() != ".json":
            raise ValueError("文件名必须是 configs/camera/ 下的 JSON 文件名")
        if target.name == source.name:
            raise ValueError("不能覆盖当前源参数文件")
        if target.exists():
            raise ValueError("目标文件已存在，请换一个文件名")
        updated = copy.deepcopy(self.payload)
        by_name = {session.config.name: session.config for session in self.sessions.values()}
        for item in updated.get("cameras", []):
            config = by_name.get(item.get("name")) if isinstance(item, dict) else None
            if config:
                item["width"], item["height"] = config.width, config.height
                item["options"] = dict(config.options)
        updated["purpose"] = purpose
        target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target


class Handler(BaseHTTPRequestHandler):
    state: PreviewState

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string}] {format % args}")

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                raw = INDEX_HTML.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
            if parsed.path == "/api/state":
                self._send_json({"cameras": [session.state() for session in self.state.sessions.values()]}); return
            if parsed.path.startswith("/stream/"):
                name = unquote(parsed.path.removeprefix("/stream/")); session = self.state.session(name)
                self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
                while not session.closed.is_set():
                    frame = session.frame()
                    if frame is None: continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"); self.wfile.flush(); time.sleep(.03)
                return
            self._send_json({"error": "Not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as error:
            self._send_json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/save":
                data = self._body(); output = self.state.save(str(data.get("name", "")), str(data.get("purpose", ""))); self._send_json({"name": output.name}); return
            prefix = "/api/cameras/"
            if not parsed.path.startswith(prefix): self._send_json({"error": "Not found"}, 404); return
            parts = parsed.path.removeprefix(prefix).split("/"); session = self.state.session(unquote(parts[0])); data = self._body()
            if len(parts) == 2 and parts[1] == "option": self._send_json({"value": session.set_option(str(data["name"]), float(data["value"]))}); return
            if len(parts) == 2 and parts[1] == "resolution": session.set_resolution(int(data["width"]), int(data["height"])); self._send_json({"width": session.config.width, "height": session.config.height}); return
            self._send_json({"error": "Not found"}, 404)
        except Exception as error:
            self._send_json({"error": str(error)}, 400)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地网页 RealSense 预览和参数调整")
    parser.add_argument("--name", required=True, help="configs/camera/ 下的 JSON 文件名")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)
    state = PreviewState(args.name)
    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"RealSense 网页预览：{url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("正在关闭网页预览…")
    finally:
        server.server_close(); state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
