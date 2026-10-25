window.CASE = {
  name: "午夜便利店",
  suspect: "陈默",
  seconds: 8 * 60,
  key: ["receipt", "cam"],
  clues: [
    { id: "receipt", title: "便利店小票", body: "21:03 结账，只买了一包烟。", tag: "物证" },
    { id: "cam", title: "小区监控", body: "21:02 单元门口拍到陈默。", tag: "影像" },
    { id: "call", title: "通话记录", body: "20:58 打给同事，时长 41 秒。", tag: "记录" },
    { id: "alibi", title: "本人陈述", body: "自称九点整一直待在店里。", tag: "口供" }
  ],
  opening: "九点我在便利店买烟，小票还在。你们要是有监控，拿出来对时间啊。",
  lines: {
    empty: "你到底想问什么？我一直在店里。",
    wrong: "这能说明什么？九点我就是在店里。",
    near: "时间对得上啊，小票不就在那儿吗。",
    crack: "那、那监控可能是延迟……小票是同事帮我拿的。",
    confess: "行了。我九点前还在小区，进店的时候人已经倒了。我怕被看见，才编了这套。"
  }
};