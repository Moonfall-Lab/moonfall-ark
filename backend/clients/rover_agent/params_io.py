"""params.yaml 的定点写回工具——初始化程序（setup_field）落盘用。

统一约定：只动目标行/块，文件里其余内容和注释一律原样保留，
这样 params.yaml 既是机器落盘的结果，也仍然是人手工调参的地方。
"""
from __future__ import annotations

import json
import pathlib
import re


def update_params_offset(path: pathlib.Path, rid: str, deg: float) -> bool:
    """只改 robots.<rid> 那一行里的 theta_offset_deg 数字，保留全部注释。"""
    text = path.read_text(encoding="utf-8")
    has_key = re.compile(
        rf"^(\s+{re.escape(rid)}:\s*\{{[^}}\n]*?theta_offset_deg:\s*)[-\d.]+",
        re.M)
    if has_key.search(text):
        new = has_key.sub(rf"\g<1>{deg:.1f}", text, count=1)
    else:
        no_key = re.compile(rf"^(\s+{re.escape(rid)}:\s*\{{[^}}\n]*?)\}}", re.M)
        if not no_key.search(text):
            return False
        new = no_key.sub(rf"\g<1>, theta_offset_deg: {deg:.1f}}}", text,
                         count=1)
    path.write_text(new, encoding="utf-8")
    return True


def robot_line(rid: str, ip: str, marker_id: int,
               theta_offset_deg: float = 0) -> str:
    return (f'  {rid}: {{ ip: "{ip}", marker_id: {int(marker_id)}, '
            f"theta_offset_deg: {theta_offset_deg:g} }}")


def upsert_robot(path: pathlib.Path, rid: str, ip: str,
                 marker_id: int) -> bool:
    """登记/更新一辆车：已有同名行就整行替换（偏移归零，需重测方向），
    有同名注释占位（# r2: …）就启用该行，否则插到 robots 块内最后一辆车之后。
    """
    text = path.read_text(encoding="utf-8")
    line = robot_line(rid, ip, marker_id)
    active = re.compile(rf"^\s+{re.escape(rid)}:\s*\{{[^\n]*\}}\s*$", re.M)
    holder = re.compile(rf"^\s*#\s*{re.escape(rid)}:[^\n]*$", re.M)
    if active.search(text):
        new = active.sub(lambda _: line, text, count=1)
    elif holder.search(text):
        new = holder.sub(lambda _: line, text, count=1)
    else:
        lines = text.splitlines(keepends=True)
        head = next((i for i, ln in enumerate(lines)
                     if re.match(r"^robots:\s*(#.*)?$", ln)), None)
        if head is None:
            return False
        insert_at = head + 1
        for i in range(head + 1, len(lines)):
            ln = lines[i]
            if ln.strip() and not ln[0].isspace():  # 块结束
                break
            if re.match(r"^\s+\w[\w-]*:\s*\{", ln):  # 块内已定义的车
                insert_at = i + 1
        lines.insert(insert_at, line + "\n")
        new = "".join(lines)
    path.write_text(new, encoding="utf-8")
    return True


def _replace_circle_block(path: pathlib.Path, key: str,
                          records: list[dict], empty_comment: str) -> bool:
    if records:
        def line(o):
            properties = ""
            if "properties" in o:
                encoded = json.dumps(
                    o["properties"], ensure_ascii=False,
                    separators=(",", ":"))
                properties = f", properties: {encoded}"
            return (
                f"  - {{ id: {o['id']}, shape: {o['shape']}, "
                f"x_cm: {float(o['x_cm']):.2f}, "
                f"y_cm: {float(o['y_cm']):.2f}, "
                f"radius_cm: {float(o['radius_cm']):.2f}"
                f"{properties} }}")

        items = "\n".join(line(o) for o in records)
        block = f"{key}:   # setup_field 圈选写入\n{items}\n"
    else:
        block = f"{key}: []   # {empty_comment}\n"
    text = path.read_text(encoding="utf-8")
    pat = re.compile(
        rf"^{re.escape(key)}:[^\n]*\n(?:(?:[ \t][^\n]*)?\n)*", re.M)
    if pat.search(text):
        new = pat.sub(lambda _: block + "\n", text, count=1)
    else:
        new = text.rstrip("\n") + "\n\n" + block
    path.write_text(new, encoding="utf-8")
    return True


def replace_landmarks(path: pathlib.Path, landmarks: list[dict]) -> bool:
    """整块替换开场手动画入、可被车辆前往的固定目标。"""
    return _replace_circle_block(
        path, "landmarks", landmarks, "setup_field 写入：场上无固定目标")


def replace_obstacles(path: pathlib.Path, obstacles: list[dict]) -> bool:
    """兼容旧配置的 obstacles 写回接口。"""
    return _replace_circle_block(
        path, "obstacles", obstacles, "setup_field 写入：场上无障碍")
