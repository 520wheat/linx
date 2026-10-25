class GameEngine {
  constructor(caseData) {
    this.caseData = caseData;
    this.selected = [];
    this.running = false;
    this.mood = "calm";
    this.secondsLeft = caseData.seconds;
    this.ended = null;
    this.cracked = false;
  }

  snapshot() {
    return {
      running: this.running,
      mood: this.mood,
      secondsLeft: this.secondsLeft,
      selected: this.selected.slice(),
      ended: this.ended,
      hint: this.isKey()
    };
  }

  isKey() {
    return this.caseData.key.every((id) => this.selected.includes(id));
  }

  titles() {
    return this.selected.map((id) => this.caseData.clues.find((clue) => clue.id === id).title);
  }

  start() {
    this.selected = [];
    this.running = true;
    this.mood = "calm";
    this.secondsLeft = this.caseData.seconds;
    this.ended = null;
    this.cracked = false;
    return this.snapshot();
  }

  toggleClue(id) {
    const index = this.selected.indexOf(id);
    if (index >= 0) this.selected.splice(index, 1);
    else if (this.selected.length < 2) this.selected.push(id);
    return { selected: this.selected.slice() };
  }

  present(heardText) {
    const heard = (heardText || "").trim();
    const playerLine = heard
      ? heard
      : this.selected.length
        ? "出示「" + this.titles().join(" + ") + "」。"
        : "没有出示证据。";

    let suspectLine = this.caseData.lines.wrong;
    if (this.selected.length === 0) suspectLine = this.caseData.lines.empty;

    if (this.isKey() && this.cracked) {
      this.mood = "break";
      this.ended = "win";
      this.running = false;
      suspectLine = this.caseData.lines.confess;
    } else if (this.isKey()) {
      this.cracked = true;
      this.mood = "panic";
      this.ended = null;
      suspectLine = this.caseData.lines.crack;
    } else {
      this.mood = "calm";
      this.ended = null;
    }

    return {
      playerLine,
      suspectLine,
      mood: this.mood,
      hint: this.isKey(),
      selected: this.selected.slice(),
      ended: this.ended
    };
  }

  tick() {
    if (this.ended || !this.running) {
      return { secondsLeft: this.secondsLeft, ended: this.ended };
    }
    this.secondsLeft -= 1;
    if (this.secondsLeft <= 0) {
      this.secondsLeft = 0;
      this.ended = "lose";
      this.running = false;
    }
    return { secondsLeft: this.secondsLeft, ended: this.ended };
  }
}

if (typeof window !== "undefined") window.GameEngine = GameEngine;
if (typeof module !== "undefined" && module.exports) module.exports = { GameEngine };