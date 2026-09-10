import os
import sys
import tempfile
import sqlite3
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "core") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "core"))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
from db_server import DatabaseServer, DEFAULT_PORT
from db_client import RemoteConnection, probe
import reception

def test_sync_photo_and_cache():
    print("[TEST] Starting test_sync_photo_and_cache...")
    
    # 1. Create a dummy db
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test_reception.db"
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE clients (
            client_id TEXT PRIMARY KEY,
            nom TEXT,
            prenom TEXT,
            full_name TEXT,
            phone TEXT,
            face_embedding BLOB,
            created_at TEXT,
            profile_pic_path TEXT,
            documents_dir TEXT,
            cin_number TEXT,
            titre_foncier TEXT,
            profession TEXT,
            address TEXT
        )
    """)
    conn.commit()
    conn.close()

    token = "TEST-TOKEN-12345"
    server = DatabaseServer(str(db_file), token, host="127.0.0.1", port=8799)
    assert server.start(), "Server failed to start"
    time.sleep(0.5)

    try:
        # Create a test photo file
        photo_dir = Path(temp_dir) / "local_profiles"
        photo_dir.mkdir()
        dummy_photo = photo_dir / "test_client_001.jpg"
        dummy_photo.write_bytes(b"FFD8FFfakejpegdata123456789")

        # Record initial cache gen
        initial_gen = reception.cache_generation()

        client_conn = RemoteConnection("127.0.0.1", 8799, token)
        
        # Test photo sync
        ok = client_conn.sync_photo(str(dummy_photo))
        assert ok, "sync_photo returned False"
        print("[SUCCESS] sync_photo returned True")

        # Check server received photo
        server_photo = config.PROFILES_DIR / "test_client_001.jpg"
        assert server_photo.exists(), "Photo file not found in server PROFILES_DIR"
        assert server_photo.read_bytes() == b"FFD8FFfakejpegdata123456789", "Photo file content mismatch"
        print("[SUCCESS] Server received photo in PROFILES_DIR")

        # Check cache generation incremented
        new_gen = reception.cache_generation()
        assert new_gen > initial_gen, f"Cache generation did not increment ({initial_gen} -> {new_gen})"
        print(f"[SUCCESS] Cache generation incremented from {initial_gen} to {new_gen}")

        # Test execute write invalidates cache
        cur_gen = reception.cache_generation()
        client_conn.execute("INSERT INTO clients (client_id, nom) VALUES ('c1', 'Test')")
        time.sleep(0.2)
        after_write_gen = reception.cache_generation()
        assert after_write_gen > cur_gen, f"Cache generation after INSERT did not increment ({cur_gen} -> {after_write_gen})"
        print(f"[SUCCESS] Cache generation after remote write incremented from {cur_gen} to {after_write_gen}")

        client_conn.close()
        print("[ALL TESTS PASSED SUCCESSFULLY]")
    finally:
        server.stop()

if __name__ == "__main__":
    test_sync_photo_and_cache()
