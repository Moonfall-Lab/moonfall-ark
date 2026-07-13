// 运行时可配置：?host=192.168.1.23:8000 指向后端；?mock=1 强制离线演示数据
const params = new URLSearchParams(location.search)

// 全局 mock 开关：true = 强制使用离线演示数据，不连后端
export const NEED_MOCK = false

export const HOST = params.get('host') || '127.0.0.1:8000'
export const FORCE_MOCK = NEED_MOCK || params.has('mock')
export const HTTP_BASE = `http://${HOST}`
export const WS_URL = `ws://${HOST}/ws`
