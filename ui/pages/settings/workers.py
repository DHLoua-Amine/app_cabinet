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


class UpdateDownloadThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str, str)  # (success, zip_path_or_err_msg, err_type)

    def __init__(self, update_info: dict):
        super().__init__()
        self.update_info = update_info

    def run(self):
        from updater import download_and_verify_update
        try:
            d_url = self.update_info.get("download_url", "")
            s_url = self.update_info.get("sha256_url", "")
            asset_api_url = self.update_info.get("asset_api_url", "")
            sha256_api_url = self.update_info.get("sha256_api_url", "")

            zip_path = download_and_verify_update(
                download_url=d_url,
                sha256_url=s_url,
                asset_api_url=asset_api_url,
                sha256_api_url=sha256_api_url,
                progress_callback=self.progress.emit
            )
            self.finished.emit(True, zip_path, "")
        except ValueError as val_err:
            self.finished.emit(False, str(val_err), "sha256_mismatch")
        except ConnectionError as conn_err:
            self.finished.emit(False, str(conn_err), "network_error")
        except Exception as e:
            self.finished.emit(False, str(e), "general_error")


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

