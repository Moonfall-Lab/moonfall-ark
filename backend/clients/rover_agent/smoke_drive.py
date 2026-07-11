"""M0 冒烟测试：对真车验证 UDP 协议与看门狗行为。

用法（repo 根目录）:
    PYTHONPATH=backend/clients python -m rover_agent.smoke_drive <车IP>

预期：车依次 前进1s → 停1s → 原地左转1s → 停；
第 5 步只发一包后静默 1.3s，车应在约 1000ms 后被固件看门狗自动刹车；
最后打印 /status 回读的轮速。
"""
from __future__ import annotations

import socket
import sys
import time
import urllib.request

UDP_PORT = 8888
SEND_PERIOD = 0.25  # 现场实测稳定节奏，仍显著小于固件 1000ms 看门狗


def send_for(sock: socket.socket, addr, l: int, r: int, seconds: float) -> None:
    t0 = time.time()
    while time.time() - t0 < seconds:
        sock.sendto(f"{l},{r}".encode(), addr)
        time.sleep(SEND_PERIOD)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m rover_agent.smoke_drive <车IP>")
        return 1
    ip = sys.argv[1]
    addr = (ip, UDP_PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("1) 前进 1s")
    send_for(sock, addr, 60, 60, 1.0)
    print("2) 停 1s")
    send_for(sock, addr, 0, 0, 1.0)
    print("3) 原地左转 1s")
    send_for(sock, addr, -40, 40, 1.0)
    print("4) 停")
    send_for(sock, addr, 0, 0, 0.3)
    print("5) 看门狗验证：发一包前进后静默 1.3s → 车应约 1s 后刹车")
    sock.sendto(b"40,40", addr)
    time.sleep(1.3)
    print("6) 读 /status")
    try:
        with urllib.request.urlopen(f"http://{ip}/status", timeout=2) as resp:
            print("   status:", resp.read().decode())
    except OSError as exc:
        print("   status 读取失败:", exc)
    send_for(sock, addr, 0, 0, 0.2)
    print("完成。若第 5 步车约 1s 后自己停 → 看门狗正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
