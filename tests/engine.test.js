const test = require("node:test");
const assert = require("node:assert/strict");
const CASE = require("../js/case.js");
const { GameEngine } = require("../js/engine.js");

function engineWithKeySelected() {
  const engine = new GameEngine(CASE);
  engine.start();
  engine.toggleClue("receipt");
  engine.toggleClue("cam");
  return engine;
}

test("toggle_clue_caps_at_two", () => {
  const engine = new GameEngine(CASE);
  engine.start();
  engine.toggleClue("receipt");
  engine.toggleClue("cam");
  const result = engine.toggleClue("call");
  assert.deepEqual(result.selected, ["receipt", "cam"]);
});

test("present_key_first_panics", () => {
  const engine = engineWithKeySelected();
  const result = engine.present("对时间");
  assert.equal(result.mood, "panic");
  assert.equal(result.ended, null);
  assert.equal(result.suspectLine, CASE.lines.crack);
  assert.equal(result.playerLine, "对时间");
  assert.equal(result.hint, true);
});

test("present_key_second_wins", () => {
  const engine = engineWithKeySelected();
  engine.present("对时间");
  const result = engine.present("");
  assert.equal(result.ended, "win");
  assert.equal(result.mood, "break");
  assert.equal(result.suspectLine, CASE.lines.confess);
});

test("present_wrong_does_not_win", () => {
  const engine = new GameEngine(CASE);
  engine.start();
  engine.toggleClue("call");
  const result = engine.present("呢");
  assert.equal(result.mood, "calm");
  assert.equal(result.ended, null);
  assert.equal(result.suspectLine, CASE.lines.wrong);
});

test("timeout_loses_even_if_cracked", () => {
  const engine = engineWithKeySelected();
  engine.present("对时间");
  let last = null;
  for (let i = 0; i < CASE.seconds; i += 1) {
    last = engine.tick();
  }
  assert.equal(last.ended, "lose");
  assert.equal(last.secondsLeft, 0);
});