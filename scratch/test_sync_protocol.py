import os, sys, time, json, base64, socket, threading

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('core'))

import core.reception as reception
from core.db_server import DatabaseServer
from core.config import PROFILES_DIR
from core.db_client import RemoteConnection

def test_photo_and_unknown_sync():
    print("--- TESTING PROTOCOL FIXES ---")
    
    # 1. Start test server
    server = DatabaseServer(host="127.0.0.1", port=15555, db_path=str(reception.DB_PATH), token="test_token")
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    # Create dummy photo on server side
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    dummy_photo_path = PROFILES_DIR / "test_sync_photo.jpg"
    with open(dummy_photo_path, "wb") as f:
        f.write(b"FAKE_JPEG_BINARY_DATA_12345")
    
    print(f"Created server photo: {dummy_photo_path}")

    # 2. Connect client
    conn = RemoteConnection(host="127.0.0.1", port=15555, token="test_token")

    # Test fetch_photo
    # Client does not have local copy of test_sync_photo.jpg in client directory initially
    fetched = conn.fetch_photo(str(dummy_photo_path))
    print(f"Fetched photo local path: {fetched}")
    assert os.path.exists(fetched), "Fetched photo file must exist locally!"
    with open(fetched, "rb") as f:
        content = f.read()
    assert content == b"FAKE_JPEG_BINARY_DATA_12345", "Photo binary content must match!"
    print("SUCCESS: Photo fetch over TCP verified!")

    # 3. Test Unknown Visitor Sync
    res = conn.get_unknown_visitors()
    print("get_unknown_visitors initial response:", res)

    # Push unknown visitor
    conn.push_unknown_visitor({
        "client_id": "new_1",
        "name": "Nouveau Client",
        "status": "new",
        "b64_crop": base64.b64encode(b"FAKE_CROP").decode("ascii")
    })

    res2 = conn.get_unknown_visitors()
    print("get_unknown_visitors after push:", res2)
    assert len(res2) > 0, "Unknown visitor push must be stored on server!"
    print("SUCCESS: Unknown visitor sync over TCP verified!")

    server.stop()
    print("--- ALL TEST PROTOCOLS PASSED ---")

if __name__ == "__main__":
    test_photo_and_unknown_sync()
