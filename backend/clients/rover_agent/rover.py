"""单辆物理小车的导航状态、控制与 UDP 驱动。"""
from __future__ import annotations

import threading
import time
import math

from rover_agent.controller import step, validate_speed_level
from rover_agent.drive import RoverDrive
from rover_agent.geometry import heading_error
from rover_agent.planner import plan, plan_to_landmark


class Rover:
    """一辆真实小车；路线、速度、控制状态与驱动全部由实例自己持有。"""

    def __init__(self, robot_id: str, robot_config: dict, params: dict,
                 field, obstacle_map, zones=(), drive=None, debug=None):
        self.robot_id = robot_id
        self.car_id = robot_id
        self.config = robot_config
        self.params = params
        self.field = field
        self.obstacle_map = obstacle_map
        self.zones = list(zones or [])
        self.cell = float(params["table"].get("cell_cm", 1))
        drive_cfg = params["drive"]
        self.drive = drive or RoverDrive(
            robot_config["ip"],
            period_ms=drive_cfg["keepalive_period_ms"],
            command_ttl_ms=drive_cfg["command_ttl_ms"],
            reverse=bool(robot_config.get("reverse", False)),
        )
        self.plan: list = []
        self.full_plan: list = []
        self.trail: list = []
        self.controller_state: dict = {}
        self.speed = 10
        self._target_landmark: dict | None = None
        self._approach_phase: str | None = None
        self._landmark_confirmations = 0
        self._last_landmark_pose_ts: float | None = None
        self._status = "idle"
        self._lock = threading.RLock()
        self._closed = False
        self._tick_n = 0
        self._debug = debug or (lambda _message: None)

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @status.setter
    def status(self, value: str) -> None:
        with self._lock:
            self._status = value

    @property
    def pose(self):
        return self.field.get_pose(self.robot_id)

    @property
    def target_landmark(self) -> dict | None:
        with self._lock:
            return (dict(self._target_landmark)
                    if self._target_landmark is not None else None)

    @property
    def approach_phase(self) -> str | None:
        with self._lock:
            return self._approach_phase

    @property
    def landmark_confirmations(self) -> int:
        with self._lock:
            return self._landmark_confirmations

    @property
    def position(self) -> dict:
        snapshot = dict(self.field.position_snapshot(self.robot_id))
        snapshot["car_id"] = self.car_id
        snapshot["status"] = self.status
        target = self.target_landmark
        snapshot["target_landmark_id"] = target["id"] if target else None
        snapshot["landmark_gap_cm"] = None
        if target and snapshot["x"] is not None:
            gap = self._surface_gap((snapshot["x"], snapshot["y"]), target)
            snapshot["landmark_gap_cm"] = round(gap, 3)
        return snapshot

    def zone_center_world(self, zone_id: str):
        for zone in self.zones:
            if zone.get("id") == zone_id and zone.get("center"):
                return float(zone["center"][0]), float(zone["center"][1])
        return None

    def set_goal(self, goal_w, avoid=(), speed: int = 10) -> bool:
        try:
            speed = validate_speed_level(speed)
        except ValueError as exc:
            print(f"[agent] {self.robot_id} 速度无效: {exc}")
            return False
        if speed == 0:
            self.stop()
            return True
        pose = self._pose_for_command()
        if pose is None:
            self.status = "lost"
            print(f"[agent] {self.robot_id} 等待位姿超时，无法规划"
                  "（检查标记/标定）")
            return False
        landmark = self.obstacle_map.landmark_for_occupied_goal(goal_w)
        if landmark is not None:
            return self._start_landmark_goal(
                landmark, pose, avoid=avoid, speed=speed)
        with self._lock:
            self._clear_landmark_state()
        grid = self.obstacle_map.grid_for(avoid)
        waypoints = plan(grid, (pose.x, pose.y), goal_w, cell=self.cell)
        if waypoints is None:
            self.status = "unreachable"
            print(f"[agent] {self.robot_id} 目标不可达: {goal_w}")
            self._debug(
                f"{self.robot_id} set_goal 不可达 "
                f"起点=({pose.x:.2f},{pose.y:.2f}) "
                f"目标=({goal_w[0]:.2f},{goal_w[1]:.2f}) "
                f"avoid={list(avoid)}")
            return False
        with self._lock:
            self.plan = list(waypoints)
            self.full_plan = [(pose.x, pose.y)] + list(waypoints)
            self.trail = []
            self.controller_state = {}
            self.speed = speed
            self._status = "moving"
        print(f"[agent] {self.robot_id} → "
              f"({goal_w[0]:.1f}, {goal_w[1]:.1f})cm，"
              f"速度 {speed}，路径 {len(waypoints)} 点")
        self._debug(
            f"{self.robot_id} set_goal 起点=({pose.x:.2f},{pose.y:.2f}) "
            f"目标=({goal_w[0]:.2f},{goal_w[1]:.2f}) 速度={speed} "
            f"路径={[(round(x, 2), round(y, 2)) for x, y in waypoints]}")
        return True

    def set_landmark_goal(self, landmark_id: str, avoid=(),
                          speed: int = 10) -> bool:
        try:
            speed = validate_speed_level(speed)
        except ValueError as exc:
            print(f"[agent] {self.robot_id} 速度无效: {exc}")
            return False
        if speed == 0:
            self.stop()
            return True
        pose = self._pose_for_command()
        if pose is None:
            self.status = "lost"
            print(f"[agent] {self.robot_id} 等待位姿超时，无法规划"
                  "（检查标记/标定）")
            return False
        try:
            landmark = self.obstacle_map.get_landmark(landmark_id)
        except KeyError:
            self.status = "unreachable"
            print(f"[agent] {self.robot_id} 未知固定目标: {landmark_id}")
            return False
        return self._start_landmark_goal(
            landmark, pose, avoid=avoid, speed=speed)

    def _pose_for_command(self):
        """发令时短暂丢码则等待恢复，超时前持续重试并做最后一次读取。"""
        pose = self.pose
        if pose is not None:
            return pose
        wait_sec = max(0.0, float(
            self.params.get("vision", {}).get("command_pose_wait_sec", 2.0)))
        if wait_sec == 0:
            return self.pose
        print(f"[agent] {self.robot_id} 当前无位姿，等待最多 {wait_sec:g}s…")
        deadline = time.monotonic() + wait_sec
        while time.monotonic() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            pose = self.pose
            if pose is not None:
                print(f"[agent] {self.robot_id} 位姿已恢复，继续规划")
                return pose
        return self.pose

    def _start_landmark_goal(self, landmark: dict, pose, avoid, speed) -> bool:
        grid = self.obstacle_map.grid_for(avoid)
        control = self.params["control"]
        result = plan_to_landmark(
            grid,
            (pose.x, pose.y),
            landmark,
            robot_radius_cm=self.params["planner"]["robot_radius_cm"],
            preapproach_gap_cm=control.get(
                "landmark_preapproach_gap_cm", 4),
            samples=int(control.get("landmark_approach_samples", 24)),
            cell=self.cell,
        )
        if result is None:
            self.status = "unreachable"
            print(f"[agent] {self.robot_id} 固定目标不可达: {landmark['id']}")
            return False
        waypoints, approach = result
        with self._lock:
            self.plan = list(waypoints)
            self.full_plan = [(pose.x, pose.y)] + list(waypoints)
            self.trail = []
            self.controller_state = {}
            self.speed = speed
            self._target_landmark = dict(landmark)
            self._approach_phase = "route"
            self._landmark_confirmations = 0
            self._last_landmark_pose_ts = None
            self._status = "moving"
        print(f"[agent] {self.robot_id} → 固定目标 {landmark['id']}，"
              f"接近点 ({approach[0]:.1f}, {approach[1]:.1f})cm，"
              f"速度 {speed}")
        return True

    def goto(self, x_cm: float, y_cm: float, wait: bool = False,
             timeout: float = 90.0, poll_s: float = 0.1,
             speed: int = 10) -> bool:
        if not self.set_goal((float(x_cm), float(y_cm)), speed=speed):
            return False
        return self._wait_for_arrival(wait, timeout, poll_s)

    def goto_landmark(self, landmark_id: str, wait: bool = False,
                      timeout: float = 90.0, poll_s: float = 0.1,
                      speed: int = 10, avoid=()) -> bool:
        if not self.set_landmark_goal(
                landmark_id, avoid=avoid, speed=speed):
            return False
        return self._wait_for_arrival(wait, timeout, poll_s)

    def _wait_for_arrival(self, wait, timeout, poll_s) -> bool:
        if not wait:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.status
            if state == "arrived":
                return True
            if state in ("idle", "unreachable", "too_close"):
                return False
            time.sleep(poll_s)
        self.stop()
        return False

    def goto_zone(self, zone_id: str, **kwargs) -> bool:
        target = self.zone_center_world(zone_id)
        if target is None:
            print(f"[fleet] 未知 zone: {zone_id}")
            return False
        return self.goto(*target, **kwargs)

    def tick(self) -> None:
        pose = self.pose
        with self._lock:
            self._tick_n += 1
            if pose is not None:
                if (not self.trail
                        or (pose.x - self.trail[-1][0]) ** 2
                        + (pose.y - self.trail[-1][1]) ** 2 > 0.5 ** 2):
                    self.trail.append((pose.x, pose.y))
                    del self.trail[:-3000]
            landmark_creep = (
                self._target_landmark is not None
                and self._approach_phase == "creep")
            if not self.plan and not landmark_creep:
                return
            if pose is None:
                self.drive.stop()
                if self._status != "lost":
                    self._debug(f"{self.robot_id} 位姿丢失 → 刹车等恢复")
                self._status = "lost"
                return
            if self._status == "lost":
                self._status = "approaching" if landmark_creep else "moving"
                self._debug(
                    f"{self.robot_id} 位姿恢复 ({pose.x:.2f},{pose.y:.2f})")
            if landmark_creep:
                self._tick_landmark_creep(pose)
                return
            left, right, remaining, done = step(
                pose,
                self.plan,
                self.params["control"],
                self.controller_state,
                speed=self.speed,
            )
            self.plan = remaining
            if done:
                self.drive.stop()
                if self._target_landmark is not None:
                    self.controller_state = {}
                    self._approach_phase = "creep"
                    self._landmark_confirmations = 0
                    self._last_landmark_pose_ts = None
                    self._status = "approaching"
                    self._debug(
                        f"{self.robot_id} 到达预接近点 → 低速贴近 "
                        f"{self._target_landmark['id']}")
                    return
                self._status = "arrived"
                print(f"[agent] {self.robot_id} 到达")
                self._debug(
                    f"{self.robot_id} 到达 ({pose.x:.2f},{pose.y:.2f})")
                return
            self.drive.set_wheels(left, right)
            if self._tick_n % 12 == 0:
                error = heading_error(pose, remaining[0])
                self._debug(
                    f"{self.robot_id} pose=({pose.x:.2f},{pose.y:.2f},"
                    f"{pose.theta:.2f}) wp={remaining[0][0]:.2f},"
                    f"{remaining[0][1]:.2f} 余{len(remaining)}点 "
                    f"err={error:.2f}rad 轮速=({left},{right}) "
                    f"udp_err={getattr(self.drive, '_err_count', 0)}")

    def _surface_gap(self, point, landmark: dict) -> float:
        center_distance = math.hypot(
            float(point[0]) - float(landmark["x_cm"]),
            float(point[1]) - float(landmark["y_cm"]),
        )
        return (center_distance - float(landmark["radius_cm"])
                - float(self.params["planner"]["robot_radius_cm"]))

    def _tick_landmark_creep(self, pose) -> None:
        landmark = self._target_landmark
        if landmark is None:
            return
        control = self.params["control"]
        gap = self._surface_gap((pose.x, pose.y), landmark)
        gap_min = float(control.get("landmark_gap_min_cm", 1))
        gap_max = float(control.get("landmark_gap_max_cm", 2))
        confirm_frames = int(control.get("landmark_confirm_frames", 2))
        if gap < gap_min:
            self.drive.stop()
            self._landmark_confirmations = 0
            self._last_landmark_pose_ts = None
            self._status = "too_close"
            self._debug(
                f"{self.robot_id} 距 {landmark['id']} 过近 gap={gap:.2f}cm")
            return
        if gap <= gap_max:
            self.drive.stop()
            if pose.ts != self._last_landmark_pose_ts:
                self._landmark_confirmations += 1
                self._last_landmark_pose_ts = pose.ts
            self._status = "approaching"
            if self._landmark_confirmations >= confirm_frames:
                self._status = "arrived"
                print(f"[agent] {self.robot_id} 到达固定目标 {landmark['id']} "
                      f"(gap={gap:.1f}cm)")
            return
        self._landmark_confirmations = 0
        self._last_landmark_pose_ts = None
        self._status = "approaching"
        creep_speed = int(control.get("landmark_creep_speed", 1))
        creep_control = dict(control)
        creep_control["waypoint_tol_cm"] = 0
        creep_control["arrive_tol_cm"] = 0
        left, right, _, _ = step(
            pose,
            [(float(landmark["x_cm"]), float(landmark["y_cm"]))],
            creep_control,
            self.controller_state,
            speed=creep_speed,
        )
        self.drive.set_wheels(left, right)

    def stop(self) -> None:
        with self._lock:
            self.plan = []
            self.controller_state = {}
            self._clear_landmark_state()
            self.drive.stop()
            self._status = "idle"

    def _clear_landmark_state(self) -> None:
        self._target_landmark = None
        self._approach_phase = None
        self._landmark_confirmations = 0
        self._last_landmark_pose_ts = None

    def acknowledge_arrival(self) -> None:
        with self._lock:
            if self._status == "arrived":
                self._status = "idle"
                self._clear_landmark_state()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.stop()
            self.drive.close()
            self._closed = True

    def __repr__(self) -> str:
        return f"Rover({self.robot_id}, status={self.status})"
