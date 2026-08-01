import os
import sys
import time
import json
import threading
import subprocess

class PerformanceMonitor:
    def __init__(self, log_path="logs/performance_log.json", interval=60):
        self.log_path = os.path.abspath(log_path)
        self.interval = interval
        self.running = False
        self.thread = None
        self.records = []
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        
    def start(self):
        self.running = True
        self.records = []
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def get_process_ram(self) -> float:
        """Returns RAM usage of the current process in MB."""
        try:
            pid = os.getpid()
            cmd = f'tasklist /FI "PID eq {pid}" /FO CSV /NH'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            # Example output: "python.exe","24112","Console","1","56 120 K"
            parts = res.stdout.strip().split(",")
            if len(parts) >= 5:
                mem_str = parts[4].strip('"').strip()
                # Extract digits only to avoid encoding / locale separator issues
                mem_digits = "".join(c for c in mem_str if c.isdigit())
                if mem_digits:
                    return float(mem_digits) / 1024.0
        except Exception:
            pass
        return 0.0

    def get_jarvis_processes_count(self) -> int:
        """Returns the number of python processes running Jarvis scripts."""
        try:
            cmd = 'wmic process where "name=\'python.exe\'" get CommandLine, ProcessId /format:csv'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            count = 0
            for line in res.stdout.splitlines():
                if line.strip() and not line.startswith("Node"):
                    line_lower = line.lower()
                    if any(x in line_lower for x in ["jarvis", "run.py", "gui_app.py", "agent.py"]):
                        count += 1
            if count > 0:
                return count
        except Exception:
            pass
            
        # Fallback: count all python.exe processes using tasklist
        try:
            cmd = 'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            lines = [l for l in res.stdout.splitlines() if l.strip()]
            return len(lines)
        except Exception:
            return 1

    def _loop(self):
        from ai.engine import RequestContext
        
        start_cpu = time.process_time()
        start_time = time.time()
        
        while self.running:
            try:
                ram = self.get_process_ram()
                elapsed_time = time.time() - start_time
                elapsed_cpu = time.process_time() - start_cpu
                cpu_percent = (elapsed_cpu / elapsed_time) * 100.0 if elapsed_time > 0 else 0.0
                
                threads = threading.active_count()
                rc_count = RequestContext.get_active_count()
                proc_count = self.get_jarvis_processes_count()
                
                record = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_seconds": round(time.time() - start_time, 1),
                    "ram_mb": round(ram, 2),
                    "cpu_percent": round(cpu_percent, 2),
                    "thread_count": threads,
                    "request_context_count": rc_count,
                    "jarvis_process_count": proc_count
                }
                
                self.records.append(record)
                self._save_log()
                
            except Exception as e:
                print(f"[PERFORMANCE_MONITOR] Error in loop: {e}")
                
            # Sleep in small chunks to exit loop quickly
            for _ in range(int(self.interval)):
                if not self.running:
                    break
                time.sleep(1)

    def _save_log(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[PERFORMANCE_MONITOR] Error saving log: {e}")
