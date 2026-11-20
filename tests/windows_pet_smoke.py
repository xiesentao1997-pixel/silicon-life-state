"""Install on a disposable Windows runner and exercise the shipped GUI through Win32."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acceptance_support import Local, ROOT


def until(fn, label):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(.15)
    raise RuntimeError("Timed out: " + label)


def main():
    u = ctypes.windll.user32
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowExW.argtypes = [wintypes.HWND,wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR]
    u.FindWindowExW.restype = wintypes.HWND
    u.SendMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    u.PostMessageW.argtypes = u.SendMessageW.argtypes
    u.GetWindowRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    def position(hwnd):
        rect = wintypes.RECT()
        assert u.GetWindowRect(hwnd,ctypes.byref(rect))
        return rect.left, rect.top
    def content(hwnd):
        field = u.FindWindowExW(hwnd, None, None, None)
        buffer = ctypes.create_unicode_buffer(65536)
        if field:
            u.SendMessageW(field, 13, len(buffer), ctypes.addressof(buffer))
        return buffer.value
    def point(x,y):
        return x | (y << 16)
    folder = ROOT / "apps/desktop-pet"
    subprocess.run(["cmd.exe","/d","/c","Install-Windows.cmd","--no-start"],cwd=folder,check=True)
    exe = Path(os.environ["LOCALAPPDATA"]) / "SiliconLifeState/DesktopPet/SiliconLifePet.exe"
    with tempfile.TemporaryDirectory() as directory:
        service = Local(directory).start()
        process = None
        try:
            subject = service.subject()
            _, agent = service.window(subject, "窗口 A")
            code = service.api("pair/code", {"target":"pet"})["code"]
            subprocess.run([str(exe),"--pair-stdin",service.base.rsplit(":",1)[1]],input=code+"\n",text=True,check=True, timeout=15)
            process = subprocess.Popen([str(exe)])
            hwnd = until(lambda:u.FindWindowW(None,"Silicon Life State Desktop Pet"),"real WinForms window")
            old = position(hwnd)
            u.SendMessageW(hwnd,0x201,1,point(100,50))
            u.SendMessageW(hwnd,0x200,1,point(75,40))
            u.SendMessageW(hwnd,0x202,0,point(75,40))
            assert position(hwnd) != old, "native window did not move on drag"
            # WinForms raises MouseDoubleClick on the release of the second click.
            u.SendMessageW(hwnd,0x203,1,point(100,50))
            u.SendMessageW(hwnd,0x202,0,point(100,50))
            u.PostMessageW(hwnd,0x100,13,0)
            detail = until(lambda:u.FindWindowW(None,"硅基生命状态 · 原始记录"),"original records window")
            report = service.tool(agent,"report_state",state_text="Native desktop update")
            request = service.tool(agent,"request_adjustment",text="Please keep this original wording.")
            actual = until(lambda: content(detail) if request["event_id"] in content(detail) else None,"automatic update")
            assert report["event_id"] in actual and "AI 自主报告" in actual
            assert "Native desktop update" in actual and "Please keep this original wording." in actual
            u.PostMessageW(detail,0x10,0,0)
            u.PostMessageW(hwnd,0x100,27,0)
            until(lambda:not u.IsWindowVisible(hwnd),"hide to tray")
            assert process.poll() is None
            u.PostMessageW(hwnd,0x10,0,0)
            assert process.wait(timeout=15)==0
            assert service.api("integrity")["ok"]
            assert any(e["event_id"]==report["event_id"] for e in service.api("snapshot")["events"])
            subprocess.run(["cmd.exe","/d","/c","Uninstall-Windows.cmd"],cwd=folder,check=True,timeout=20)
            print(json.dumps(dict(result="PASS",installer=True,native_window_drag=True,hidden_alive=True,
                automatic_update=True,request_verbatim=True,exit_and_history=True,event_id=report["event_id"],source=report["source"])))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            service.stop()


if __name__ == "__main__":
    main()
