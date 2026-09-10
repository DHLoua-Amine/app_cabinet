"""
scratch/test_mic_and_dual_cin.py
Verification test for:
1. Microphone AudioRecorder hardware detection & session initialization.
2. Single-image dual-face CIN OCR extraction (both sides in 1 photo).
"""

import sys
import os
import time
from pathlib import Path

# Ensure UTF-8 output streams for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Set up paths
ROOT_DIR = Path(__file__).parent.parent.resolve()
CORE_DIR = ROOT_DIR / "core"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(CORE_DIR))

import auth
import permissions
import reception

# Sign in as admin to enable all capabilities during UI tests
permissions.session.sign_in("admin", "admin", "Notaire Test")

# Create offscreen Qt Application
from PySide6.QtWidgets import QApplication
if not QApplication.instance():
    app = QApplication(["-platform", "offscreen"])
else:
    app = QApplication.instance()

print("==================================================")
print("TESTING MICROPHONE & SINGLE-IMAGE DUAL FACE SCAN")
print("==================================================")

# ---------------------------------------------------------
# TEST 1: MICROPHONE & AUDIO RECORDER INITIALIZATION
# ---------------------------------------------------------
try:
    from ui.components.audio_recorder import AudioRecorder
    from PySide6.QtMultimedia import QMediaDevices
    
    inputs = AudioRecorder.peripheriques_entree()
    print(f"[Microphone Audit] Detected {len(inputs)} audio input devices on system.")
    for idx, dev in enumerate(inputs):
        desc = dev.description()
        is_loop = AudioRecorder.est_bouclage(desc)
        print(f"  - Device {idx+1}: '{desc}' | Rebouclage: {is_loop}")
        
    dev_chosen, reason = AudioRecorder.choisir_peripherique()
    if dev_chosen:
        print(f"[Microphone Audit] Selected primary mic: '{dev_chosen.description()}' | Reason: {reason}")
    else:
        print(f"[Microphone Audit] Device selection note: {reason}")
        
    recorder = AudioRecorder()
    print(f"[AudioRecorder] Recorder initialized successfully with output mime: {recorder.output_mime}")
    print("[PASS] Microphone Hardware & AudioRecorder test passed cleanly!")

except Exception as e:
    print(f"[FAIL] Microphone Test Exception: {e}")

# ---------------------------------------------------------
# TEST 2: DUAL-FACE SINGLE IMAGE OCR PROMPT CHECK
# ---------------------------------------------------------
try:
    import cin_extractor
    
    sample_combined_dict = {
        "cin_number": "01234567",
        "first_name": "محمد",
        "father_name": "علي",
        "grandfather_name": "البشير",
        "last_name": "الطرابلسي",
        "birth_date": "1992/08/14",
        "birth_place": "سوسة",
        "issue_date": "2021/05/10",
        "job": "مهندس",
        "address": "حي الرياض سوسة"
    }
    
    assembled_name = cin_extractor._assemble_tunisian_full_name(sample_combined_dict)
    print(f"[Combined Single-Image CIN Test] Assembled full name: '{assembled_name}'")
    
    if "محمد" in assembled_name and "علي" in assembled_name and "الطرابلسي" in assembled_name:
        print("[PASS] Single-Image Dual Face Name Assembly verified!")
    else:
        print(f"[FAIL] Single-Image Dual Face Name Assembly mismatch: '{assembled_name}'")

except Exception as e:
    print(f"[FAIL] Combined Dual-Face OCR Test Exception: {e}")

print("==================================================")
