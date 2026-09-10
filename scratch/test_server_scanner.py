import socket
import concurrent.futures

def scan_server_port(port=8765, timeout=0.15):
    """
    Scans local subnet for the notary office server on port 8765.
    Returns the server IP string or None if not found.
    """
    try:
        # Get local IP address to find subnet (e.g. 192.168.1.50)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "192.168.1.1"

    prefix = ".".join(local_ip.split(".")[:3])  # e.g. "192.168.1"
    ip_candidates = [f"{prefix}.{i}" for i in range(1, 255)]

    def probe(ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            res = sock.connect_ex((ip, port))
            sock.close()
            if res == 0:
                return ip
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(probe, ip) for ip in ip_candidates]
        for f in concurrent.futures.as_completed(futures):
            found = f.result()
            if found:
                return found
    return None

if __name__ == "__main__":
    print("Testing subnet scanner for port 8765...")
    found_ip = scan_server_port()
    print("Found server IP:", found_ip)
