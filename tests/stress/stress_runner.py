# -*- coding: utf-8 -*-
import argparse
import time
import json
import os
import sys
import traceback
import uuid

# Add parent directory to path so imports work cleanly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.stress.performance_monitor import PerformanceMonitor
from tests.stress.router_stress import run_router_stress, ROUTER_ACCURACY_MAP
from tests.stress.mini_planner_stress import run_mini_planner_stress
from tests.stress.planner_v2_stress import run_planner_v2_stress
from tests.stress.chaos_test import run_chaos_tests
from tests.stress.launch_stress import run_launch_stress
from ai.engine import RequestContext

def parse_args():
    parser = argparse.ArgumentParser(description="Jarvis Stress Test Runner")
    parser.add_argument("--hours", type=float, help="Duration of stress test in hours")
    parser.add_argument("--iterations", type=int, help="Number of test iterations")
    parser.add_argument("--profile", type=str, choices=["smoke", "short", "medium", "long", "launch"], help="Predefined test profile")
    parser.add_argument("--real-run", action="store_true", help="fysicky spouštět aplikace na ploše (dry_run=False)")
    parser.add_argument("--verify-launch", action="store_true", help="Ověřit reálné spuštění aplikací (Phase 3.1)")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Predefined profile resolution
    iterations = None
    hours = None
    profile_name = "custom"
    
    if args.profile:
        profile_name = args.profile
        if args.profile == "smoke":
            iterations = 10
        elif args.profile == "short":
            iterations = 100
        elif args.profile == "medium":
            iterations = 1000
        elif args.profile == "long":
            hours = 12.0
        elif args.profile == "launch":
            iterations = 5
    else:
        if args.hours is not None:
            hours = args.hours
        elif args.iterations is not None:
            iterations = args.iterations
        else:
            # Default to smoke if nothing specified
            profile_name = "smoke"
            iterations = 10
            
    dry_run = not args.real_run
    verify_launch = args.verify_launch or (profile_name == "launch")
    
    print(f"=== JARVIS STRESS RUNNER STARTED ===")
    print(f"Profile: {profile_name.upper()}")
    if iterations:
        print(f"Target: {iterations} iterations")
    else:
        print(f"Target: {hours} hours")
    print(f"Mode: {'REAL RUN' if not dry_run else 'DRY RUN (Safe)'}")
    
    # Initialize files and performance monitor
    perf_log_path = "logs/performance_log.json"
    report_path = "logs/stress_report.json"
    failure_path = "logs/failure_summary.json"
    crash_dir = "logs/crashes"
    os.makedirs(crash_dir, exist_ok=True)
    
    # Clean old logs
    for p in [perf_log_path, report_path, failure_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
                
    perf_mon = PerformanceMonitor(log_path=perf_log_path, interval=10) # 10s interval for test speed
    perf_mon.start()
    
    start_time = time.time()
    initial_ram = perf_mon.get_process_ram()
    
    # Running statistics
    total_commands = 0
    success_commands = 0
    failed_commands = 0
    ollama_calls = 0
    ollama_calls_prevented = 0
    router_failures = 0
    planner_failures = 0
    memory_warnings = 0
    crashes = 0
    ollama_leaks = 0
    
    expected_application = None
    matched_application = None
    route = None
    confidence = None
    resolved_path = None
    pid = None
    process_name = None
    verification_method = None
    verification_duration = None
    timeout_used = None
    parent_pid = None
    detected_child_pids = []
    final_detected_process = None
    
    fast_times = []
    accuracy_runs = 0
    accuracy_success = 0
    last_failed_commands = []
    
    # Failure category counts
    failure_counts = {}
    
    def log_failure(category, command=None, expected=None, actual=None, reason=None,
                    expected_application=None, matched_application=None, route=None, confidence=None):
        failure_counts[category] = failure_counts.get(category, 0) + 1
        entry = {"command": command, "reason": reason}
        if expected:
            entry["expected"] = expected
        if actual:
            entry["actual"] = actual
        if expected_application is not None:
            entry["expected_application"] = expected_application
        if matched_application is not None:
            entry["matched_application"] = matched_application
        if route is not None:
            entry["route"] = route
        if confidence is not None:
            entry["confidence"] = confidence
        last_failed_commands.append(entry)

    def write_crash_log(cmd, err, tb):
        nonlocal crashes
        crashes += 1
        crash_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_command": cmd,
            "error": str(err),
            "stack_trace": tb,
            "request_id": f"stress_{uuid.uuid4().hex[:8]}"
        }
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(crash_dir, f"crash_{timestamp}_{crashes}.json")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(crash_data, f, indent=4, ensure_ascii=False)
        except Exception as ex:
            print(f"Failed to write crash log: {ex}")
            
    # Main execution loop
    current_iter = 0
    loop_duration = hours * 3600 if hours else None
    
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        if loop_duration and elapsed >= loop_duration:
            break
        if iterations and current_iter >= iterations:
            break
            
        current_iter += 1
        if iterations:
            print(f"Iteration {current_iter}/{iterations} ({elapsed:.1f}s elapsed)...")
        else:
            print(f"Running iteration {current_iter} (elapsed {elapsed:.1f}s / {loop_duration:.1f}s)...")
            
        if profile_name == "launch":
            try:
                l_stats = run_launch_stress(num_iterations=1, verify_launch=verify_launch, dry_run=dry_run)
                total_commands += l_stats["total_runs"]
                success_commands += l_stats["success_runs"]
                failed_commands += l_stats["failed_runs"]
                fast_times.extend(l_stats["elapsed_times"])
                
                expected_application = l_stats.get("expected_application")
                matched_application = l_stats.get("matched_application")
                route = l_stats.get("route")
                confidence = l_stats.get("confidence")
                resolved_path = l_stats.get("resolved_path")
                pid = l_stats.get("pid")
                process_name = l_stats.get("process_name")
                verification_method = l_stats.get("verification_method")
                verification_duration = l_stats.get("verification_duration")
                timeout_used = l_stats.get("timeout_used")
                parent_pid = l_stats.get("parent_pid")
                detected_child_pids = l_stats.get("detected_child_pids")
                final_detected_process = l_stats.get("final_detected_process")
                
                for fail in l_stats["failures_details"]:
                    log_failure(
                        "launch_failure", 
                        command=fail["command"], 
                        reason=fail["reason"],
                        expected_application=fail.get("expected_application"),
                        matched_application=fail.get("matched_application"),
                        route=fail.get("route"),
                        confidence=fail.get("confidence")
                    )
            except Exception as e:
                failed_commands += 1
                log_failure("launch_crash", reason=str(e))
                write_crash_log("launch_stress_run", e, traceback.format_exc())
        else:
            # 1. Run Router Stress Tests
            try:
                r_stats = run_router_stress(num_iterations=1)
                total_commands += r_stats["total_runs"]
                success_commands += r_stats["success_runs"]
                failed_commands += r_stats["failed_runs"]
                ollama_leaks += r_stats["ollama_leaks"]
                fast_times.extend(r_stats["elapsed_times"])
                accuracy_runs += r_stats["accuracy_runs"]
                accuracy_success += r_stats["accuracy_success"]
                
                for fail in r_stats["failures_details"]:
                    reason = fail.get("reason", "unknown")
                    if "ollama_leak" in reason:
                        log_failure("ollama_leak", command=fail["command"], reason="FAST_COMMAND triggered Ollama")
                    elif "wrong_routing_level" in reason:
                        router_failures += 1
                        log_failure("wrong_routing_level", command=fail["command"], reason=reason)
                    elif "wrong application match" in reason:
                        log_failure("wrong_app_match", command=fail["command"], expected=fail.get("expected"), actual=fail.get("actual"), reason=reason)
                    else:
                        log_failure("router_error", command=fail["command"], reason=reason)
                        
                ollama_calls_prevented += r_stats["success_runs"]
                
            except Exception as e:
                router_failures += 1
                log_failure("router_crash", reason=str(e))
                write_crash_log("router_stress_run", e, traceback.format_exc())
                
            # 2. Run Mini Planner Stress
            try:
                m_stats = run_mini_planner_stress(num_iterations=1)
                total_commands += m_stats["total_runs"]
                success_commands += m_stats["success_runs"]
                failed_commands += m_stats["failed_runs"]
                ollama_calls += m_stats["ollama_calls"]
                
                for fail in m_stats["failures_details"]:
                    reason = fail.get("reason", "unknown")
                    if "wrong_routing_level" in reason:
                        log_failure("wrong_routing_level", command=fail["command"], reason=reason)
                    else:
                        planner_failures += 1
                        log_failure("mini_planner_failure", command=fail["command"], reason=reason)
                        
            except Exception as e:
                planner_failures += 1
                log_failure("mini_planner_crash", reason=str(e))
                write_crash_log("mini_planner_run", e, traceback.format_exc())
                
            # 3. Run Planner V2 Stress
            try:
                p_stats = run_planner_v2_stress(num_iterations=1)
                total_commands += p_stats["total_runs"]
                success_commands += p_stats["success_runs"]
                failed_commands += p_stats["failed_runs"]
                ollama_calls += p_stats["ollama_calls"]
                
                for fail in p_stats["failures_details"]:
                    reason = fail.get("reason", "unknown")
                    if "wrong_routing_level" in reason:
                        log_failure("wrong_routing_level", command=fail["command"], reason=reason)
                    else:
                        planner_failures += 1
                        log_failure("planner_v2_failure", command=fail["command"], reason=reason)
                        
            except Exception as e:
                planner_failures += 1
                log_failure("planner_v2_crash", reason=str(e))
                write_crash_log("planner_v2_run", e, traceback.format_exc())
                
            # 4. Run Chaos Test
            try:
                c_stats = run_chaos_tests()
                for fail in c_stats["failures_details"]:
                    log_failure("chaos_scenario_failed", command=fail["chaos_scenario"], reason=fail["reason"])
                    failed_commands += 1
                    
                success_commands += c_stats["success_runs"]
                total_commands += c_stats["total_chaos_runs"]
            except Exception as e:
                log_failure("chaos_framework_crash", reason=str(e))
                write_crash_log("chaos_test_run", e, traceback.format_exc())
            
        # 5. Monitor Memory Leaks
        current_ram = perf_mon.get_process_ram()
        ram_growth = current_ram - initial_ram
        if ram_growth > 50.0:
            memory_warnings += 1
            print(f"[WARNING]\nPossible memory leak detected\n\nRAM growth:\n+{ram_growth:.2f} MB\n")
            
        active_rc = RequestContext.get_active_count()
        if active_rc > 10:
            memory_warnings += 1
            print(f"[WARNING]\nPossible memory leak detected (RequestContext)\n\nActive contexts:\n{active_rc}\n")
            
        time.sleep(0.5)

    perf_mon.stop()
    
    # Calculate stats
    duration_hours = elapsed / 3600.0
    success_rate = (success_commands / total_commands * 100.0) if total_commands > 0 else 0.0
    
    avg_fast_time = (sum(fast_times) / len(fast_times)) if fast_times else 0.0
    min_fast_time = min(fast_times) if fast_times else 0.0
    max_fast_time = max(fast_times) if fast_times else 0.0
    
    if avg_fast_time > 0.5:
        print(f"[WARNING]\nFast command performance degradation detected\n\nAverage fast command time:\n{avg_fast_time:.3f}s (Threshold: 0.500s)\n")
        
    router_accuracy = (accuracy_success / accuracy_runs * 100.0) if accuracy_runs > 0 else 100.0
    
    # Generate reports
    report_data = {
        "duration_hours": round(duration_hours, 3),
        "total_commands": total_commands,
        "success_rate": round(success_rate, 2),
        "failed_commands": failed_commands,
        "ollama_calls": ollama_calls,
        "ollama_calls_prevented": ollama_calls_prevented,
        "router_failures": router_failures,
        "planner_failures": planner_failures,
        "launch_failures": failure_counts.get("launch_failure", 0) + failure_counts.get("launch_crash", 0),
        "memory_warnings": memory_warnings,
        "crashes": crashes,
        "avg_fast_time": round(avg_fast_time, 3),
        "min_fast_time": round(min_fast_time, 3),
        "max_fast_time": round(max_fast_time, 3),
        "router_accuracy": round(router_accuracy, 2),
        "ollama_leaks": ollama_leaks,
        "expected_application": expected_application,
        "matched_application": matched_application,
        "route": route,
        "confidence": confidence,
        "resolved_path": resolved_path,
        "pid": pid,
        "process_name": process_name,
        "verification_method": verification_method,
        "verification_duration": verification_duration,
        "timeout_used": timeout_used,
        "parent_pid": parent_pid,
        "detected_child_pids": detected_child_pids,
        "final_detected_process": final_detected_process,
        "last_failed_commands": last_failed_commands[:50]
    }
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False)
        print(f"Stress report successfully written to {report_path}")
    except Exception as e:
        print(f"Error saving report: {e}")
        
    try:
        with open(failure_path, "w", encoding="utf-8") as f:
            json.dump(failure_counts, f, indent=4, ensure_ascii=False)
        print(f"Failure summary successfully written to {failure_path}")
    except Exception as e:
        print(f"Error saving failure summary: {e}")
        
    # Console output summary
    print(f"\n======================================")
    print(f"=== STRESS TEST COMPLETED SUMMARY ===")
    print(f"======================================")
    print(f"Duration: {duration_hours:.3f} hours")
    print(f"Total Commands Executed: {total_commands}")
    print(f"Success Rate: {success_rate:.2f}%")
    print(f"Failed Commands: {failed_commands}")
    if profile_name == "launch":
        print(f"Launch Failures: {failure_counts.get('launch_failure', 0) + failure_counts.get('launch_crash', 0)}")
    else:
        print(f"Ollama calls: {ollama_calls}")
        print(f"Ollama calls prevented: {ollama_calls_prevented}")
        print(f"Router Failures: {router_failures}")
        print(f"Planner Failures: {planner_failures}")
    print(f"Memory Warnings: {memory_warnings}")
    print(f"Crashes detected: {crashes}")
    if profile_name != "launch":
        print(f"Router App Match Accuracy: {router_accuracy:.2f}%")
        print(f"Ollama leaks: {ollama_leaks}")
    print(f"Benchmark: Fast times avg={avg_fast_time:.3f}s (min={min_fast_time:.3f}s, max={max_fast_time:.3f}s)")
    print(f"======================================")

if __name__ == "__main__":
    main()
