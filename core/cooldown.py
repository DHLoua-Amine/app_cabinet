import time
from typing import Dict, Tuple

class CooldownManager:
    def __init__(self, cooldown_seconds: float = 30.0):
        self.cooldown_seconds = cooldown_seconds
        self.last_logs: Dict[str, float] = {}

    def process_detection(self, client_id: str, location: str) -> Tuple[str, bool]:
        now = time.time()
        key = f"{client_id}_{location}"
        last_time = self.last_logs.get(key, 0.0)

        if now - last_time > self.cooldown_seconds:
            self.last_logs[key] = now
            return "LOGGED", True
        return "COOLDOWN", False
