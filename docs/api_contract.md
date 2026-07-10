# Moonfall Runtime API Contract

Runtime 提供 HTTP API 和 WebSocket API。HTTP 用于调试、查看状态和简单输入；WebSocket 用于比赛时的实时连接。

## 基础地址

后端本机：

```text
http://127.0.0.1:8000
ws://127.0.0.1:8000/ws
```

队友电脑连接时，把 `127.0.0.1` 换成后端电脑 IPv4，例如：

```text
http://192.168.1.23:8000
ws://192.168.1.23:8000/ws
```

## WebSocket 统一消息格式

所有 WebSocket 消息都必须是：

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "timestamp": 1720000000.0,
  "payload": {}
}
```

字段：

- `topic`：消息类型。
- `source`：消息来源，例如 `runtime`、`frontend`、`robot_r1`、`arm`、`hr_p1`、`voice_test`。
- `timestamp`：Unix 时间戳，float。
- `payload`：业务数据对象。

格式错误时 Runtime 返回：

```json
{
  "topic": "error",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "code": "INVALID_MESSAGE",
    "message": "缺少 topic/source/timestamp/payload 字段",
    "raw": {}
  }
}
```

payload 缺字段时 Runtime 返回：

```json
{
  "topic": "error",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "code": "INVALID_PAYLOAD",
    "message": "payload 字段不完整或类型错误: ...",
    "raw": {}
  }
}
```

## HTTP API

### GET /api/health

检查服务是否启动。

响应：

```json
{
  "ok": true,
  "service": "moonfall-runtime"
}
```

### GET /api/state

返回当前完整 `WorldState`。

```bash
curl http://127.0.0.1:8000/api/state
```

### POST /api/input/hr

上传心率并重算 `moon_rage`。

请求：

```json
{
  "player_id": "p1",
  "heart_rate": 105
}
```

响应包含更新后的 `state`。

### POST /api/input/voice

提交语音文本，让 Runtime 解析成小车命令。

请求：

```json
{
  "player_id": "p1",
  "text": "让一号车绕开月尘去东北资源区采集燃料"
}
```

响应：

```json
{
  "ok": true,
  "intent": {
    "intent_type": "robot_command",
    "player_id": "p1",
    "robot_id": "r1",
    "action": "collect",
    "target_zone": "resource_ne",
    "avoid": ["dust_center"],
    "confidence": 0.6
  },
  "command": {
    "command_id": "...",
    "robot_id": "r1",
    "action": "collect",
    "target_zone": "resource_ne",
    "speed": 0.5,
    "priority": 1.2,
    "avoid": ["dust_center"]
  }
}
```

同时 Runtime 会通过 WebSocket 广播 `cmd.robot` 和 `state.event`。

### POST /api/input/card

MVP 只记录卡牌输入并广播 `state.event`。

请求：

```json
{
  "player_id": "p1",
  "card_id": "boost_fuel",
  "action": "use",
  "payload": {
    "value": 10
  }
}
```

### POST /api/debug/reset

重置内存 WorldState，生成新的 `session_id`。

### POST /api/debug/set_fuel

请求：

```json
{
  "fuel": 70
}
```

设置燃料并广播 `state.world`。

### POST /api/debug/set_moon_rage

请求：

```json
{
  "moon_rage": 0.8
}
```

设置月怒并广播 `state.world`。

### POST /api/debug/trigger_arm

请求：

```json
{
  "action": "drop_dust",
  "target_zone": "dust_center"
}
```

生成并广播 `cmd.arm`。

### POST /api/debug/trigger_boss

直接设置：

- `fuel = 70`
- `boss_mode = true`

并广播 `state.event` 和 `state.world`。

## WebSocket API

路径：

```text
/ws
```

连接后 Runtime 会立即发送一条 `state.world`，之后每秒广播一次完整世界状态。

Runtime 接受的主要输入 topic：

- `sensor.hr`
- `perception.pose`
- `input.voice`
- `input.card`
- `input.debug`
- `debug.echo`
- `debug.log`
- `state.event`：仅用于设备回传事件，例如机械臂 `arm_done`。

Runtime 主要输出 topic：

- `state.world`
- `state.event`
- `cmd.robot`
- `cmd.arm`
- `cmd.humanoid`
- `error`
