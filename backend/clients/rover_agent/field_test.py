"""M1/M2 自动化场地测试：标定 → 定位抖动 → 满场巡游，输出成败报告。

用法（repo 根目录，终端里跑）:
    PYTHONPATH=backend/clients python -m rover_agent.field_test --camera 0 --robot r1
    只测定位不动车: 追加 --skip-drive

流程：
1. 等待四角标定（30s 超时）；
2. 找到车顶标记，静止采 5s 位姿，报告抖动（标准差，阈值 1cm）；
3. 巡游：中心 → 四角附近 → 回中心，共 6 段，逐段记录 距离/用时/停点误差/成败；
4. 打印报告并写入 field_test_report.txt。

窗口在实景画面叠加坐标、障碍、路径与轨迹；空格 = 全场急停，q = 中止。
"""
from __future__ import annotations

import argparse
import statistics
import threading
import time

import cv2

from rover_agent.fleet import Fleet
from rover_agent.geometry import dist
from rover_agent.overlay import draw_overlay
from rover_agent.planner import planning_margin_cm
from rover_agent.viz import FONT, load_params


def wait_until(cond, timeout: float, poll: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(poll)
    return False


class FieldTest:
    def __init__(self, fleet: Fleet, robot: str, skip_drive: bool):
        self.fleet = fleet
        self.field = fleet.field
        self.rover = fleet.rover(robot)
        self.calib = self.field.calibrator
        self.robot = robot
        self.skip_drive = skip_drive
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

    def _run(self) -> None:
        rid = self.robot
        self.log(f"=== rover_agent 场地测试 {time.strftime('%H:%M:%S')} ===")

        # 1. 标定
        if not wait_until(lambda: self.calib.calibrated or self.aborted, 30):
            self.log("FAIL [标定] 30s 内未同时看到 4 个角标记（看 camera 窗口缺哪个）")
            return
        if self.aborted:
            return
        assigned = self.calib.assigned or self.calib.marker_ids
        self.log(f"PASS [标定] 角分配（左下→右下→右上→左上）: {assigned}")

        # 2. 车辆定位与静态抖动
        if not wait_until(lambda: self.rover.pose is not None
                          or self.aborted, 15):
            self.log(f"FAIL [定位] 15s 内未看到 {rid} 的车顶标记（贴了吗？字典对吗？）")
            return
        xs, ys = [], []
        t0 = time.time()
        while time.time() - t0 < 5 and not self.aborted:
            pose = self.rover.pose
            if pose:
                xs.append(pose.x)
                ys.append(pose.y)
            time.sleep(0.1)
        if len(xs) < 10:
            self.log(f"FAIL [定位] 5s 内仅 {len(xs)} 次有效位姿，检测太不稳定")
            return
        jx, jy = statistics.pstdev(xs), statistics.pstdev(ys)
        pose = self.rover.pose
        verdict = "PASS" if max(jx, jy) < 1.0 else "WARN"
        self.log(f"{verdict} [定位] {len(xs)} 帧，当前 ({pose.x:.1f},{pose.y:.1f})cm，"
                 f"抖动 std x={jx:.2f}cm y={jy:.2f}cm（阈值 1cm，车须静止）")

        if self.skip_drive:
            self.log("SKIP [巡游] --skip-drive 已指定")
            return

        # 3. 满场巡游
        w = float(self.fleet.params["table"]["width_cm"])
        h = float(self.fleet.params["table"]["height_cm"])
        m = 12  # 距角落边距，避开角标记纸
        legs = [("去中心", (w / 2, h / 2)), ("左下角", (m, m)),
                ("右下角", (w - m, m)), ("右上角", (w - m, h - m)),
                ("左上角", (m, h - m)), ("回中心", (w / 2, h / 2))]
        passed = 0
        for name, goal in legs:
            if self.aborted:
                self.log("ABORT 用户中止")
                return
            start_pose = self.rover.pose
            if start_pose is None:
                self.log(f"FAIL [{name}] 出发时位姿丢失")
                continue
            leg_dist = dist((start_pose.x, start_pose.y), goal)
            if not self.rover.set_goal(goal):
                self.log(f"FAIL [{name}] 规划失败（目标被障碍占用或位姿丢失）")
                continue
            t0 = time.time()
            arrived = wait_until(
                lambda: self.rover.status == "arrived" or self.aborted, 40)
            elapsed = time.time() - t0
            end_pose = self.rover.pose
            err_cm = (dist((end_pose.x, end_pose.y), goal)
                      if end_pose else float("nan"))
            if arrived and not self.aborted:
                passed += 1
                self.log(f"PASS [{name}] 行程 {leg_dist:.1f}cm 用时 {elapsed:.1f}s "
                         f"停点误差 {err_cm:.1f}cm")
            else:
                self.fleet.stop_all()
                self.log(f"FAIL [{name}] 40s 未到达，剩余误差 {err_cm:.1f}cm，"
                         f"状态 {self.rover.status}")
            time.sleep(0.6)
        self.log(f"=== 巡游 {passed}/{len(legs)} 段通过 ===")


def main() -> None:
    ap = argparse.ArgumentParser(description="rover_agent 自动化场地测试")
    ap.add_argument("--params", default=None)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--robot", default="r1")
    ap.add_argument("--skip-drive", action="store_true", help="只测定位不动车")
    args = ap.parse_args()

    params = load_params(args.params)
    fleet = Fleet(camera=args.camera, params=params, health=False)
    test = FieldTest(fleet, args.robot, args.skip_drive)

    threading.Thread(
        target=test.run, name="fieldtest", daemon=True).start()

    # 主线程：取帧 + 检测 + UI（macOS 的 cv2 窗口必须在主线程）
    cam_w = 960
    print("窗口按键: 空格=急停  q=中止")
    try:
        while not test.done:
            frame, found = fleet.field.visual_snapshot()
            if frame is not None:
                frame = frame.copy()
                for mid, quad in found.items():
                    cv2.polylines(frame, [quad.astype(int).reshape(-1, 1, 2)],
                                  True, (0, 255, 0), 3)
                    cv2.putText(frame, str(mid), tuple(quad[0].astype(int)),
                                FONT, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
                status_line = (test.report[-1][:80] if test.report else "启动中")
                cv2.putText(frame, status_line, (10, 45), FONT, 0.9,
                            (0, 255, 255), 2, cv2.LINE_AA)
                frame = draw_overlay(
                    frame, fleet.field.calibrator, fleet.get_obstacles(),
                    robot_states=fleet.rovers, paths=fleet.paths,
                    trails=fleet.trails,
                    robot_radius_cm=planning_margin_cm(params))
                h = int(frame.shape[0] * cam_w / frame.shape[1])
                cv2.imshow("camera", cv2.resize(frame, (cam_w, h)))
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
        cv2.destroyAllWindows()
        with open("field_test_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(test.report) + "\n")
        print("\n报告已存 field_test_report.txt")


if __name__ == "__main__":
    main()
