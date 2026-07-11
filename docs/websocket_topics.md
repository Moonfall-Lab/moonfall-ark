# WebSocket Topics

所有消息都走：

```json
{
  "topic": "topic.name",
  "source": "sender_name",
  "timestamp": 1720000000.0,
  "payload": {}
}
```

## state.world

Runtime 广播完整世界状态。客户端连接 `/ws` 后会先收到一次，之后 GameLoop 每秒广播。

示例输出：

```json
{
  "topic": "state.world",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "game_id": "moonfall",
    "session_id": "uuid",
    "phase": "prepare",
    "fuel": 0.0,
    "core_hp": 100,
    "moon_rage": 0.0,
    "boss_mode": false,
    "winner": null,
    "robots": {},
    "players": {},
    "current_events": []
  }
}
```

## state.event

Runtime 广播游戏事件。机械臂也可以用它回传 `arm_done`，Runtime 会记录后再广播。

机械臂回传示例：

```json
{
  "topic": "state.event",
  "source": "arm",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "arm_done",
    "message": "机械臂动作完成",
    "command_id": "cmd-id",
    "action": "drop_dust"
  }
}
```

Runtime 事件输出示例：

```json
{
  "topic": "state.event",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "enter_boss",
    "message": "燃料达到 70%，进入 Boss 战"
  }
}
```

## input.voice

语音文本输入。

输入：

```json
{
  "topic": "input.voice",
  "source": "voice_test",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "text": "让一号车绕开月尘去东北资源区采集燃料"
  }
}
```

输出：

- `cmd.robot`
- `state.event`

## input.card

卡牌输入。MVP 只记录并广播事件。

输入：

```json
{
  "topic": "input.card",
  "source": "frontend",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "card_id": "boost_fuel",
    "action": "use"
  }
}
```

输出：

```json
{
  "topic": "state.event",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "card_input",
    "message": "收到卡牌输入"
  }
}
```

## input.debug

调试输入。MVP 记录并广播 `state.event`。

输入：

```json
{
  "topic": "input.debug",
  "source": "frontend",
  "timestamp": 1720000000.0,
  "payload": {
    "message": "debug from frontend"
  }
}
```

## sensor.hr

心率上传。

输入：

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "heart_rate": 105
  }
}
```

处理：

- 更新玩家心率。
- 计算 stress。
- 重算所有玩家平均 `moon_rage`。
- 广播 `state.world`。

## perception.pose

小车、人形或物体位置上传。当前 MVP 主要用于小车。

输入：

```json
{
  "topic": "perception.pose",
  "source": "robot_r1",
  "timestamp": 1720000000.0,
  "payload": {
    "robot_id": "r1",
    "x": 3.2,
    "y": 5.1,
    "theta": 90,
    "status": "moving"
  }
}
```

输出：

- `state.world`

## cmd.robot

Runtime 下发给小车。

输出：

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "uuid",
    "robot_id": "r1",
    "action": "collect",
    "target_zone": "resource_ne",
    "x": null,
    "y": null,
    "speed": 0.5,
    "priority": 1.2,
    "avoid": ["dust_center"]
  }
}
```

小车客户端只处理 `payload.robot_id` 等于自己的命令。

## cmd.arm

Runtime 下发给机械臂。

输出：

```json
{
  "topic": "cmd.arm",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "uuid",
    "action": "drop_dust",
    "target_zone": "dust_center",
    "x": null,
    "y": null,
    "intensity": 1.0,
    "safe_mode": true
  }
}
```

机械臂执行后建议回传：

```json
{
  "topic": "state.event",
  "source": "arm",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "arm_done",
    "message": "机械臂动作完成",
    "command_id": "uuid"
  }
}
```

## cmd.humanoid

Runtime 下发给人形机器人。MVP 预留 topic，当前没有主动生成。

输出示例：

```json
{
  "topic": "cmd.humanoid",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "uuid",
    "action": "speak",
    "text": "请返回基地",
    "target": "p1"
  }
}
```

## debug.echo

连接测试。Runtime 原样回传。

输入：

```json
{
  "topic": "debug.echo",
  "source": "frontend",
  "timestamp": 1720000000.0,
  "payload": {
    "ping": "pong"
  }
}
```

输出与输入相同。

## debug.log

调试日志。Runtime 记录并广播 `state.event`。

输入：

```json
{
  "topic": "debug.log",
  "source": "robot_r1",
  "timestamp": 1720000000.0,
  "payload": {
    "message": "wheel ready"
  }
}
```

## error

Runtime 错误消息。

```json
{
  "topic": "error",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "code": "UNKNOWN_TOPIC",
    "message": "未知或不允许客户端发送的 topic: xxx",
    "raw": {}
  }
}
```

## input.qr_skill

Insta360 Link 2C 二维码客户端在识别到已登记卡牌时发送。Runtime 会再次核对卡牌名称和技能 ID，只广播识别事件，不执行技能，也不修改游戏状态。

输入：

```json
{
  "topic": "input.qr_skill",
  "source": "insta360_link_2c",
  "timestamp": 1720000000.0,
  "payload": {
    "qr_text": "瞬移偷窃",
    "skill_id": "teleport_steal",
    "skill_name": "瞬移偷窃"
  }
}
```

有效输入广播：

```json
{
  "topic": "state.event",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "qr_skill_detected",
    "message": "识别到技能卡：瞬移偷窃",
    "data": {
      "qr_text": "瞬移偷窃",
      "skill_id": "teleport_steal",
      "skill_name": "瞬移偷窃"
    }
  }
}
```

未知二维码、缺少字段或名称与技能 ID 不一致时返回 `INVALID_PAYLOAD`。
