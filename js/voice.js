window.Voice = {
  _rec: null,
  _text: "",
  start() {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    this._text = "";
    if (!Speech) return Promise.resolve("");
    return new Promise((resolve) => {
      const rec = new Speech();
      rec.lang = "zh-CN";
      rec.interimResults = false;
      rec.continuous = true;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        resolve(this._text || "");
      };
      rec.onresult = (event) => {
        const last = event.results[event.results.length - 1];
        if (last && last[0]) this._text = last[0].transcript;
      };
      rec.onerror = finish;
      rec.onend = finish;
      this._rec = rec;
      this._finish = finish;
      try { rec.start(); } catch (err) { finish(); }
    });
  },
  stop() {
    if (this._rec) {
      try { this._rec.stop(); } catch (err) { /* already stopped */ }
    } else if (this._finish) {
      this._finish();
    }
  },
  speak(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "zh-CN";
    utter.rate = 1;
    utter.pitch = 0.85;
    window.speechSynthesis.speak(utter);
  }
};