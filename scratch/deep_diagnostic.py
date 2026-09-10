import os, sys
sys.stdout.reconfigure(encoding='utf-8')

def search_code():
    files = [
        'ui/pages/presence_page.py',
        'ui/pages/home_page.py',
        'ui/components/camera_thread.py',
        'ui/services/camera_service.py',
        'ui/pages/clients_page.py',
        'ui/pages/fiche_client_page.py',
        'core/reception.py',
        'core/db_client.py',
        'core/db_server.py'
    ]

    print("--- DIAGNOSTIC AUDIT START ---")
    
    # Check 1: How presence_page / camera_thread handles Unknown detection
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            if any(k in line.lower() for k in ['inconnu', 'unknown', 'sync_photo', 'save_unknown', 'profile_pic_path', 'get_photo']):
                print(f"{path}:{idx} -> {line.strip()[:120]}")

if __name__ == '__main__':
    search_code()
