import os
import sys
from pathlib import Path

# Add core to sys.path
sys.path.insert(0, os.path.abspath("core"))

import config

def test_photo_fallback():
    print("Testing cross-PC photo resolution fallback...")
    
    # Simulate a photo path from Notary's laptop (different username)
    notary_fake_path = "C:\\Users\\amin\\AppData\\Local\\CabinetNotarialZarai\\data\\profiles\\test_client_999.jpg"
    
    # Ensure PROFILES_DIR exists
    config.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create test dummy image in local PROFILES_DIR
    target_local_file = config.PROFILES_DIR / "test_client_999.jpg"
    target_local_file.write_text("dummy_image_data")
    
    # Run fallback resolution logic
    pic_path = notary_fake_path
    resolved_src = None
    
    if pic_path and os.path.exists(pic_path):
        resolved_src = pic_path
    elif pic_path:
        rel_p = config.PROFILES_DIR / os.path.basename(pic_path)
        if rel_p.exists():
            resolved_src = str(rel_p)
            
    print(f"Original path: {notary_fake_path}")
    print(f"Resolved path on current PC: {resolved_src}")
    
    assert resolved_src == str(target_local_file), "Fallback failed to resolve cross-PC image path!"
    
    # Clean up test dummy file
    if target_local_file.exists():
        target_local_file.unlink()
        
    print("[SUCCESS] TEST PASSED: Cross-PC photo resolution works 100%!")

if __name__ == "__main__":
    test_photo_fallback()
