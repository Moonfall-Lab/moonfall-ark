# MoonFall 实时计分大屏

React + Vite + Tailwind + Framer Motion。订阅后端 Runtime 的实时状态，渲染四人竞速大屏。不连后端也能用内置 mock 数据预览。

## 运行

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

## 连接后端

默认连 `ws://127.0.0.1:8000/ws`。可用 URL 参数覆盖：

- `?host=192.168.1.23:8000` 指定后端地址（联机演示时用后端电脑 IP）。
- `?mock=1` 强制使用离线演示数据，不连后端。

连不上后端时会自动降级到 mock，界面照常运转。左上角状态灯：`● LIVE` 连真后端 / `○ MOCK 演示`。

## 数据来源

- 静态定义（地图网格、区域中心与 kind、阵营名、卡牌）来自 `GET /api/config`，启动时拉一次。
- 实时状态来自 WebSocket `state.world`（每秒一次），事件来自 `state.event`。
- 消息封套统一为 `{ topic, source, timestamp, payload }`，与 `docs/frontend/API_INTEGRATION.md` 一致。
- 所有 id（阵营、区域、卡牌、事件）从数据读取，换配置不改前端代码。

## 目录

```
src/
  App.jsx                 布局，组合各面板
  config.js               运行时地址与 mock 开关
  lib/
    useGameData.js        WebSocket + config 拉取 + mock 兜底
    mock.js               离线演示数据源（结构与后端一致）
    factions.js           阵营配色
  components/
    MapGrid.jsx           12×12 地图，SVG 渲染区域与小车
    PlayerPanel.jsx       玩家飞船面板：燃料/血量/心率/状态徽章
    MoonRageMeter.jsx     月球狂暴度仪表，四档 25/50/80
    HeartRateWave.jsx     Canvas 心率波形
    EventLog.jsx          事件流跑马灯
    RankBoard.jsx         升空排名结算
    DangerOverlay.jsx     终局预警层
    DebugPanel.jsx        导播调试台（Ctrl+D），按钮走 REST 调试接口
    LoadingScreen.jsx     连接/加载态
```

## 交互

- `Ctrl + D` 打开/关闭调试台。
- 调试台按钮（强制狂暴、触发陨石/月尘、设燃料、重置）仅在连真后端时生效。

## 说明

界面渲染的内容随后端加载的游戏配置变化。当前后端配置声明了完整 MVP 地图与卡牌，但对抗/月球分步结算、卡牌效果等运行时逻辑仍在后端补齐中，因此实时对局的部分行为可能尚不完整。
