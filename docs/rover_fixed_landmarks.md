# Rover 固定目标数据

本文档记录当前 `80cm × 60cm` 场地中五个固定目标的几何坐标与业务类型。
坐标原点、方向及单位与 Rover Agent 一致，所有距离均使用厘米。

## 固定目标

```json
[
  {
    "id": "obstacle-1",
    "shape": "circle",
    "x_cm": 19.22,
    "y_cm": 52.58,
    "radius_cm": 5.82,
    "properties": {
      "type": "energy_station"
    }
  },
  {
    "id": "obstacle-2",
    "shape": "circle",
    "x_cm": 61.51,
    "y_cm": 51.09,
    "radius_cm": 5.44,
    "properties": {
      "type": "ruins"
    }
  },
  {
    "id": "obstacle-3",
    "shape": "circle",
    "x_cm": 37.37,
    "y_cm": 29.88,
    "radius_cm": 5.77,
    "properties": {
      "type": "high_energy_station"
    }
  },
  {
    "id": "obstacle-4",
    "shape": "circle",
    "x_cm": 12.71,
    "y_cm": 10.16,
    "radius_cm": 5.94,
    "properties": {
      "type": "ruins"
    }
  },
  {
    "id": "obstacle-5",
    "shape": "circle",
    "x_cm": 61.83,
    "y_cm": 13.90,
    "radius_cm": 5.41,
    "properties": {
      "type": "energy_station"
    }
  }
]
```

## 字段定义

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `id` | string | 是 | 固定目标的唯一标识；当前为 `obstacle-1..5` |
| `shape` | string | 是 | 几何形状；当前固定为 `circle` |
| `x_cm` | number | 是 | 圆心的 X 坐标，单位厘米 |
| `y_cm` | number | 是 | 圆心的 Y 坐标，单位厘米 |
| `radius_cm` | number | 是 | 固定目标实体的半径，单位厘米 |
| `properties` | object | 是 | 上层业务属性；不参与路径规划的几何计算 |
| `properties.type` | string | 是 | 固定目标的业务类型 |

## 业务类型

| `properties.type` | 中文含义 | 对应目标 |
| --- | --- | --- |
| `energy_station` | 普通能源站 | `obstacle-1`、`obstacle-5` |
| `high_energy_station` | 高能能源站 | `obstacle-3` |
| `ruins` | 遗迹 | `obstacle-2`、`obstacle-4` |

## 使用约定

- 路径规划只读取 `shape`、`x_cm`、`y_cm` 和 `radius_cm`。
- 上层规则通过 `properties.type` 判断固定目标的业务含义。
- 后续增加阵营、分值、资源量等信息时，继续写入 `properties`，不要改变几何字段的含义。
- Rover Agent 的 `get_landmarks` 接口应原样返回几何字段和 `properties`。
