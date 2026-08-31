"""
ui/pages/settings/workers.py — Asynchronous QThread workers for settings tasks.
"""

from PySide6.QtCore import QThread, Signal

class CamConnectThread(QThread):
    finished = Signal(bool)
    
    def __init__(self, ip_url):
        super().__init__()
        self.ip_url = ip_url
        
    def run(self):
        from camera import check_ip_reachable
        res = check_ip_reachable(self.ip_url, timeout=0.3)
        self.finished.emit(res)


class BackupThread(QThread):
    finished = Signal(str)  # returns path of zip or empty string
    
    def run(self):
        from system_guardian import create_full_system_backup
        try:
            zip_p = create_full_system_backup(
                "manual_notary_backup", should_cancel=self.isInterruptionRequested)
            if zip_p and zip_p.exists():
                self.finished.emit(str(zip_p))
            else:
                self.finished.emit("")
        except Exception:
            self.finished.emit("")


class UpdateCheckThread(QThread):
    finished = Signal(object)  # returns update info dict or None
    
    def run(self):
        from updater import check_for_update
        try:
            up_info = check_for_update()
            self.finished.emit(up_info)
        except Exception:
            self.finished.emit(None)


class ArchiveImportThread(QThread):
    finished = Signal(dict)
    
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
        
    def run(self):
        from archive_importer import bulk_import_legacy_notary_folders
        try:
            res = bulk_import_legacy_notary_folders(
                self.folder_path, should_cancel=self.isInterruptionRequested)
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({
                "status": "error", 
                "folders_scanned": 0,
                "clients_created": 0,
                "documents_imported": 0,
                "faces_extracted": 0,
                "logs": [f" خطأ غير متوقع أثناء الاستيراد: {str(e)}"]
            })
