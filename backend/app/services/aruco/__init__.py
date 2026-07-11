"""ArUco 标记检测与定位模块。"""
from .calibration import Calibrator, aruco_detect, dict_id_by_name
from .geometry import Pose, norm_angle
