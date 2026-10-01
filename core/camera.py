import os
import socket
import threading
import time
import cv2
import numpy as np

def check_ip_reachable(ip_url: str, timeout: float = 2.5) -> bool:
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


def discover_ip_camera_on_subnet(saved_source: str, target_port: int = 8080) -> str:
    """
    Scans the local Wi-Fi subnet (e.g. 192.168.0.1..254) for an active IP webcam
    if the phone's IP address changed on Wi-Fi (DHCP reassignment).
    Returns the discovered stream URL if found, else original saved_source.
    """
    if not isinstance(saved_source, str) or not saved_source.strip():
        return saved_source
    src_str = saved_source.strip()
    if src_str.isdigit():
        return saved_source  # USB Camera
    
    # Extract port & host if available
    port = target_port
    clean = src_str
    for proto in ("http://", "https://", "rtsp://"):
        if clean.lower().startswith(proto):
            clean = clean[len(proto):]
            break
    host_port = clean.split("/")[0].split("?")[0]
    if ":" in host_port:
        h, p_s = host_port.split(":")
        try:
            port = int(p_s)
        except Exception:
            pass
        clean_host = h
    else:
        clean_host = host_port

    parts = clean_host.split(".")
    if len(parts) != 4:
        return saved_source
    subnet_prefix = ".".join(parts[:3])

    import concurrent.futures
    def _probe_host(i):
        host_ip = f"{subnet_prefix}.{i}"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.15)
            res = s.connect_ex((host_ip, port))
            s.close()
            if res == 0:
                # Test if it returns valid camera stream/image
                test_url = f"http://{host_ip}:{port}/video"
                if probe_camera_stream(test_url, timeout=0.8):
                    return test_url
        except Exception:
            pass
        return None

    try:
        ips_to_scan = range(1, 255)
        with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
            results = ex.map(_probe_host, ips_to_scan)
            for res_url in results:
                if res_url:
                    # Found live camera on subnet! Update saved configuration automatically
                    set_saved_camera_source(res_url)
                    return res_url
    except Exception:
        pass

    return saved_source


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

        # 1. Local USB Camera (e.g. 0, 1)
        if isinstance(src, int) or (isinstance(src, str) and str(src).strip().isdigit()):
            dev_idx = int(src)
            try:
                self.cap = cv2.VideoCapture(dev_idx, cv2.CAP_ANY)
                if self.cap and self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            
            if self.cap and self.cap.isOpened():
                while self.running and self.cap and self.cap.isOpened():
                    try:
                        ret, frame = self.cap.read()
                        if ret and frame is not None and frame.size > 0:
                            h, w = frame.shape[:2]
                            if w > 640:
                                frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_NEAREST)
                            self.frame = frame
                            self.ret = True
                            time.sleep(0.001)
                        else:
                            time.sleep(0.02)
                    except Exception:
                        time.sleep(0.02)
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
            return

        # 2. Network IP Camera (HTTP or RTSP)
        src_str = str(src).strip()
        while src_str.startswith("/"):
            src_str = src_str[1:].strip()
        if not src_str.startswith("http://") and not src_str.startswith("https://") and not src_str.startswith("rtsp://"):
            src_str = "http://" + src_str

        is_http = src_str.startswith("http://") or src_str.startswith("https://")

        # Fast non-blocking socket reachability check
        if not check_ip_reachable(src_str, timeout=1.5):
            discovered = discover_ip_camera_on_subnet(src_str)
            if discovered != src_str and check_ip_reachable(discovered, timeout=1.5):
                src_str = discovered
            else:
                self.running = False
                self.failed = True
                return

        # ENGINE A: Native High-Speed Zero-Latency Auto-Reconnecting MJPEG Stream Engine for IP Webcams
        if is_http:
            mjpeg_url = src_str
            if not mjpeg_url.endswith("/video") and not mjpeg_url.endswith("/mjpeg") and not mjpeg_url.endswith("/shot.jpg"):
                mjpeg_url = mjpeg_url.rstrip("/") + "/video"
            
            import urllib.request
            reconnect_attempts = 0
            last_frame_time = time.time()
            engine_a_success = False

            while self.running:
                try:
                    print(f"[🌐 CAMERA CONNECTING] Opening HTTP MJPEG stream at {mjpeg_url}...", flush=True)
                    req = urllib.request.urlopen(mjpeg_url, timeout=3.0)
                    if req.status == 200:
                        print(f"[🌐 CAMERA CONNECTED] Connected to stream: {mjpeg_url}", flush=True)
                        stream_bytes = b''
                        consecutive_errs = 0
                        reconnect_attempts = 0
                        while self.running:
                            try:
                                chunk = req.read(16384)
                                if not chunk:
                                    break
                                stream_bytes += chunk
                                
                                # Cap buffer size to 256KB max to prevent memory queuing
                                if len(stream_bytes) > 262144:
                                    stream_bytes = stream_bytes[-65536:]

                                # Instant Buffer Drain: Jump straight to the LATEST complete frame
                                last_end = stream_bytes.rfind(b'\xff\xd9')
                                if last_end != -1:
                                    start_idx = stream_bytes.rfind(b'\xff\xd8', 0, last_end)
                                    if start_idx != -1:
                                        jpg_data = stream_bytes[start_idx : last_end + 2]
                                        stream_bytes = stream_bytes[last_end + 2:]
                                        
                                        img_arr = np.frombuffer(jpg_data, dtype=np.uint8)
                                        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                                        if frame is not None and frame.size > 0:
                                            h, w = frame.shape[:2]
                                            if w > 640:
                                                frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_NEAREST)
                                            self.frame = frame
                                            self.ret = True
                                            self.last_frame_time = time.time()
                                            last_frame_time = self.last_frame_time
                                            engine_a_success = True
                                            consecutive_errs = 0
                                    else:
                                        stream_bytes = stream_bytes[last_end + 2:]
                                time.sleep(0.001)
                            except Exception:
                                consecutive_errs += 1
                                if consecutive_errs > 15:
                                    break
                                time.sleep(0.02)
                        req.close()
                except Exception:
                    reconnect_attempts += 1
                    # If stream fails to connect/reconnect after 4 attempts or frame stale for 2.0s
                    if reconnect_attempts > 4:
                        self.ret = False
                        if engine_a_success or (time.time() - last_frame_time > 2.0):
                            break
                    time.sleep(0.3)
            
            if engine_a_success and not self.running:
                self.ret = False
                self.frame = None
                return

        # ENGINE B: OpenCV VideoCapture with Buffer Flushing for RTSP / Fallback video streams
        if is_http and not src_str.endswith("/video") and not src_str.endswith("/shot.jpg"):
            src_str = src_str.rstrip("/") + "/video"

        try:
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0|probedelay;0|reorder_queue_size;0"
            self.cap = cv2.VideoCapture(src_str, cv2.CAP_FFMPEG if is_http else cv2.CAP_ANY)
            if self.cap:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            print(f"[Camera] OpenCV VideoCapture open failed for {src_str}: {e}")

        if self.cap and self.cap.isOpened():
            consecutive_failures = 0
            while self.running and self.cap and self.cap.isOpened():
                try:
                    # Flush extra queued frames from OpenCV internal FFmpeg buffer
                    for _ in range(2):
                        self.cap.grab()
                    ret, frame = self.cap.retrieve()
                    if not ret or frame is None:
                        ret, frame = self.cap.read()
                    
                    if ret and frame is not None and frame.size > 0:
                        h, w = frame.shape[:2]
                        if w > 640:
                            frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_NEAREST)
                        self.frame = frame
                        self.ret = True
                        self.last_frame_time = time.time()
                        consecutive_failures = 0
                        time.sleep(0.001)
                    else:
                        self.ret = False
                        consecutive_failures += 1
                        if consecutive_failures > 30:
                            break
                        time.sleep(0.03)
                except Exception:
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        break
                    time.sleep(0.03)
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass

        # Complete teardown: mark thread as not running so CameraThread immediately notices stream termination
        self.ret = False
        self.frame = None
        self.running = False

    def read_frame(self):
        # Never hand back a stale frame once the device has gone away.
        if not self.running:
            return False, None
        if self.ret and self.frame is not None:
            frame = self.frame
            try:
                # Digital vertical ROI crop: disabled by default (0.0) to prevent chopping off forehead/eyes
                v_crop = 0.0
                if v_crop > 0.0:
                    h, w = frame.shape[:2]
                    top_cut = int(h * v_crop)
                    if h - top_cut > 100:
                        cropped = frame[top_cut:h, 0:w]
                        frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
            except Exception:
                frame = self.frame
            return self.ret, frame
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
