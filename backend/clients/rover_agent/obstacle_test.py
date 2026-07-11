"""绕障联调测试：中心圆柱 + 两侧往返穿越，验证路径规划与实际轨迹。

用法（repo 根目录，终端里跑）:
    PYTHONPATH=backend/clients python -m rover_agent.obstacle_test --camera 0 --robot r1
    指定障碍: --obstacle 40,30,5  （x_cm,y_cm,半径_cm；缺省取 params.yaml 第一项）

流程：标定 → 找车 → 就位到障碍左侧 → 穿越到右侧（直线被障碍挡住，必须绕行）→
返回左侧 → 报告存 obstacle_test_report.txt，轨迹图存 obstacle_test_trace.png。

⚠️ 本测试特意只调用对上封装的公开接口，顺带验收 API：
    params["landmarks"]          固定目标配置（自动栅格化 + 车体膨胀）
    Fleet(params)                初始化共享感知与多车运行时
    rover.set_goal((x, y))       下发目标点（内部 A* 绕障规划）
    rover.pose / rover.status    实时位姿与单车状态
    fleet.stop_all()             全场急停
窗口按键: 空格=急停  q=中止
"""
from __future__ import annotations

import argparse
import math
import threading
import time

import cv2

from rover_agent.fleet import Fleet
from rover_agent.geometry import dist
from rover_agent.overlay import draw_overlay
from rover_agent.planner import planning_margin_cm
from rover_agent.viz import FONT, load_params, render_topview


def wait_until(cond, timeout: float, poll: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(poll)
    return False


def seg_dist(p, a, b) -> float:
    """点 p 到线段 ab 的距离。"""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return dist(p, (ax + t * dx, ay + t * dy))


def polyline_clearance(pts, center) -> float:
    """折线到障碍圆心的最小距离。"""
    if len(pts) < 2:
        return dist(pts[0], center) if pts else float("inf")
    return min(seg_dist(center, pts[i], pts[i + 1])
               for i in range(len(pts) - 1))


class ObstacleTest:
    def __init__(self, fleet: Fleet, robot: str,
                 obstacle: tuple[float, float, float]):
        self.fleet = fleet
        self.field = fleet.field
        self.rover = fleet.rover(robot)
        self.calib = self.field.calibrator
        self.robot = robot
        self.obstacle = obstacle
        self.trails: dict[str, list] = {}  # 段名 → [(x,y)...]，UI 实时画
        self.report: list[str] = []
        self.done = False
        self.aborted = False

    def log(self, line: str) -> None:
        print(line, flush=True)
        self.report.append(line)

    def run(self) -> None:
        try:
            self._run()
        finally:
            self.fleet.stop_all()
            self.done = True

    # ── 单段行驶：只用公开接口，同时采样轨迹 ──
    def _drive(self, name: str, goal, timeout: float = 45.0):
        rid = self.robot
        pose = self.rover.pose
        if pose is None:
            self.log(f"FAIL [{name}] 出发时位姿丢失")
            return None
        if not self.rover.set_goal(goal):
            self.log(f"FAIL [{name}] 规划失败（状态 {self.rover.status}）")
            return None
        planned = list(self.rover.full_plan)
        trail = self.trails.setdefault(name, [])
        t0 = time.time()
        while time.time() - t0 < timeout and not self.aborted:
            p = self.rover.pose
            if p:
                trail.append((p.x, p.y))
            if self.rover.status == "arrived":
                break
            time.sleep(0.1)
        arrived = self.rover.status == "arrived" and not self.aborted
        if not arrived:
            self.fleet.stop_all()
        return {"arrived": arrived, "elapsed": time.time() - t0,
                "trail": trail, "planned": planned}

    def _run(self) -> None:
        rid = self.robot
        ox, oy, orad = self.obstacle
        self.log(f"=== 绕障联调测试 {time.strftime('%H:%M:%S')} ===")
        self.log(f"障碍圆柱: 圆心 ({ox:.1f}, {oy:.1f})cm，半径 {orad:.1f}cm；"
                 f"栅格中已按 +车体/安全距离 "
                 f"{planning_margin_cm(self.fleet.params):.1f}cm 膨胀")

        if not wait_until(lambda: self.calib.calibrated or self.aborted, 30):
            self.log("FAIL [标定] 30s 内未同时看到 4 个角标记")
            return
        if not wait_until(lambda: self.rover.pose is not None
                          or self.aborted, 15):
            self.log(f"FAIL [定位] 15s 内未看到 {rid} 的车顶标记")
            return
        if self.aborted:
            return
        self.log("PASS [就绪] 标定与车辆定位正常")

        # 障碍两侧取 A/B 点：直线 A→B 恰好穿过障碍，逼出绕行
        w = float(self.fleet.params["table"]["width_cm"])
        h = float(self.fleet.params["table"]["height_cm"])
        span = 25
        pt_a = (max(10, ox - span), min(max(10, oy), h - 10))
        pt_b = (min(w - 10, ox + span), pt_a[1])
        line_clear = seg_dist((ox, oy), pt_a, pt_b)
        self.log(f"起终点 A({pt_a[0]:.2f},{pt_a[1]:.2f}) ↔ "
                 f"B({pt_b[0]:.2f},{pt_b[1]:.2f})；"
                 f"A-B 直线距障碍圆心 {line_clear:.1f}cm "
                 f"（< 半径 {orad:.0f}cm，直穿必撞 → 必须绕行）")

        if self._drive("就位", pt_a) is None or self.aborted:
            return
        time.sleep(0.8)

        passed = 0
        for name, start, goal in (("去程", pt_a, pt_b), ("回程", pt_b, pt_a)):
            if self.aborted:
                self.log("ABORT 用户中止")
                return
            res = self._drive(name, goal)
            if res is None:
                continue
            trail = res["trail"]
            planned_clear = polyline_clearance(res["planned"], (ox, oy))
            if len(trail) >= 2:
                path_len = sum(dist(trail[i], trail[i + 1])
                               for i in range(len(trail) - 1))
                actual_clear = min(dist(p, (ox, oy)) for p in trail)
            else:
                path_len, actual_clear = 0.0, float("nan")
            straight = dist(start, goal)
            end_err = dist(trail[-1], goal) if trail else float("nan")
            ok = res["arrived"] and actual_clear >= orad
            if ok:
                passed += 1
            self.log(f"{'PASS' if ok else 'FAIL'} [{name}] "
                     f"{'到达' if res['arrived'] else '未到达'} "
                     f"用时 {res['elapsed']:.1f}s，停点误差 {end_err:.1f}cm")
            self.log(f"      规划: {len(res['planned'])} 点，"
                     f"折线距障碍圆心最近 {planned_clear:.1f}cm；"
                     f"实际: 走了 {path_len:.1f}cm（直线 {straight:.1f}cm，"
                     f"绕行系数 {path_len / straight:.2f}），"
                     f"轨迹距圆心最近 {actual_clear:.1f}cm"
                     f"（圆柱半径 {orad:.0f}cm）")
            time.sleep(0.8)

        self.log(f"=== 绕障往返 {passed}/2 段通过 ===")
        self.log("本测试全程仅调用封装接口: params.landmarks / Fleet / "
                 "Rover.set_goal / pose / status / stop_all")


def main() -> None:
    ap = argparse.ArgumentParser(description="rover_agent 绕障联调测试")
    ap.add_argument("--params", default=None)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--robot", default="r1")
    ap.add_argument("--obstacle", default=None,
                    help="x_cm,y_cm,radius_cm，缺省取 params.yaml 第一项")
    args = ap.parse_args()

    params = load_params(args.params)
    if args.obstacle:
        x, y, r = (float(v) for v in args.obstacle.split(","))
        params["landmarks"] = [{"id": "cli", "shape": "circle",
                                "x_cm": x, "y_cm": y, "radius_cm": r}]
    records = params.get("landmarks", params.get("obstacles", ()))
    if not records:
        ap.error("没有固定目标；先运行 setup_field，或传 --obstacle x,y,r")
    obs = records[0]
    obstacle = (float(obs["x_cm"]), float(obs["y_cm"]),
                float(obs["radius_cm"]))

    fleet = Fleet(camera=args.camera, params=params, health=False)
    test = ObstacleTest(fleet, args.robot, obstacle)

    threading.Thread(target=test.run, name="obstacletest", daemon=True).start()

    cam_w = 960
    print("窗口按键: 空格=急停  q=中止")
    try:
        while not test.done:
            frame, found = fleet.field.visual_snapshot()
            if frame is not None:
                frame = frame.copy()
                for mid, quad in found.items():
                    cv2.polylines(frame, [quad.astype(int).reshape(-1, 1, 2)],
                                  True, (0, 255, 0), 2)
                status_line = (test.report[-1][:90] if test.report else "启动中")
                cv2.putText(frame, status_line, (10, 45), FONT, 0.8,
                            (0, 255, 255), 2, cv2.LINE_AA)
                frame = draw_overlay(
                    frame, fleet.field.calibrator, fleet.get_obstacles(),
                    robot_states=fleet.rovers, paths=fleet.paths,
                    trails=test.trails,
                    robot_radius_cm=planning_margin_cm(params))
                fh = int(frame.shape[0] * cam_w / frame.shape[1])
                cv2.imshow("camera", cv2.resize(frame, (cam_w, fh)))
            key = cv2.waitKey(30) & 0xFF
            if key == ord(" "):
                fleet.stop_all()
            elif key == ord("q"):
                test.aborted = True
                fleet.stop_all()
        time.sleep(0.5)
    except KeyboardInterrupt:
        test.aborted = True
    finally:
        fleet.shutdown()
        trace = render_topview(fleet.field.store, params, grid=fleet.base_grid,
                               calibrated=True, trails=test.trails)
        cv2.imwrite("obstacle_test_trace.png", trace)
        cv2.destroyAllWindows()
        with open("obstacle_test_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(test.report) + "\n")
        print("\n报告: obstacle_test_report.txt  轨迹图: obstacle_test_trace.png")


if __name__ == "__main__":
    main()
