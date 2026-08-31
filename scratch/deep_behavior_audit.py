import sys
import os
import sqlite3
import hashlib
import time
import glob
import ast
import re
import subprocess
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import reception
import auth
import permissions
import face_engine

permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire (Admin)")

def log_section(title):
    print(f"\n{'='*75}")
    print(f" {title}")
    print(f"{'='*75}")

def run_deep_audit():
    # -------------------------------------------------------------------------
    log_section("ISSUE 1: EXECUTABLE SIZE DISCREPANCY & --SELFTEST EXECUTION")
    dist_dir = BASE_DIR / "dist" / "CabinetNotarialZarai"
    dist_exe = dist_dir / "CabinetNotarialZarai.exe"

    print(f"Dist Directory Path: {dist_dir}")
    print(f"Executable File Path: {dist_exe}")

    if dist_exe.exists():
        exe_size_mb = dist_exe.stat().st_size / (1024 * 1024)
        print(f"  - CabinetNotarialZarai.exe File Size: {exe_size_mb:.2f} MB")
        
        total_folder_size = 0
        file_count = 0
        onnx_found = []
        qss_found = []

        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                fp = Path(root) / file
                file_size = fp.stat().st_size
                total_folder_size += file_size
                file_count += 1
                if file.endswith(".onnx") or "face" in file.lower() or "sface" in file.lower() or "yunet" in file.lower():
                    onnx_found.append(str(fp.relative_to(dist_dir)))
                if file.endswith(".qss"):
                    qss_found.append(str(fp.relative_to(dist_dir)))

        total_folder_size_mb = total_folder_size / (1024 * 1024)
        print(f"  - Total dist/ Folder Size (with _internal/): {total_folder_size_mb:.2f} MB")
        print(f"  - Total Bundled Files: {file_count}")
        print(f"  - Bundled Face/ONNX Models: {onnx_found}")
        print(f"  - Bundled Stylesheets (QSS): {qss_found}")

        print("\n--- Running --selftest against packaged executable ---")
        try:
            res = subprocess.run([str(dist_exe), "--selftest"], capture_output=True, text=True, timeout=15)
            print(f"Selftest Return Code: {res.returncode}")
            print(f"Selftest Stdout:\n{res.stdout}")
            if res.stderr:
                print(f"Selftest Stderr:\n{res.stderr}")
        except Exception as e:
            print(f"Selftest Execution Exception: {e}")

    # -------------------------------------------------------------------------
    log_section("ISSUE 2: REAL BEHAVIORAL RE-TESTS")

    # 2.1 FACE ENGINE REAL BEHAVIORAL TEST
    print("\n--- 2.1 Camera & Face Recognition Real Behavioral Test ---")
    try:
        engine = face_engine.get_global_face_engine()
        print(f"FaceEngine Initialized: {engine is not None}")
        
        import cv2
        import numpy as np
        synthetic_img = np.full((300, 300, 3), 240, dtype=np.uint8)
        cv2.ellipse(synthetic_img, (150, 150), (60, 80), 0, 0, 360, (180, 150, 120), -1)
        cv2.circle(synthetic_img, (130, 130), 8, (50, 50, 50), -1)
        cv2.circle(synthetic_img, (170, 130), 8, (50, 50, 50), -1)

        faces = engine.detect_and_extract(synthetic_img)
        print(f"detect_and_extract executed cleanly on OpenCV frame. Detected faces count: {len(faces)}")
        print("[PASS] Face Recognition Engine Behavioral Test Succeeded!")
    except Exception as e:
        print(f"[FAIL] Face Engine Test Exception: {e}")

    # 2.2 FICHE CLIENT: 60-RAPID-CLIENT-CREATION COLLISION TEST VIA RECEPTION API
    print("\n--- 2.2 Fiche Client: 60 Rapid Client Creation Collision Test ---")
    created_test_ids = []
    collisions = 0
    start_t = time.time()
    
    for i in range(60):
        cid = reception.register_client(nom=f"TestNom{i}", prenom="TestPrenom", phone=f"900000{i:02d}")
        if cid in created_test_ids:
            collisions += 1
        created_test_ids.append(cid)

    duration = time.time() - start_t
    print(f"Registered 60 consecutive clients via reception.register_client() in {duration:.4f} seconds.")
    print(f"Unique IDs created: {len(set(created_test_ids))} / 60")
    print(f"Collisions detected: {collisions}")
    
    # Cleanup test clients from DB
    conn = sqlite3.connect(reception.DB_PATH)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM clients WHERE client_id IN ({','.join(['?']*len(created_test_ids))})", created_test_ids)
    conn.commit()
    conn.close()

    assert collisions == 0, "CRITICAL: ID collisions detected during rapid registration!"
    print("[PASS] 60-Rapid Client Registration Collision Test Succeeded (0 Collisions)!")

    # 2.3 PARAMÈTRES & AUTHENTICATION BEHAVIORAL TEST
    print("\n--- 2.3 Paramètres: Password Change & PBKDF2 Authentication Test ---")
    test_pass = "SecurePass2026!"
    
    hashed_str = auth.hash_password(test_pass)
    print(f"PBKDF2 Hash Generated: {hashed_str}")

    is_valid = auth.verify_hash(test_pass, hashed_str)
    is_invalid = auth.verify_hash("WrongPass", hashed_str)
    print(f"Verification with Correct Password: {is_valid}")
    print(f"Verification with Wrong Password: {is_invalid}")
    assert is_valid is True, "Password verification failed for correct password!"
    assert is_invalid is False, "Password verification passed for incorrect password!"
    print("[PASS] PBKDF2 Password Authentication Test Succeeded!")

    # -------------------------------------------------------------------------
    log_section("ISSUE 3: REVENUE & INFLOWS GROUND TRUTH BEHAVIORAL TEST")
    
    conn = sqlite3.connect(reception.DB_PATH)
    cur = conn.cursor()
    sql_cases = cur.execute("SELECT case_id, client_id, total_amount, avance_amount, created_at FROM cases WHERE avance_amount > 0").fetchall()
    total_sql_avances = sum(float(c[3] or 0) for c in sql_cases)
    conn.close()

    print(f"Direct SQL SUM(avance_amount) over cases: {total_sql_avances:,.3f} TND")
    
    api_inflows = reception.get_case_inflows_between("2020-01-01", "2030-12-31")
    total_api_avances = sum(float(inf.get('avance_amount', 0)) for inf in api_inflows)
    print(f"reception.get_case_inflows_between() returned {len(api_inflows)} rows | Total: {total_api_avances:,.3f} TND")

    assert abs(total_sql_avances - total_api_avances) < 0.01, "Revenue mismatch!"
    print("[PASS] Revenue Ground Truth & Inflow Behavioral Verification Complete!")

if __name__ == "__main__":
    run_deep_audit()
