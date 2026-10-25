(function () {
  const data = window.CASE;
  const selected = [];
  let left = data.seconds;
  let running = false;
  let cracked = false;
  let timerId = null;
  const log = document.getElementById("log");
  const hint = document.getElementById("hint");
  const mood = document.getElementById("mood");
  const timer = document.getElementById("timer");
  const bar = document.getElementById("bar");
  const mic = document.getElementById("mic");

  function titles() {
    return selected.map((id) => data.clues.find((c) => c.id === id).title);
  }

  function isKey() {
    return data.key.every((id) => selected.includes(id));
  }

  function say(who, text, mine) {
    const node = document.createElement("div");
    node.className = "msg" + (mine ? " me" : "");
    const whoEl = document.createElement("div");
    whoEl.className = "who";
    whoEl.textContent = who;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    node.append(whoEl, bubble);
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
  }

  function renderSlots() {
    ["s0", "s1"].forEach((id, index) => {
      const el = document.getElementById(id);
      el.className = selected[index] ? "hold in" : "hold";
      el.textContent = selected[index] ? titles()[index] : "证据位 " + (index + 1);
    });
    hint.classList.toggle("on", isKey());
  }

  function renderCards() {
    const box = document.getElementById("cards");
    box.innerHTML = "";
    data.clues.forEach((clue) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "card" + (selected.includes(clue.id) ? " on" : "");
      button.innerHTML = "<div class='tag'></div><h3></h3><p></p>";
      button.querySelector(".tag").textContent = clue.tag;
      button.querySelector("h3").textContent = clue.title;
      button.querySelector("p").textContent = clue.body;
      button.onclick = function () {
        if (!running) return;
        const index = selected.indexOf(clue.id);
        if (index >= 0) selected.splice(index, 1);
        else if (selected.length < 2) selected.push(clue.id);
        renderCards();
        renderSlots();
      };
      box.appendChild(button);
    });
  }

  function paintTime() {
    const minutes = String(Math.floor(left / 60)).padStart(2, "0");
    const seconds = String(left % 60).padStart(2, "0");
    timer.textContent = minutes + ":" + seconds;
    bar.style.transform = "scaleX(" + (left / data.seconds) + ")";
  }

  function finish(won) {
    running = false;
    clearInterval(timerId);
    window.Voice.stop();
    document.getElementById("endKicker").textContent = won ? "真相只有一个" : "时间到";
    document.getElementById("endTitle").textContent = won ? "不在场证明已破" : "他还在圆谎";
    document.getElementById("endBody").textContent = won
      ? "21:02 陈默还在小区门口，不可能 21:03 自己在店里结账。口供垮了。"
      : "八分钟用完了。把小票和监控叠在一起再问一次。";
    document.getElementById("end").classList.remove("hidden");
  }

  function reply(heard) {
    const text = (heard || "").trim();
    if (text) say("你", text, true);
    else say("你", selected.length ? "出示「" + titles().join(" + ") + "」。" : "没有出示证据。", true);

    if (isKey() && cracked) {
      say(data.suspect, data.lines.confess, false);
      window.Voice.speak(data.lines.confess);
      mood.textContent = "情绪：崩了";
      setTimeout(() => finish(true), 900);
      return;
    }
    if (isKey()) {
      cracked = true;
      say(data.suspect, data.lines.crack, false);
      window.Voice.speak(data.lines.crack);
      mood.textContent = "情绪：慌了，开始漏嘴";
      return;
    }
    const line = selected.length === 0 ? data.lines.empty : data.lines.wrong;
    say(data.suspect, line, false);
    window.Voice.speak(line);
    mood.textContent = "情绪：镇定圆谎";
  }

  let hearing = null;

  function beginAsk(event) {
    if (!running || hearing) return;
    event.preventDefault();
    mic.classList.add("hot");
    mic.textContent = "正在听";
    hearing = window.Voice.start();
  }

  async function endAsk() {
    if (!hearing) return;
    window.Voice.stop();
    const heard = await hearing;
    hearing = null;
    mic.classList.remove("hot");
    mic.textContent = "按住问话";
    reply(heard);
  }

  function start() {
    selected.length = 0;
    left = data.seconds;
    cracked = false;
    running = true;
    log.innerHTML = "";
    mood.textContent = "情绪：镇定圆谎";
    document.getElementById("boot").classList.add("hidden");
    document.getElementById("end").classList.add("hidden");
    renderCards();
    renderSlots();
    paintTime();
    say(data.suspect, data.opening, false);
    window.Voice.speak(data.opening);
    clearInterval(timerId);
    timerId = setInterval(() => {
      left -= 1;
      paintTime();
      if (left <= 0) finish(false);
    }, 1000);
  }

  document.getElementById("start").onclick = start;
  document.getElementById("again").onclick = start;
  mic.addEventListener("pointerdown", beginAsk);
  mic.addEventListener("pointerup", endAsk);
  mic.addEventListener("pointerleave", endAsk);
  renderCards();
  renderSlots();
  paintTime();
})();