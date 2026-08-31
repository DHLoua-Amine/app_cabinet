import io
import time
import wave
import numpy as np

# Generate a 2.3 MB synthetic stereo 44.1kHz WAV buffer (approx 26 seconds of audio)
sample_rate = 44100
duration = 26  # seconds
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

raw_wav = buf.getvalue()
print(f"Original Raw WAV Size: {len(raw_wav)} bytes ({len(raw_wav)/1024/1024:.2f} MB)")

# Downsample function
t0 = time.time()

with wave.open(io.BytesIO(raw_wav), "rb") as wf:
    n_channels = wf.getnchannels()
    sampwidth = wf.getsampwidth()
    framerate = wf.getframerate()
    n_frames = wf.getnframes()
    pcm_data = wf.readframes(n_frames)

samples = np.frombuffer(pcm_data, dtype=np.int16)
if n_channels == 2:
    samples = ((samples[0::2].astype(np.int32) + samples[1::2].astype(np.int32)) // 2).astype(np.int16)

if framerate > 16000:
    step = framerate / 16000.0
    indices = (np.arange(0, len(samples) / step) * step).astype(np.int64)
    indices = indices[indices < len(samples)]
    samples = samples[indices]
    framerate = 16000

out_io = io.BytesIO()
with wave.open(out_io, "wb") as out_wf:
    out_wf.setnchannels(1)
    out_wf.setsampwidth(2)
    out_wf.setframerate(framerate)
    out_wf.writeframes(samples.tobytes())

downsampled_wav = out_io.getvalue()
t1 = time.time()

print(f"Downsampled 16kHz Mono WAV Size: {len(downsampled_wav)} bytes ({len(downsampled_wav)/1024/1024:.2f} MB)")
print(f"Payload Reduction: {((len(raw_wav) - len(downsampled_wav)) / len(raw_wav)) * 100:.1f}% smaller!")
print(f"Downsampling Execution Time: {(t1 - t0)*1000:.2f} ms")

assert len(downsampled_wav) < len(raw_wav) / 4, "FAIL: Downsampling did not reduce payload size sufficiently!"
print("✅ WAV Downsampling Test Passed!")
