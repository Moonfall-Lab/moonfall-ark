"""多车运行时入口：共享一套场地感知，协调彼此独立的 Rover 对象。

用法（先由 setup_field 生成 params.yaml）::

    from rover_agent.fleet import Fleet

    with Fleet(camera=0) as fleet:
        fleet.wait_ready()
        fleet.car("r0").goto(30, 40, speed=3, wait=True)
        print(fleet.get_position("r0"))

Fleet 只负责生命周期和批量调度；位姿归 FieldTracker，路线、控制状态和
UDP 驱动归各自 Rover。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from rover_agent.field_tracker import FieldTracker
from rover_agent.obstacle_map import ObstacleMap
from rover_agent.rover import Rover
from rover_agent.viz import load_params

DEBUG_LOG = "rover_agent_debug.log"


def load_zones(config_path: str) -> list[dict]:
    """读取游戏配置中会参与规划的地图区域。"""
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)
    return config.get("map", {}).get("zones", [])


class Fleet:
    """场地感知和多辆 Rover 的薄协调器。"""

    def __init__(self, camera: int = 0, params=None,
                 config: str | None = None, source=None, field=None,
                 rover_factory=Rover, health: bool = True,
                 start: bool = True, debug=None, obstacles=None,
                 landmarks=None, transient_obstacles=None):
        self.params = params if isinstance(params, dict) else load_params(params)
        self.zones = load_zones(config) if config else []
        if obstacles is not None and landmarks is not None:
            raise ValueError("obstacles 与 landmarks 不能同时传入")
        fixed = (landmarks if landmarks is not None else obstacles)
        if fixed is None:
            fixed = self.params.get(
                "landmarks", self.params.get("obstacles", ()))
        self.obstacle_map = ObstacleMap(
            self.params,
            zones=self.zones,
            landmarks=fixed,
            transient=transient_obstacles,
        )
        self.control_period_s = (
            float(self.params["control"]["correction_period_ms"]) / 1000.0
        )
        self.field = field or FieldTracker(
            self.params, camera=camera, source=source)

        self._debug_file = None
        if debug is None:
            self._debug_file = open(
                DEBUG_LOG, "a", encoding="utf-8", buffering=1)
            self._debug = self._write_debug
        else:
            self._debug = debug

        self._rovers = {
            robot_id: rover_factory(
                robot_id,
                robot_config,
                self.params,
                self.field,
                self.obstacle_map,
                self.zones,
                debug=self._debug,
            )
            for robot_id, robot_config in self.params["robots"].items()
        }
        self._health_enabled = health
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lifecycle_lock = threading.Lock()
        self._started = False
        self._shutdown = False
        self._debug(f"===== fleet 启动 robots={list(self._rovers)} =====")
        if start:
            self.start()

    def _write_debug(self, message: str) -> None:
        if self._debug_file is not None:
            self._debug_file.write(
                f"{time.strftime('%H:%M:%S')} {message}\n")

    # ---- 生命周期 ----
    def start(self) -> "Fleet":
        with self._lifecycle_lock:
            if self._shutdown:
                raise RuntimeError("Fleet 已关闭，不能再次启动")
            if self._started:
                return self
            self._started = True
            self._stop_event.clear()

        self.field.start()
        specs = [("control", self._control_loop)]
        if self._health_enabled:
            specs.append(("health", self._health_loop))
        for name, target in specs:
            thread = threading.Thread(
                target=target, name=f"fleet-{name}", daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def shutdown(self) -> None:
        with self._lifecycle_lock:
            if self._shutdown:
                return
            self._shutdown = True
            self._stop_event.set()

        self.stop_all()
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1.0)
        for rover in self._rovers.values():
            rover.close()
        self.field.stop()
        if self._debug_file is not None:
            self._debug_file.close()
            self._debug_file = None

    def __enter__(self) -> "Fleet":
        return self

    def __exit__(self, *_exc) -> None:
        self.shutdown()

    # ---- 协调 ----
    def rover(self, robot_id: str) -> Rover:
        try:
            return self._rovers[robot_id]
        except KeyError:
            raise KeyError(
                f"未知车辆 {robot_id}，params.yaml 里已登记: "
                f"{list(self._rovers)}") from None

    def car(self, car_id: str) -> Rover:
        """按对外 car_id 取车；r0..r3 与车顶标记 0..3 一一对应。"""
        return self.rover(car_id)

    @property
    def rovers(self) -> dict[str, Rover]:
        return dict(self._rovers)

    def tick(self) -> None:
        for rover in self._rovers.values():
            rover.tick()

    def stop_all(self) -> None:
        for rover in self._rovers.values():
            rover.stop()
        print("[agent] 全场急停")

    def wait_ready(self, timeout: float = 30.0, robots=None) -> bool:
        """等待标定和指定车辆位姿就绪；robots 省略时等待全部车辆。"""
        wanted = list(robots) if robots is not None else list(self._rovers)
        for robot_id in wanted:
            self.rover(robot_id)
        ready = self.field.wait_ready(wanted, timeout=timeout)
        if ready:
            return True

        missing = []
        get_pose = getattr(self.field, "get_pose", None)
        if get_pose is not None:
            missing = [rid for rid in wanted if get_pose(rid) is None]
        calibrated = getattr(self.field, "calibrated", False)
        print(f"[fleet] wait_ready 超时: calibrated={calibrated} "
              f"未见车={missing or wanted}（查四角码/车顶码遮挡）")
        return False

    def get_position(self, car_id: str) -> dict:
        """返回最后位置；短暂丢码时仍可通过 fresh/age_ms 判断新鲜度。"""
        return self.car(car_id).position

    @property
    def trails(self) -> dict[str, list]:
        return {rid: rover.trail for rid, rover in self._rovers.items()}

    @property
    def paths(self) -> dict[str, list]:
        return {rid: rover.full_plan for rid, rover in self._rovers.items()}

    @property
    def base_grid(self):
        return self.obstacle_map.grid_for()

    def _ensure_map_idle(self) -> None:
        active = [
            rid for rid, rover in self._rovers.items()
            if (rover.plan
                or rover.status == "approaching"
                or (rover.status == "lost"
                    and getattr(rover, "approach_phase", None) is not None))
        ]
        if active:
            raise RuntimeError(f"车辆仍有未完成路线: {active}")

    def get_obstacles(self) -> dict:
        """兼容接口：返回固定目标和临时障碍的分层快照及并集。"""
        return self.obstacle_map.snapshot()

    def get_landmarks(self) -> dict:
        return self.obstacle_map.landmarks_snapshot()

    def get_transient_obstacles(self) -> dict:
        return self.obstacle_map.transient_snapshot()

    def replace_obstacles(self, obstacles) -> dict:
        """兼容旧接口：手动障碍视为固定目标。"""
        return self.replace_landmarks(obstacles)

    def replace_landmarks(self, landmarks) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.replace_landmarks(landmarks)

    def upsert_obstacle(self, obstacle) -> dict:
        return self.upsert_landmark(obstacle)

    def upsert_landmark(self, landmark) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.upsert_landmark(landmark)

    def remove_obstacle(self, obstacle_id: str) -> dict:
        return self.remove_landmark(obstacle_id)

    def remove_landmark(self, landmark_id: str) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.remove_landmark(landmark_id)

    def replace_transient_obstacles(self, obstacles) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.replace_transient(obstacles)

    def upsert_transient_obstacle(self, obstacle) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.upsert_transient(obstacle)

    def remove_transient_obstacle(self, obstacle_id: str) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.remove_transient(obstacle_id)

    def clear_transient_obstacles(self) -> dict:
        self._ensure_map_idle()
        return self.obstacle_map.clear_transient()

    def _control_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(self.control_period_s)

    def _health_loop(self) -> None:
        """空闲时每 10 秒探测车辆 HTTP 状态，连续失败才报警。"""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        failures = {rid: 0 for rid in self._rovers}
        while not self._stop_event.is_set():
            for rid, rover in self._rovers.items():
                if self._stop_event.is_set():
                    break
                if rover.status == "moving":
                    continue
                ip = rover.drive.addr[0]
                try:
                    with opener.open(f"http://{ip}/status", timeout=3) as resp:
                        resp.read()
                    if failures[rid] >= 3:
                        print(f"[health] {rid}@{ip} 恢复可达")
                        self._debug(f"{rid}@{ip} HTTP 恢复")
                    failures[rid] = 0
                except OSError:
                    failures[rid] += 1
                    count = failures[rid]
                    if count in (3, 6) or count % 30 == 0:
                        print(f"[health] ⚠️ {rid}@{ip} 连续 {count} 次不可达"
                              "——查车电源/电池/WiFi/OLED 上的 IP")
                        self._debug(
                            f"{rid}@{ip} HTTP 连续 {count} 次不可达")
            self._stop_event.wait(10)
