(function () {
  const data = window.CASE;
  const engine = new window.GameEngine(data);
  let running = false;
  let timerId = null;
  let hearing = null;
  const log = document.getElementById("log");
  const hint = document.getElementById("hint");
  const mood = document.getElementById("mood");
  const timer = document.getElementById("timer");
  const bar = document.getElementById("bar");
  const mic = document.getElementById("mic");
  const moodText = {
    calm: "情绪：镇定圆谎",
    panic: "情绪：慌了，开始漏嘴",
    break: "情绪：崩了"
  };

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

  function paint(state) {
    mood.textContent = moodText[state.mood] || moodText.calm;
    hint.textContent = data.hint;
    hint.classList.toggle("on", Boolean(state.hint));
    const minutes = String(Math.floor(state.secondsLeft / 60)).padStart(2, "0");
    const seconds = String(state.secondsLeft % 60).padStart(2, "0");
    timer.textContent = minutes + ":" + seconds;
    bar.style.transform = "scaleX(" + (state.secondsLeft / data.seconds) + ")";
    ["s0", "s1"].forEach((id, index) => {
      const el = document.getElementById(id);
      const clueId = state.selected[index];
      const clue = data.clues.find((item) => item.id === clueId);
      el.className = clue ? "hold in" : "hold";
      el.textContent = clue ? clue.title : "证据位 " + (index + 1);
    });
    document.querySelectorAll("#cards .card").forEach((button) => {
      button.classList.toggle("on", state.selected.includes(button.dataset.id));
    });
  }

  function finish(ended) {
    running = false;
    clearInterval(timerId);
    window.Voice.stop();
    document.getElementById("endKicker").textContent = ended === "win" ? "真相只有一个" : "时间到";
    document.getElementById("endTitle").textContent = ended === "win" ? "不在场证明已破" : "他还在圆谎";
    document.getElementById("endBody").textContent = ended === "win"
      ? "21:02 陈默还在小区门口，不可能 21:03 自己在店里结账。口供垮了。"
      : "八分钟用完了。把小票和监控叠在一起再问一次。";
    document.getElementById("end").classList.remove("hidden");
  }

  function renderCards() {
    const box = document.getElementById("cards");
    box.innerHTML = "";
    data.clues.forEach((clue) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "card";
      button.dataset.id = clue.id;
      button.innerHTML = "<div class='tag'></div><h3></h3><p></p>";
      button.querySelector(".tag").textContent = clue.tag;
      button.querySelector("h3").textContent = clue.title;
      button.querySelector("p").textContent = clue.body;
      button.onclick = function () {
        if (!running) return;
        paint({ ...engine.snapshot(), selected: engine.toggleClue(clue.id).selected });
      };
      box.appendChild(button);
    });
  }

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
    const result = engine.present(heard);
    say("你", result.playerLine, true);
    say(data.suspect, result.suspectLine, false);
    window.Voice.speak(result.suspectLine);
    paint(result);
    if (result.ended) setTimeout(() => finish(result.ended), 900);
  }

  function start() {
    const state = engine.start();
    running = true;
    log.innerHTML = "";
    document.getElementById("boot").classList.add("hidden");
    document.getElementById("end").classList.add("hidden");
    renderCards();
    paint(state);
    say(data.suspect, data.opening, false);
    window.Voice.speak(data.opening);
    clearInterval(timerId);
    timerId = setInterval(() => {
      const next = engine.tick();
      paint({ ...engine.snapshot(), secondsLeft: next.secondsLeft, ended: next.ended });
      if (next.ended) finish(next.ended);
    }, 1000);
  }

  document.getElementById("start").onclick = start;
  document.getElementById("again").onclick = start;
  mic.addEventListener("pointerdown", beginAsk);
  mic.addEventListener("pointerup", endAsk);
  mic.addEventListener("pointerleave", endAsk);
  hint.textContent = data.hint;
  renderCards();
  paint(engine.snapshot());
})();