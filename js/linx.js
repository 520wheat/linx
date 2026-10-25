// 灵矽实时语音占位。拿到控制台 Token 后，把 listen/speak 切到
// wss://xrobo-io.qiniuapi.com/v1/ws/ ，请求头带 Authorization、Device-Id、Client-Id。
window.LINX = {
  token: "",
  deviceId: "",
  enabled: false
};