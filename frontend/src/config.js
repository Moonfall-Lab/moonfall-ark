// 运行时可配置：?host=192.168.1.23:8000 指向后端；?mock=1 强制离线演示数据
const params = new URLSearchParams(location.search)

export const HOST = params.get('host') || '127.0.0.1:8000'
export const FORCE_MOCK = params.has('mock')
export const HTTP_BASE = `http://${HOST}`
export const WS_URL = `ws://${HOST}/ws`
