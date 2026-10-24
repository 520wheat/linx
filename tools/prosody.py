"""语气实测：分析一组 WAV 的时长、能量和音高，检验不同情绪 emoji 是否真的改变了 TTS 语气（#29）。

换音色后用法：
1. 临时把测试智能体换成平台模型，角色介绍改为「用户说测试一到测试N时，只回复：<指定 emoji>+同一句固定台词」；
2. 用设备模拟器录音：uv run --group devsim python tools/devsim.py say 测试一 测试二 … --audio out/
3. 分析：uv run --group devsim python tools/prosody.py out/*.wav
音高中位数、能量和基线（😌）明显不同的情绪，才适合用在案件的档位上。
"""

import sys
import wave
from pathlib import Path

import numpy as np


def analyze(path: Path) -> dict:
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    frame = int(sr * 0.04)
    hop = frame // 2
    frames = [x[i : i + frame] for i in range(0, len(x) - frame, hop)]
    rms = np.array([np.sqrt(np.mean(f * f)) for f in frames])
    voiced = rms > max(0.02, rms.max() * 0.1)
    lo, hi = int(sr / 400), int(sr / 70)  # 人声基频大致在 70–400Hz
    f0 = []
    for f, v in zip(frames, voiced, strict=True):
        if not v:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[len(f) - 1 :]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            f0.append(sr / k)
    f0 = np.array(f0) if f0 else np.array([0.0])
    return {
        "seconds": len(x) / sr,
        "voiced": voiced.sum() * hop / sr,
        "energy": float(rms[voiced].mean()) if voiced.any() else 0.0,
        "pitch": float(np.median(f0)),
        "pitch_sd": float(np.std(f0)),
    }


def main(paths: list[str]) -> None:
    for p in paths:
        r = analyze(Path(p))
        print(
            f"{Path(p).name:12s} 总长 {r['seconds']:4.2f}s 发声 {r['voiced']:4.2f}s  "
            f"能量 {r['energy']:.3f}  音高中位 {r['pitch']:5.0f}Hz  音高波动 {r['pitch_sd']:4.0f}Hz"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
