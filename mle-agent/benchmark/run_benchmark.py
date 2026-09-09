import sys
import os
import json
import time
import argparse
import statistics
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List

# Ensure parent directory is in python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from benchmark.sample_prompts import BENCHMARK_PROMPTS

def check_server_reachability(server_url: str) -> bool:
    """Checks if the local llama-server is online and responding."""
    health_url = f"{server_url.rstrip('/')}/models"
    try:
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False

def benchmark_llm_call(server_url: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Measures latency, output token count, TTFT, and tokens/sec for a single LLM call."""
    endpoint = f"{server_url.rstrip('/')}/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            t_first_token = time.time()
            res_body = json.loads(resp.read().decode("utf-8"))
            t_end = time.time()

        usage = res_body.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        
        # If server usage object doesn't provide token counts, estimate from content length
        if completion_tokens == 0 and "choices" in res_body:
            content = res_body["choices"][0]["message"]["content"]
            completion_tokens = max(1, len(content.split()))

        total_time = t_end - t0
        ttft = t_first_token - t0
        tok_per_sec = completion_tokens / total_time if total_time > 0 else 0.0

        return {
            "wall_time": total_time,
            "ttft": ttft,
            "completion_tokens": completion_tokens,
            "tok_per_sec": tok_per_sec,
            "success": True
        }
    except Exception as e:
        return {
            "wall_time": time.time() - t0,
            "ttft": 0.0,
            "completion_tokens": 0,
            "tok_per_sec": 0.0,
            "success": False,
            "error": str(e)
        }

def run_synthetic_benchmark(reps: int) -> Dict[str, Any]:
    """Generates synthetic benchmark numbers for testing without live llama-server."""
    results = {}
    for prompt_info in BENCHMARK_PROMPTS:
        role = prompt_info["role"]
        tok_speed = 18.5 + (hash(role) % 5)
        call_times = [2.5 + (i * 0.1) for i in range(reps)]
        results[role] = {
            "reps": reps,
            "mean_wall_time_sec": round(statistics.mean(call_times), 3),
            "median_wall_time_sec": round(statistics.median(call_times), 3),
            "std_wall_time_sec": round(statistics.stdev(call_times) if reps > 1 else 0.0, 3),
            "mean_tok_per_sec": round(tok_speed, 2),
            "mean_completion_tokens": 350
        }
    return results

def main():
    parser = argparse.ArgumentParser(description="MLE Agent Standalone Benchmarking Harness")
    parser.add_argument("--reps", type=int, default=5, help="Number of repetitions per prompt (default: 5)")
    parser.add_argument("--mock-server", action="store_true", help="Run benchmark in mock/synthetic mode")
    args = parser.parse_args()

    settings = get_settings()
    server_url = settings.model.server_url

    print("==================================================")
    print("      MLE Agent Inference Benchmark Harness      ")
    print("==================================================")
    print(f"Target Server Endpoint: {server_url}")
    print(f"Repetitions per Prompt: {args.reps}")

    if not args.mock_server and not check_server_reachability(server_url):
        print(f"\n[BENCHMARK ERROR] Could not connect to llama-server at '{server_url}'.")
        print("Please start the server first using:")
        print("   export LOCAL_MODEL_PATH=\"/path/to/qwen2.5-coder-32b-instruct-q4_k_m.gguf\"")
        print("   bash model_server/launch_llama_server.sh")
        print("\nOr run with --mock-server flag for offline testing.")
        sys.exit(1)

    print("\nStarting prompt throughput benchmark...")
    role_results = {}

    if args.mock_server:
        print("[Notice] Executing in mock benchmark mode...")
        role_results = run_synthetic_benchmark(args.reps)
    else:
        for prompt_info in BENCHMARK_PROMPTS:
            role = prompt_info["role"]
            print(f"\nBenchmarking Agent Role: [{role.upper()}] ...")
            wall_times = []
            ttfts = []
            tokens_list = []
            tok_speeds = []

            for i in range(args.reps):
                res = benchmark_llm_call(server_url, prompt_info["system"], prompt_info["user"])
                if res["success"]:
                    wall_times.append(res["wall_time"])
                    ttfts.append(res["ttft"])
                    tokens_list.append(res["completion_tokens"])
                    tok_speeds.append(res["tok_per_sec"])
                    print(f"  Rep {i+1}/{args.reps}: {res['wall_time']:.2f}s | {res['completion_tokens']} tok | {res['tok_per_sec']:.2f} tok/s")
                else:
                    print(f"  Rep {i+1}/{args.reps}: FAILED ({res.get('error')})")

            if wall_times:
                role_results[role] = {
                    "reps": len(wall_times),
                    "mean_wall_time_sec": round(statistics.mean(wall_times), 3),
                    "median_wall_time_sec": round(statistics.median(wall_times), 3),
                    "std_wall_time_sec": round(statistics.stdev(wall_times) if len(wall_times) > 1 else 0.0, 3),
                    "mean_ttft_sec": round(statistics.mean(ttfts), 3),
                    "mean_tok_per_sec": round(statistics.mean(tok_speeds), 2),
                    "mean_completion_tokens": round(statistics.mean(tokens_list), 1)
                }

    # Output Console Summary Table
    print("\n==================================================")
    print("             Benchmark Summary Results            ")
    print("==================================================")
    print(f"{'Role':<15} | {'Mean Time (s)':<13} | {'Tok/s':<8} | {'Tokens':<8}")
    print("-" * 55)

    all_tok_speeds = []
    coder_mean_time = 30.0

    for role, metrics in role_results.items():
        print(f"{role:<15} | {metrics['mean_wall_time_sec']:<13} | {metrics['mean_tok_per_sec']:<8} | {metrics['mean_completion_tokens']:<8}")
        all_tok_speeds.append(metrics['mean_tok_per_sec'])
        if role == "coder":
            coder_mean_time = metrics['mean_wall_time_sec']

    avg_tok_s = statistics.mean(all_tok_speeds) if all_tok_speeds else 15.0

    # Save timestamped JSON
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_file = results_dir / f"benchmark_{timestamp}.json"

    benchmark_data = {
        "timestamp": timestamp,
        "server_url": server_url,
        "mock_mode": args.mock_server,
        "results": role_results
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)

    print(f"\nResults written to: {out_file}")

    # Config recommendation summary block
    est_actions = settings.budget.actions_total
    est_total_mins = round((est_actions * coder_mean_time * 1.5) / 60.0, 1)

    print("\n==================================================")
    print("        Suggested Settings.yaml Budget Config      ")
    print("==================================================")
    print(f"Measured average model throughput: ~{avg_tok_s:.1f} tok/s")
    print(f"Measured average Coder step latency: ~{coder_mean_time:.1f}s")
    print("Based on these measured speeds, recommended settings.yaml values:")
    print("budget:")
    print(f"  actions_total: {est_actions}")
    print(f"  time_total_minutes: {est_total_mins}")
    print("==================================================")

if __name__ == "__main__":
    main()
