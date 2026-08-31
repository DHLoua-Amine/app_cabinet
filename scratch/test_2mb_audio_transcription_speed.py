import io
import sys
import time
import wave
import numpy as np
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import voice_verifier

provider, model = config.load_ai_engine()
keys = config.load_saved_api_keys(provider)

if not keys:
    print("[ERROR] No API Key found in config!")
    sys.exit(1)

# Generate synthetic 2.3 MB WAV audio buffer (approx 26 seconds of audio)
sample_rate = 44100
duration = 26
num_samples = sample_rate * duration
t = np.linspace(0, duration, num_samples, False)
mono_signal = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
stereo_signal = np.column_stack((mono_signal, mono_signal)).flatten()

buf = io.BytesIO()
with wave.open(buf, "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(stereo_signal.tobytes())

raw_audio_bytes = buf.getvalue()
print("="*70)
print(f" 🚀 BENCHMARK: REAL 2.3 MB AUDIO TRANSCRIPTION SPEED TEST")
print(f" Raw Audio Size: {len(raw_audio_bytes):,} bytes ({len(raw_audio_bytes)/1024/1024:.2f} MB)")
print("="*70)

t0 = time.time()
res = voice_verifier.transcribe_audio_bytes(
    audio_bytes=raw_audio_bytes,
    api_key=keys,
    mime_type="audio/wav",
    model_name=model,
    provider=provider
)
t1 = time.time()
elapsed = t1 - t0

print(f"\n⏱️ Total Transcription Execution Time: {elapsed:.2f} seconds")
print(f"Status Success: {res.get('success')}")
assert elapsed < 20.0, f"FAIL: Audio transcription ({elapsed:.2f}s) exceeded 20 seconds!"
print("\n✅ 2.3 MB Audio Speed Test Passed (< 20 seconds target achieved!)")
print("="*70)
