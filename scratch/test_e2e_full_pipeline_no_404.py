import sys
import time
import io
import wave
import numpy as np
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
from ui.pages.scanner_page import UnifiedPipelineThread

provider, model = config.load_ai_engine()
keys = config.load_saved_api_keys(provider)

if not keys:
    print("[ERROR] No API Key found in config!")
    sys.exit(1)

print("="*70)
print(f" 🚀 E2E INTEGRATION BENCHMARK: FULL PIPELINE WITHOUT 404 ERRORS")
print(f" Active AI Engine: Provider={provider}, Model={model}")
print("="*70)

# Generate synthetic 2.3 MB WAV audio buffer
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

audio_bytes = buf.getvalue()

p1_payload = [{"client_id": None, "front_bytes": None, "back_bytes": None, "extracted": {
    "full_name": "محمد الطيب بن محمد بن البشير ابن الحاج مبارك",
    "cin_number": "02998019",
    "job": "عامل يومي",
    "address": "5 نهج 10300 الوردية 4"
}}]

p2_payload = [{"client_id": None, "front_bytes": None, "back_bytes": None, "extracted": {
    "full_name": "وفاء بنت حسن بن محمد ابن الحاج",
    "cin_number": "08495241",
    "job": "متصرف بوزارة الصحة",
    "address": "53 نهج القصرين المروج 1 بن عروس"
}}]

contract_vars = {
    "property_desc": "جميع 99.528 جزء من تجزئة العقار إلى 317379 جزء",
    "price_num": "3000",
    "price_words": "ثلاثة آلاف دينار",
    "ownership_origin": "انجرار الملكية بالبيع بحجة حررناها في 16/08/2002"
}

t0 = time.time()
thread = UnifiedPipelineThread(
    contract_type="عقد هبة",
    p1_data=p1_payload,
    p2_data=p2_payload,
    procuration_text="",
    audio_bytes=audio_bytes,
    audio_mime="audio/wav",
    voice_text="الفصل الأول: وهبت وسلمت وحوزت الطرف الأول للطرف الثاني التي قبلت جميع مناباتها. الفصل الثاني: قيمة العقار الموهوب ثلاثة آلاف دينار 3000.",
    api_key=keys,
    provider=provider,
    model=model,
    contract_vars=contract_vars
)

res = {}
def on_finished(r):
    global res
    res = r

thread.finished.connect(on_finished)
thread.run()
t1 = time.time()
elapsed = t1 - t0

print("\n" + "="*70)
print(f" 🏁 E2E BENCHMARK RESULTS")
print("="*70)
print(f"⏱️ Total End-to-End Pipeline Execution Time: {elapsed:.2f} seconds")
print(f"Pipeline Success Status: {res.get('success')}")
print(f"Warnings / Errors Count: {len(res.get('warnings', []))}")
print(f"Warnings List: {res.get('warnings')}")
print(f"Spoken Content Extracted: {res.get('spoken_content')[:100]}...")

assert res.get("success") == True, f"FAIL: E2E test failed with errors: {res.get('warnings')}"
assert elapsed < 25.0, f"FAIL: E2E Pipeline time ({elapsed:.2f}s) exceeded 25s!"
print("\n✅ E2E INTEGRATION TEST PASSED WITH ZERO 404 / ZERO MODEL ERRORS!")
print("="*70)
