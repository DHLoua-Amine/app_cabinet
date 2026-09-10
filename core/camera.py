import os
import socket
import threading
import time
import cv2
import numpy as np

def check_ip_reachable(ip_url: str, timeout: float = 1.5) -> bool:
    """Socket test to prevent OpenCV network freezes on offline IP cameras."""
    if not isinstance(ip_url, str):
        return True
    ip_str = str(ip_url).strip()
    if not ip_str:
        return False
    if ip_str.isdigit():
        return True  # USB camera index like 0, 1
    
    try:
        clean = ip_str
        for proto in ("http://", "https://", "rtsp://", "rtp://"):
            if clean.lower().startswith(proto):
                clean = clean[len(proto):]
                break
        if "@" in clean:
            clean = clean.split("@")[-1]
        host_port = clean.split("/")[0].split("?")[0]
        if ":" in host_port:
            host, port_s = host_port.split(":")
            port = int(port_s)
        else:
            host = host_port
            port = 554 if ip_str.lower().startswith("rtsp://") else 80
        
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def probe_camera_stream(source, timeout: float = 2.5) -> bool:
    """
    Real probe function: tests if the camera/URL returns a valid video frame!
    Used by Settings page test button so it NEVER lies to the user.
    """
    if source is None:
        return False
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        try:
            dev_idx = int(source)
            cap = cv2.VideoCapture(dev_idx, cv2.CAP_ANY)
            if cap and cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                return ret and frame is not None
            return False
        except Exception:
            return False
    
    src = str(source).strip()
    if not src:
        return False
    
    if not src.startswith("http://") and not src.startswith("https://") and not src.startswith("rtsp://"):
        src = "http://" + src
    
    if not check_ip_reachable(src, timeout=1.2):
        return False

    is_http = src.startswith("http://") or src.startswith("https://")
    try:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "fflags;nobuffer|flags;low_delay|max_delay;0"
        cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG if is_http else cv2.CAP_ANY)
        if cap and cap.isOpened():
            start_t = time.time()
            while time.time() - start_t < timeout:
                ret, frame = cap.read()
                if ret and frame is not None:
                    cap.release()
                    return True
                time.sleep(0.05)
            cap.release()
    except Exception as e:
        print(f"[Camera Probe] Error probing {src}: {e}")
    
    if is_http:
        try:
            base_url = src.rsplit('/', 1)[0]
            shot_url = f"{base_url}/shot.jpg"
            import urllib.request
            req = urllib.request.urlopen(shot_url, timeout=timeout)
            # Un simple « plus de 100 octets » suffisait a declarer le succes.
            # Sur un reseau avec portail captif, ou derriere un routeur qui repond
            # a toute adresse, la page d'erreur renvoyee passait pour une camera :
            # le notaire lisait « connecte » sur n'importe quelle adresse.
            statut = getattr(req, "status", None) or req.getcode()
            if statut != 200:
                return False
            type_contenu = (req.headers.get("Content-Type") or "").lower()
            if not type_contenu.startswith("image/"):
                return False
            img_bytes = req.read()
            if len(img_bytes) < 100:
                return False
            # En-tete JPEG (FF D8 FF) ou PNG : une page HTML servie avec un
            # Content-Type menteur ne passera pas cette derniere porte.
            if img_bytes[:3] == b"\xff\xd8\xff" or img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                return True
            return False
        except Exception:
            pass

    return False


_active_camera_instance = None

def stop_active_camera():
    global _active_camera_instance
    if _active_camera_instance is not None:
        try:
            _active_camera_instance.stop()
        except Exception as stop_err:
            # (b) A camera that will not stop holds the device open, so the next
            # start fails for a reason that looks like "no camera connected".
            from system_guardian import log_system_error
            log_system_error("could not stop the active camera", stop_err)
        _active_camera_instance = None

class VideoCaptureThread:
    # How long to wait for the device to produce its FIRST frame after it opens.
    # Kept below CameraThread.CONNECT_TIMEOUT_S so the camera gives up before the
    # layer above it does.
    FIRST_FRAME_TIMEOUT_S = 12.0

    def __init__(self, source=0):
        self.source = source
        self.cap = None
        self.frame = None
        self.ret = False
        self.running = False
        self.failed = False
        self.thread = None

    def start(self):
        global _active_camera_instance
        if self.running or self.failed:
            return
        _active_camera_instance = self
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        src = self.source
        if isinstance(src, str):
            src = src.strip()
            while src.startswith("/"):
                src = src[1:].strip()
            if not src.startswith("http://") and not src.startswith("https://") and not src.startswith("rtsp://"):
                src = "http://" + src
            if not src.endswith("/video") and not src.startswith("rtsp") and not src.endswith("/shot.jpg") and not src.endswith("/mjpeg"):
                src = src.rstrip("/") + "/video"

        is_http = isinstance(src, str) and (
            src.startswith("http://") or src.startswith("https://")
        )
        is_network = is_http or (isinstance(src, str) and (
            src.startswith("rtsp://") or src.startswith("rtp://")
        ))

        # Fast non-blocking socket test to prevent OpenCV 30s network locks
        if is_network and not check_ip_reachable(src, timeout=1.5):
            self.running = False
            self.failed = True
            return

        # Engine 1: Try OpenCV VideoCapture first with FFMPEG nobuffer & low_delay flags
        try:
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
            self.cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG if is_network else cv2.CAP_ANY)
            if self.cap:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            print(f"[Camera] OpenCV open failed for {src}: {e}")

        cv_worked = False
        # Wait for the first frame for up to FIRST_FRAME_TIMEOUT_S rather than the old
        # five attempts over 150 ms. Some cameras (and most phone/IP streams) open
        # instantly but need a couple of seconds before they hand over a picture, and
        # giving up in 150 ms declared those dead. Interruptible, so stopping the camera
        # during the wait still takes effect immediately.
        if self.cap and self.cap.isOpened():
            probe_deadline = time.time() + self.FIRST_FRAME_TIMEOUT_S
            while self.running and time.time() < probe_deadline:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    cv_worked = True
                    self.ret = True
                    # Downscale high-res mobile camera streams (1080p/4K) to 640px for ultra-fast 30 FPS rendering
                    h, w = frame.shape[:2]
                    if w > 640:
                        frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_NEAREST)
                    self.frame = frame
                    break
                time.sleep(0.03)

        if cv_worked:
            # OpenCV is streaming cleanly
            consecutive_failures = 0
            while self.running and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    if w > 640:
                        frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_NEAREST)
                    self.ret = True
                    self.frame = frame
                    consecutive_failures = 0
                    time.sleep(0.01)  # Smooth 30-60 FPS real-time stream
                else:
                    self.ret = False
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        break
                    time.sleep(0.03)
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    # (c) Safe. Releasing a capture that has already gone away -
                    # unplugged, or released by the other exit path below.
                    pass

        # If OpenCV failed or lost stream and source is HTTP, switch to Snapshot Engine (/shot.jpg)
        if self.running and is_http:
            base_url = src.rsplit('/', 1)[0]
            shot_url = f"{base_url}/shot.jpg"
            print(f"[Camera] Switching to Ultra-Fast HTTP Snapshot Engine: {shot_url}")
            import urllib.request
            import numpy as np

            while self.running:
                try:
                    req = urllib.request.urlopen(shot_url, timeout=1)
                    img_bytes = req.read()
                    img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        h, w = frame.shape[:2]
                        if w > 1280:
                            frame = cv2.resize(frame, (1280, int(h * 1280 / w)), interpolation=cv2.INTER_NEAREST)
                        self.frame = frame
                        self.ret = True
                    time.sleep(0.03)
                except Exception as e:
                    self.ret = False
                    time.sleep(0.2)

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                # (c) Safe, same reason as above.
                pass

        # The capture loop has ended, so this device is finished. Without this the
        # thread left running=True and ret=True with the last frame still in hand, so
        # read_frame() kept serving that frozen image forever: an unplugged camera went
        # on "recognising" whoever happened to be in view when it died.
        self.ret = False
        self.frame = None
        self.running = False

    def read_frame(self):
        # Never hand back a stale frame once the device has gone away.
        if not self.running:
            return False, None
        return self.ret, self.frame

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()

import json
from config import DATA_DIR

CAM_CONFIG_FILE = DATA_DIR / "camera_config.json"

def get_saved_camera_source():
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("camera_source", 0)
        except Exception as read_err:
            from system_guardian import log_system_error
            log_system_error("could not read the saved camera source; "
                             "falling back to the default device", read_err)
    return 0

def get_saved_secondary_camera_source():
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("camera_source_2", "")
        except Exception:
            pass
    return ""

def get_saved_tertiary_camera_source():
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("camera_source_3", "")
        except Exception:
            pass
    return ""

def has_saved_camera_source() -> bool:
    """
    True only when a camera has actually been configured on this machine.

    get_saved_camera_source() falls back to 0, which is indistinguishable from a real
    choice of device 0. Auto-start needs that difference: probing a camera that was
    never set up costs several seconds and shows an alarming error on a machine that
    simply has no webcam.
    """
    if not CAM_CONFIG_FILE.exists():
        return False
    try:
        return "camera_source" in json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False


def get_camera_autostart() -> bool:
    """Whether the camera should come up by itself at launch. Default on."""
    if not CAM_CONFIG_FILE.exists():
        return True
    try:
        return bool(json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8")).get("autostart", True))
    except Exception:
        return True


def set_camera_autostart(enabled: bool):
    data = {}
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["autostart"] = bool(enabled)
    try:
        CAM_CONFIG_FILE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as write_err:
        from system_guardian import log_system_error
        log_system_error("could not save the camera autostart setting", write_err)
        return False


def set_saved_camera_source(source):
    # Merge, so saving a source does not wipe the autostart preference.
    data = {}
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["camera_source"] = source
    try:
        CAM_CONFIG_FILE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as write_err:
        from system_guardian import log_system_error
        log_system_error("could not save the camera source", write_err)
        return False

def set_saved_secondary_camera_source(source):
    data = {}
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["camera_source_2"] = source
    try:
        CAM_CONFIG_FILE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as write_err:
        from system_guardian import log_system_error
        log_system_error("could not save the secondary camera source", write_err)
        return False

def set_saved_tertiary_camera_source(source):
    data = {}
    if CAM_CONFIG_FILE.exists():
        try:
            data = json.loads(CAM_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["camera_source_3"] = source
    try:
        CAM_CONFIG_FILE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as write_err:
        from system_guardian import log_system_error
        log_system_error("could not save the tertiary camera source", write_err)
        return False
