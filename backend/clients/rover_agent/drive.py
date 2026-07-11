"""UDP 驱动层：把轮速百分比发给 Deskbot 小车。

协议（TableBot/jiqiren.ino）：UDP:8888，文本 "L,R"，-100~100，负为倒转。
固件看门狗 1000ms 无指令自动刹车，因此本层内置保活线程持续重发最近指令；
上层每 100ms 重新计算，但普通轮速变化最多每 250ms 抢发一次；保活线程仍
每 250ms 重发最近指令。转向脉冲的开始/停止绕过限频，以保证脉冲时长。
超过 command_ttl_ms 未刷新时，保活线程改发停车。
安全要求（plan §0.6）：输出恒 clamp 到 ±100；进程退出时发停车指令。
"""
from __future__ import annotations

import atexit
import socket
import threading
import time


class RoverDrive:
    def __init__(self, ip: str, port: int = 8888, period_ms: int = 250,
                 command_ttl_ms: int = 1000, reverse: bool = False):
        self.addr = (ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lock = threading.Lock()
        self._pulse_lock = threading.Lock()
        self._pulse_timer: threading.Timer | None = None
        self._l = 0
        self._r = 0
        self._err_count = 0
        # 电机反装补偿：指令前进=物理后退的车，把两轮速同时取反
        self._sign = -1 if reverse else 1
        self._period = period_ms / 1000.0
        self._command_ttl = command_ttl_ms / 1000.0
        self._last_update = time.monotonic()
        self._last_send_time = 0.0
        self._running = True
        self._thread = threading.Thread(
            target=self._keepalive, name=f"drive-{ip}", daemon=True
        )
        self._thread.start()
        atexit.register(self.close)

    def set_wheels(self, l: float, r: float) -> None:
        self._set_wheels(l, r, immediate=False, cancel_pulse=True)

    def _set_wheels(self, l: float, r: float, *, immediate: bool,
                    cancel_pulse: bool) -> None:
        if cancel_pulse:
            self._cancel_pulse()
        l = max(-100, min(100, int(round(l * self._sign))))
        r = max(-100, min(100, int(round(r * self._sign))))
        now = time.monotonic()
        with self._lock:
            changed = (l, r) != (self._l, self._r)
            self._l, self._r = l, r
            self._last_update = now
            may_send = now - self._last_send_time >= self._period
        # 轮速没变就不抢发，交给保活线程按节拍重发——
        # ESP32 处理能力差，指令轰炸会让它卡顿掉包
        if changed and (immediate or may_send):
            self._send(l, r)

    def stop(self) -> None:
        self._set_wheels(0, 0, immediate=True, cancel_pulse=True)

    def start_pulse(self, l: float, r: float, duration_sec: float) -> None:
        """立即开始一次定时轮速脉冲，并由本机定时器立即停车。"""
        if duration_sec <= 0:
            raise ValueError("duration_sec 必须大于 0")
        self._cancel_pulse()
        self._set_wheels(l, r, immediate=True, cancel_pulse=False)
        timer = threading.Timer(duration_sec, self._finish_pulse)
        timer.daemon = True
        with self._pulse_lock:
            self._pulse_timer = timer
        timer.start()

    def _finish_pulse(self) -> None:
        with self._pulse_lock:
            self._pulse_timer = None
        self._set_wheels(0, 0, immediate=True, cancel_pulse=False)

    def _cancel_pulse(self) -> None:
        with self._pulse_lock:
            timer = self._pulse_timer
            self._pulse_timer = None
        if timer is not None:
            timer.cancel()

    def close(self) -> None:
        """停保活线程并确保停车指令发出。可重复调用。"""
        if not self._running:
            return
        self._running = False
        self._cancel_pulse()
        for _ in range(3):
            self._send(0, 0)
            time.sleep(0.02)

    def _send(self, l: int, r: int) -> None:
        with self._lock:
            self._last_send_time = time.monotonic()
        try:
            self.sock.sendto(f"{l},{r}".encode(), self.addr)
            if self._err_count:
                print(f"[drive {self.addr[0]}] UDP 恢复"
                      f"（此前连续失败 {self._err_count} 次）")
                self._err_count = 0
        except OSError as exc:
            # 不抛给控制循环（看门狗兜底刹车），但必须大声报告
            self._err_count += 1
            if self._err_count in (1, 10) or self._err_count % 100 == 0:
                print(f"[drive {self.addr[0]}] ⚠️ UDP 发送失败"
                      f"×{self._err_count}: {exc} —— 查车电源/WiFi/IP")

    def _keepalive(self) -> None:
        while self._running:
            with self._lock:
                l, r = self._l, self._r
                expired = time.monotonic() - self._last_update > self._command_ttl
            if expired:
                l, r = 0, 0
            self._send(l, r)
            time.sleep(self._period)
