#!/usr/bin/env python3
"""
Benchmark multiple LLMs on STS2: run each model N times, report average floor reached.

Usage:
  python3 benchmark_llm.py
  python3 benchmark_llm.py --runs 5 --character Ironclad
  python3 benchmark_llm.py --models claude-sonnet-4-6 gpt-4o --runs 3
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from play_llm import STS2Engine, LLMAgent, VALID_CHARACTERS

MODELS = [
    "claude-sonnet-4-6",
    #"claude-opus-4-6",
    "gpt-5.4-2026-03-05",
    "gemini-3-flash-preview",
    "qwen3.6-plus",
    #"deepseek-r1",
    #"gpt-o3",
]


def run_one_game(character: str, seed: str, model: str, log_dir: str) -> dict:
    """Play one game, return result dict. Each run writes a jsonl trace."""
    engine = None
    jsonl_path = os.path.join(log_dir, f"{model}_{character}_{seed}.jsonl")
    jsonl_fh = open(jsonl_path, "w", encoding="utf-8")

    def log_entry(entry: dict):
        jsonl_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        jsonl_fh.flush()

    try:
        engine = STS2Engine(verbose=False, log_dir=log_dir)
        agent = LLMAgent(model=model, verbose=False)

        state = engine.send({"cmd": "start_run", "character": character, "seed": seed})
        log_entry({"type": "start", "model": model, "character": character, "seed": seed})

        step = 0
        max_steps = 500
        stuck_count = 0
        last_state_key = ""

        while step < max_steps:
            step += 1
            decision = state.get("decision", "")

            if state.get("type") == "error":
                log_entry({"type": "error", "step": step, "message": state.get("message", "")})
                state = engine.send({"cmd": "action", "action": "proceed"})
                if state.get("type") == "error":
                    state = engine.send({"cmd": "action", "action": "leave_room"})
                continue

            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player", {})
                ctx = state.get("context", {})
                log_entry({"type": "game_over", "step": step, "victory": victory,
                           "floor": ctx.get("floor", 0), "act": ctx.get("act", 0),
                           "hp": player.get("hp", 0), "max_hp": player.get("max_hp", 0)})
                return {
                    "victory": victory,
                    "floor": ctx.get("floor", 0),
                    "act": ctx.get("act", 0),
                    "hp": player.get("hp", 0),
                    "max_hp": player.get("max_hp", 0),
                    "steps": step,
                    "tokens": agent.total_tokens,
                    "error": None,
                }

            # Stuck detection
            hand_len = len(state.get("hand", []))
            enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
            state_key = f"{decision}:{state.get('round')}:{state.get('player',{}).get('hp')}:{hand_len}:{enemy_hp}"
            if state_key == last_state_key:
                stuck_count += 1
                if stuck_count > 15:
                    log_entry({"type": "stuck", "step": step, "decision": decision})
                    state = engine.send({"cmd": "action", "action": "end_turn"})
                    if state.get("type") == "error":
                        state = engine.send({"cmd": "action", "action": "proceed"})
                    stuck_count = 0
                    continue
            else:
                stuck_count = 0
                last_state_key = state_key

            action_dict, llm_text = agent.decide(state)

            player = state.get("player", {})
            ctx = state.get("context", {})
            log_entry({
                "type": "decision",
                "step": step,
                "decision": decision,
                "act": ctx.get("act"),
                "floor": ctx.get("floor"),
                "hp": player.get("hp"),
                "action": action_dict,
                "llm_response": llm_text,
            })

            cmd = {"cmd": "action", "action": action_dict.get("action", "proceed")}
            args = action_dict.get("args")
            if args:
                cmd["args"] = args
            state = engine.send(cmd)

        log_entry({"type": "timeout", "step": max_steps})
        return {
            "victory": False,
            "floor": state.get("context", {}).get("floor", 0),
            "act": state.get("context", {}).get("act", 0),
            "hp": 0,
            "max_hp": 0,
            "steps": max_steps,
            "tokens": agent.total_tokens,
            "error": "timeout",
        }

    except Exception as e:
        log_entry({"type": "exception", "error": str(e)})
        return {
            "victory": False,
            "floor": 0,
            "act": 0,
            "hp": 0,
            "max_hp": 0,
            "steps": 0,
            "tokens": 0,
            "error": str(e),
        }
    finally:
        jsonl_fh.close()
        if engine:
            engine.close()


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLMs on STS2")
    parser.add_argument("--models", "-m", nargs="+", default=None,
                        help=f"Models to test (default: all). Available: {MODELS}")
    parser.add_argument("--runs", "-n", type=int, default=3, help="Runs per model (default: 3)")
    parser.add_argument("--character", "-c", default="Ironclad", choices=VALID_CHARACTERS)
    parser.add_argument("--seed-prefix", default="bench", help="Seed prefix (seeds: prefix_0, prefix_1, ...)")
    parser.add_argument("--parallel", "-p", type=int, default=5, help="Max parallel games (default: 5)")
    args = parser.parse_args()

    models = args.models or MODELS
    n_runs = args.runs
    character = args.character

    # Setup output dirs
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(base_dir, "logs", f"benchmark_{ts}")
    os.makedirs(log_dir, exist_ok=True)

    results_path = os.path.join(log_dir, "results.json")
    all_results = {}

    print(f"STS2 LLM Benchmark")
    print(f"Character: {character} | Runs per model: {n_runs}")
    print(f"Models: {', '.join(models)}")
    print(f"Log dir: {log_dir}")
    print("=" * 70)

    seeds = [f"{args.seed_prefix}_{i}" for i in range(n_runs)]

    jobs = [(model, seed) for model in models for seed in seeds]
    max_workers = min(len(jobs), args.parallel)

    print(f"Parallel workers: {max_workers} | Total runs: {len(jobs)}")
    print("=" * 70)

    completed = 0

    def run_job(model_seed):
        model, seed = model_seed
        t0 = time.time()
        result = run_one_game(character, seed, model, log_dir)
        result["seed"] = seed
        result["elapsed_sec"] = round(time.time() - t0, 1)
        return model, result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_job, job): job for job in jobs}

        for future in as_completed(futures):
            model, result = future.result()
            completed += 1

            if model not in all_results:
                all_results[model] = []
            all_results[model].append(result)

            status = "WIN" if result["victory"] else f"Floor {result['floor']}"
            if result["error"]:
                status += f" (err: {result['error'][:30]})"
            print(f"  [{completed}/{len(jobs)}] {model:<25} seed={result['seed']} -> {status} | {result['elapsed_sec']:.0f}s | {result['tokens']} tokens")

            # Save intermediate results
            with open(results_path, "w") as f:
                json.dump({"character": character, "runs": n_runs, "seeds": seeds,
                           "results": all_results}, f, indent=2, ensure_ascii=False)

    # Print summary table
    print(f"\n{'=' * 70}")
    print(f"SUMMARY — {character}, {n_runs} runs per model")
    print(f"{'=' * 70}")
    print(f"{'Model':<25} {'Avg Floor':>10} {'Max Floor':>10} {'Wins':>6} {'Avg Tokens':>12}")
    print(f"{'─' * 70}")

    for model in models:
        runs = all_results.get(model, [])
        if not runs:
            print(f"{model:<25} {'(no data)':>10}")
            continue
        floors = [r["floor"] for r in runs]
        wins = sum(1 for r in runs if r["victory"])
        tokens = [r["tokens"] for r in runs]
        avg_floor = sum(floors) / len(floors)
        max_floor = max(floors)
        avg_tokens = sum(tokens) / len(tokens)
        print(f"{model:<25} {avg_floor:>10.1f} {max_floor:>10} {wins:>6} {avg_tokens:>12.0f}")

    print(f"\nResults saved: {results_path}")


if __name__ == "__main__":
    main()
