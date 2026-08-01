# -*- coding: utf-8 -*-
import time
import os
import subprocess
from core.intents.fast_command_router import classify_routing_level
from core.agent import open_program

# Predefined launch applications and their expected executable names for process checks
LAUNCH_VERIFICATION_MAP = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "epic games launcher": "EpicGamesLauncher.exe",
    "blender": "blender.exe",
    "visual studio code": "Code.exe",
    "vscode": "Code.exe",
    "calculator": "calc.exe",
    "kalkulačka": "calc.exe",
    "notepad": "notepad.exe",
    "poznámkový blok": "notepad.exe",
    "steam": "steam.exe"
}

def is_ignored_verification_app(name: str) -> bool:
    name_lower = name.lower()
    ignored_keywords = ["epicwebhelper", "updater", "crash reporter", "crashreporter", "crash_reporter", "helper"]
    return any(kw in name_lower for kw in ignored_keywords)

def get_all_processes_info():
    processes = []
    try:
        cmd = "wmic process get Name,ParentProcessId,ProcessId /format:csv"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("Node"):
                continue
            parts = line.split(",")
            if len(parts) >= 4:
                name = parts[1].strip()
                ppid_str = parts[2].strip()
                pid_str = parts[3].strip()
                if ppid_str.isdigit() and pid_str.isdigit():
                    processes.append({
                        "name": name,
                        "pid": int(pid_str),
                        "ppid": int(ppid_str)
                    })
    except Exception as e:
        print(f"[LAUNCH_VERIFY] wmic failed: {e}")
        try:
            cmd = "tasklist /FO CSV /NH"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip('"')
                    pid_str = parts[1].strip('"')
                    if pid_str.isdigit():
                        processes.append({
                            "name": name,
                            "pid": int(pid_str),
                            "ppid": 0
                        })
        except Exception:
            pass
    return processes

def get_descendants(parent_pid, processes_info):
    from collections import defaultdict
    children = defaultdict(list)
    for proc in processes_info:
        children[proc["ppid"]].append(proc)
        
    queue = [parent_pid]
    descendants = []
    visited = set()
    
    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        
        for child in children[curr]:
            if child["pid"] not in visited:
                descendants.append(child)
                queue.append(child["pid"])
    return descendants

def select_verified_process(app_name, parent_pid, processes_info):
    descendants = get_descendants(parent_pid, processes_info)
    
    parent_proc = next((p for p in processes_info if p["pid"] == parent_pid), None)
    
    candidates = []
    if parent_proc:
        candidates.append(parent_proc)
    candidates.extend(descendants)
    
    app_lower = app_name.lower()
    valid_candidates = []
    
    if "epic" in app_lower:
        for c in candidates:
            c_name = c["name"].lower()
            if "epic" in c_name:
                valid_candidates.append(c)
    elif "calculator" in app_lower or "kalkulacka" in app_lower:
        for c in candidates:
            c_name = c["name"].lower()
            if c_name in ("calc.exe", "calculator.exe", "win32calculator.exe", "applicationframehost.exe"):
                valid_candidates.append(c)
    else:
        for c in candidates:
            c_name = c["name"].lower()
            ignored_keywords = ["updater", "crash reporter", "crashreporter", "crash_reporter", "helper"]
            if not any(kw in c_name for kw in ignored_keywords):
                valid_candidates.append(c)
                
    if valid_candidates:
        # Prefer main EpicGamesLauncher over helper epicwebhelper if both are active in the tree
        for c in valid_candidates:
            if "epicgameslauncher" in c["name"].lower():
                return c
        return valid_candidates[0]
        
    return None

def is_pid_running(pid):
    try:
        cmd = f'tasklist /FI "PID eq {pid}" /FO CSV /NH'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
        return str(pid) in res.stdout
    except Exception:
        return False

def kill_pid(pid):
    try:
        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True, timeout=3)
    except Exception:
        pass

def run_launch_stress(num_iterations=1, verify_launch=False, dry_run=True, mock_cache_data=None):
    if mock_cache_data is None:
        mock_cache_data = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "notepad": "C:\\Windows\\notepad.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
            "blender": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "visual studio code": "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
            "steam": "C:\\Program Files (x86)\\Steam\\steam.exe"
        }

    stats = {
        "total_runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "elapsed_times": [],
        "failures_details": [],
        "expected_application": None,
        "matched_application": None,
        "route": None,
        "confidence": None,
        "resolved_path": None,
        "pid": None,
        "process_name": None,
        "verification_method": None,
        "verification_duration": None,
        "timeout_used": None,
        "parent_pid": None,
        "detected_child_pids": [],
        "final_detected_process": None
    }

    commands = [
        "zapni chrome",
        "zapni epic",
        "zapni blender",
        "otevři vscode",
        "otevři kalkulačku",
        "otevři notepad"
    ]

    expected_app_map = {
        "zapni chrome": "google chrome",
        "zapni epic": "epic games launcher",
        "zapni blender": "blender",
        "otevři vscode": "visual studio code",
        "otevři kalkulačku": "calculator",
        "otevři notepad": "notepad"
    }

    if dry_run:
        # Dry run simulation
        for _ in range(num_iterations):
            for cmd in commands:
                stats["total_runs"] += 1
                start_t = time.perf_counter()
                
                try:
                    # 1. Routing classification check
                    route_info = classify_routing_level(cmd)
                    
                    stats["expected_application"] = expected_app_map.get(cmd)
                    stats["route"] = route_info.get("route")
                    stats["confidence"] = route_info.get("confidence")
                    if route_info.get("step"):
                        stats["matched_application"] = route_info["step"].get("input", {}).get("name")
                    else:
                        stats["matched_application"] = None

                    if route_info["route"] != "FAST_COMMAND":
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": f"Routing failure: expected FAST_COMMAND, got {route_info['route']}",
                            "expected_application": expected_app_map.get(cmd),
                            "matched_application": route_info.get("step", {}).get("input", {}).get("name") if route_info.get("step") else None,
                            "route": route_info.get("route"),
                            "confidence": route_info.get("confidence")
                        })
                        continue
                        
                    step = route_info["step"]
                    if not step or step["tool"] != "open_app":
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": f"Tool failure: expected open_app, got {step.get('tool') if step else None}",
                            "expected_application": expected_app_map.get(cmd),
                            "matched_application": step.get("input", {}).get("name") if step else None,
                            "route": route_info.get("route"),
                            "confidence": route_info.get("confidence")
                        })
                        continue
                    
                    # 2. Simulate launch check
                    app_name = step["input"]["name"]
                    
                    # Verify cache matching in simulation
                    found = False
                    for cache_name in mock_cache_data:
                        if app_name.lower() in cache_name.lower() or cache_name.lower() in app_name.lower():
                            found = True
                            break
                            
                    if not found and app_name not in ("calc", "calculator", "kalkulačka"):
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": f"Application not found in mock cache: {app_name}",
                            "expected_application": expected_app_map.get(cmd),
                            "matched_application": app_name,
                            "route": route_info.get("route"),
                            "confidence": route_info.get("confidence")
                        })
                        continue
                        
                    elapsed = time.perf_counter() - start_t
                    stats["elapsed_times"].append(elapsed)
                    stats["success_runs"] += 1
                    
                    stats["resolved_path"] = mock_cache_data.get(expected_app_map.get(cmd), "C:\\mock_path.exe")
                    stats["pid"] = 9999
                    stats["process_name"] = LAUNCH_VERIFICATION_MAP.get(expected_app_map.get(cmd), "mock.exe")
                    stats["verification_method"] = "pid_tree"
                    stats["verification_duration"] = 0.05
                    stats["timeout_used"] = 30.0 if "epic" in cmd.lower() else 10.0
                    stats["parent_pid"] = 9999
                    stats["detected_child_pids"] = [10001, 10002]
                    stats["final_detected_process"] = LAUNCH_VERIFICATION_MAP.get(expected_app_map.get(cmd), "mock.exe")
                    
                except Exception as e:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": f"Simulation exception: {str(e)}",
                        "expected_application": expected_app_map.get(cmd),
                        "matched_application": None,
                        "route": None,
                        "confidence": 0.0
                    })
    else:
        # REAL RUN - Launches and verifies
        for _ in range(num_iterations):
            for cmd in commands:
                stats["total_runs"] += 1
                start_t = time.perf_counter()
                
                try:
                    # 1. Classify
                    route_info = classify_routing_level(cmd)
                    
                    stats["expected_application"] = expected_app_map.get(cmd)
                    stats["route"] = route_info.get("route")
                    stats["confidence"] = route_info.get("confidence")
                    if route_info.get("step"):
                        stats["matched_application"] = route_info["step"].get("input", {}).get("name")
                    else:
                        stats["matched_application"] = None

                    if route_info["route"] != "FAST_COMMAND":
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": f"Routing failure: expected FAST_COMMAND, got {route_info['route']}",
                            "expected_application": expected_app_map.get(cmd),
                            "matched_application": route_info.get("step", {}).get("input", {}).get("name") if route_info.get("step") else None,
                            "route": route_info.get("route"),
                            "confidence": route_info.get("confidence")
                        })
                        continue
                        
                    step = route_info["step"]
                    if not step or step["tool"] != "open_app":
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": f"Tool failure: expected open_app, got {step.get('tool') if step else None}",
                            "expected_application": expected_app_map.get(cmd),
                            "matched_application": step.get("input", {}).get("name") if step else None,
                            "route": route_info.get("route"),
                            "confidence": route_info.get("confidence")
                        })
                        continue
                        
                    app_name = step["input"]["name"]
                    
                    # 2. Launch real app via open_program
                    res = open_program(app_name)
                    
                    resolved_path = None
                    pid = None
                    if isinstance(res, dict):
                        resolved_path = res.get("path")
                        pid = res.get("pid")
                    
                    stats["resolved_path"] = resolved_path
                    stats["pid"] = pid
                    stats["parent_pid"] = pid
                    stats["timeout_used"] = 30.0 if "epic" in app_name.lower() else 10.0
                    
                    # 3. Verify launch if requested
                    verification_start = time.perf_counter()
                    launch_verified = False
                    matched_proc_info = None
                    verification_method = "none"
                    detected_child_pids = []
                    
                    if verify_launch:
                        poll_interval = 0.25
                        timeout = 30.0 if "epic" in app_name.lower() else 10.0
                        
                        if pid is not None:
                            verification_method = "pid_tree"
                            while time.perf_counter() - verification_start < timeout:
                                procs = get_all_processes_info()
                                descendants = get_descendants(pid, procs)
                                detected_child_pids = [d["pid"] for d in descendants]
                                
                                if "epic" in app_name.lower():
                                    print(f"[PROCESS_TREE] Checking tree for Parent PID {pid}:")
                                    if not descendants:
                                        print("  No descendants found yet.")
                                    for d in descendants:
                                        print(f"  -> parent_pid={pid}, child_pid={d['pid']}, child_process_name={d['name']}")
                                
                                matched_proc = select_verified_process(app_name, pid, procs)
                                if matched_proc:
                                    launch_verified = True
                                    matched_proc_info = matched_proc
                                    break
                                time.sleep(poll_interval)
                        else:
                            verification_method = "name_fallback"
                            exec_name = None
                            for key, val in LAUNCH_VERIFICATION_MAP.items():
                                if key in app_name.lower():
                                    exec_name = val
                                    break
                            if not exec_name:
                                exec_name = f"{app_name}.exe"
                                
                            allowed_names = [exec_name.lower()]
                            if exec_name.lower() in ("calc.exe", "calculator.exe", "win32calculator.exe", "applicationframehost.exe"):
                                allowed_names = ["calc.exe", "calculator.exe", "win32calculator.exe", "applicationframehost.exe"]
                                
                            while time.perf_counter() - verification_start < timeout:
                                procs = get_all_processes_info()
                                matched = [p for p in procs if p["name"].lower() in allowed_names]
                                if matched:
                                    launch_verified = True
                                    matched_proc_info = matched[0]
                                    break
                                time.sleep(poll_interval)
                                
                        verification_duration = time.perf_counter() - verification_start
                        stats["verification_duration"] = round(verification_duration, 3)
                        stats["verification_method"] = verification_method
                        stats["detected_child_pids"] = detected_child_pids
                        
                        if launch_verified and matched_proc_info:
                            stats["process_name"] = matched_proc_info["name"]
                            stats["final_detected_process"] = matched_proc_info["name"]
                            stats["pid"] = matched_proc_info["pid"]
                            
                            # Cleanup
                            kill_pid(matched_proc_info["pid"])
                            if pid is not None and pid != matched_proc_info["pid"]:
                                kill_pid(pid)
                        else:
                            stats["process_name"] = None
                            stats["final_detected_process"] = None
                            
                        # Logging requirement (task 6)
                        verify_status = "SUCCESS" if launch_verified else "FAILED"
                        print(f"\n[LAUNCH_VERIFY]")
                        print(f"Application:\n{app_name}")
                        print(f"\nResolved Path:\n{resolved_path}")
                        print(f"\nPID:\n{pid}")
                        print(f"\nVerification:\n{verify_status}")
                        print(f"\nDuration:\n{round(verification_duration, 2)}s\n")
                        
                        if not launch_verified:
                            stats["failed_runs"] += 1
                            stats["failures_details"].append({
                                "command": cmd,
                                "reason": f"Launch verification failed: application {app_name} did not start or process check timed out.",
                                "expected_application": expected_app_map.get(cmd),
                                "matched_application": app_name,
                                "route": route_info.get("route"),
                                "confidence": route_info.get("confidence"),
                                "resolved_path": resolved_path,
                                "pid": pid,
                                "process_name": stats["process_name"],
                                "verification_method": verification_method,
                                "verification_duration": stats["verification_duration"],
                                "timeout_used": timeout,
                                "parent_pid": pid,
                                "detected_child_pids": detected_child_pids,
                                "final_detected_process": stats["final_detected_process"]
                            })
                            continue
                            
                    elapsed = time.perf_counter() - start_t
                    stats["elapsed_times"].append(elapsed)
                    stats["success_runs"] += 1
                    
                except Exception as e:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": f"Launch exception: {str(e)}",
                        "expected_application": expected_app_map.get(cmd),
                        "matched_application": route_info.get("step", {}).get("input", {}).get("name") if route_info.get("step") else None,
                        "route": route_info.get("route"),
                        "confidence": route_info.get("confidence")
                    })
                    
    return stats
