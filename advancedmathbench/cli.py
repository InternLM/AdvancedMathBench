"""Sequential CLI. One saved record per generated proof or benchmark proof."""
import argparse
import json
import os
from pathlib import Path

from . import __version__
from .backends import BackendError, make_backend, validate_config
from .data import canonical, load_data, sha256, write_json
from .metrics import summarize
from .protocol import (LEVEL_SCORES, PROMPTS, extract_steps, meta_prompt, parse_level,
                       parse_verdict, response_error, strip_thinking, verifier_prompt)


def call(backend, prompt):
    try:
        return backend.complete(prompt)
    except BackendError as exc:
        return {"text": "", "finish_reason": None, "error": str(exc)}


def evaluate(row, task, backends, templates, repeats, use_reference, sample_index):
    result = {"problem_id": row["problem_id"], "domain": row["domain"], "subject": row["subject"],
              "sample_index": sample_index, "problem": row["problem"], "verifier_trials": [], "inputs": {}}
    if task == "prover":
        prompt = templates["generation"].format(problem=row["problem"])
        result["inputs"]["policy_prompt"] = prompt
        response = call(backends["policy"], prompt)
        steps = extract_steps(strip_thinking(response["text"]))
        error = response_error(response)
        if not error and not steps:
            error = "no_proof_steps"
        result.update(policy_response=response, steps=steps, generation_error=error)
        if error:
            return result
    else:
        steps = row["steps"]
        result.update(proof_id=row["proof_id"], steps=steps, is_correct=row["is_correct"],
                      first_error_step=row["first_error_step"])
    prompt = verifier_prompt(templates["verifier"], row, steps, use_reference)
    result["inputs"]["verifier_prompt"] = prompt
    for index in range(repeats):
        response = call(backends["verifier"], prompt)
        trial = {"index": index, "response": response, "parsed": None,
                 "error": response_error(response), "valid": False}
        if not trial["error"]:
            try:
                trial["parsed"] = parse_verdict(response["text"], len(steps))
                trial["valid"] = True
            except ValueError as exc:
                trial["error"] = str(exc)
        if task == "verifier" and "meta" in backends:
            trial["meta"] = {"valid": False, "score": 0.0, "error": "verifier_invalid", "response": None}
            if trial["valid"]:
                m_prompt = meta_prompt(templates["meta"], row, trial["parsed"], use_reference)
                m_resp = call(backends["meta"], m_prompt)
                m = {"valid": False, "score": 0.0, "error": response_error(m_resp),
                     "response": m_resp, "prompt": m_prompt}
                if not m["error"]:
                    try:
                        level = parse_level(m_resp["text"])
                        m.update(valid=True, level=level, score=LEVEL_SCORES[level])
                    except ValueError as exc:
                        m["error"] = str(exc)
                trial["meta"] = m
        result["verifier_trials"].append(trial)
        print(f"  verifier pass {index + 1}/{repeats}: {'valid' if trial['valid'] else 'invalid'}", flush=True)
    return result


def parser():
    root = argparse.ArgumentParser(description="AdvancedMathBench: simple, standalone sequential evaluation")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="task", required=True)
    for task in ("prover", "verifier"):
        cmd = sub.add_parser(task)
        cmd.add_argument("--data", type=Path, required=True, help="Local benchmark JSONL")
        cmd.add_argument("--config", type=Path, required=True, help="Backend JSON config; no API keys")
        cmd.add_argument("--output", type=Path, required=True)
        cmd.add_argument("--domain", choices=["all", "ugd", "qe"], default="all")
        cmd.add_argument("--limit", type=int, help="Only the first N selected rows; for smoke tests")
        cmd.add_argument("--verifier-repeats", type=int, default=8 if task == "prover" else 1)
        cmd.add_argument("--use-reference-solution", action=argparse.BooleanOptionalAction, default=task == "prover")
        cmd.add_argument("--verifier-prompt", type=Path, default=PROMPTS / "proof_verifier.md")
        cmd.add_argument("--resume", action="store_true", help="Continue this exact data/config/protocol run")
        cmd.add_argument("--dry-run", action="store_true", help="Validate and print call budget without model/API calls or output writes")
        if task == "prover":
            cmd.add_argument("--samples", type=int, default=1, help="Independent proof samples per problem")
            cmd.add_argument("--generation-prompt", type=Path, default=PROMPTS / "proof_generation_zh_v2.md")
        else:
            cmd.add_argument("--meta", action="store_true", help="Also grade verifier explanations using an independent meta model")
            cmd.add_argument("--meta-prompt", type=Path, default=PROMPTS / "meta_verification_v3_w_gt.md")
    return root


def export(output, manifest, rows, records):
    settings = manifest["settings"]
    summary = summarize(manifest["task"], rows, records, settings["samples"],
                        settings["verifier_repeats"], settings["meta"])
    summary["run_id"] = manifest["run_id"]
    write_json(output / "summary.json", summary)
    tmp = output / "results.jsonl.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    tmp.replace(output / "results.jsonl")
    return summary


def run(args, backend_factory=make_backend):
    samples = getattr(args, "samples", 1)
    with_meta = getattr(args, "meta", False)
    if samples < 1 or args.verifier_repeats < 1 or (args.limit is not None and args.limit < 1):
        raise ValueError("samples, verifier-repeats, and limit must be positive")
    rows = load_data(args.data, args.task)
    source_rows = len(rows)
    rows = [r for r in rows if args.domain == "all" or r["domain"] == args.domain]
    rows = rows[:args.limit] if args.limit else rows
    if not rows:
        raise ValueError("No rows remain after selection")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) - {"policy", "verifier", "meta"}:
        raise ValueError("Config contains only policy, verifier, and optional meta sections")
    for spec in config.values():
        if not isinstance(spec, dict):
            raise ValueError("Each backend section must be an object")
        validate_config(spec)
    roles = ["verifier"] + (["policy"] if args.task == "prover" else []) + (["meta"] if with_meta else [])
    if any(role not in config for role in roles):
        raise ValueError(f"Config requires backend sections: {roles}")
    config = {role: config[role] for role in roles}
    templates = {"verifier": args.verifier_prompt.read_text(encoding="utf-8")}
    if args.task == "prover":
        templates["generation"] = args.generation_prompt.read_text(encoding="utf-8")
        templates["generation"].format(problem="FORMAT_CHECK")
    if with_meta:
        templates["meta"] = args.meta_prompt.read_text(encoding="utf-8")
    verifier_prompt(templates["verifier"], rows[0], ["FORMAT_CHECK"], args.use_reference_solution)
    manifest = {"evaluator_version": __version__, "protocol": "basic-v1", "task": args.task,
                "data_sha256": sha256(args.data.read_bytes()), "source_rows": source_rows, "selected_rows": len(rows),
                "config": config, "settings": {"samples": samples, "verifier_repeats": args.verifier_repeats,
                    "meta": with_meta, "domain": args.domain, "limit": args.limit,
                    "use_reference_solution": args.use_reference_solution},
                "prompt_sha256": {k: sha256(v.encode()) for k, v in templates.items()},
                "code_sha256": sha256(b"".join(p.name.encode() + p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))),
                "output_policy": "invalid output = zero credit, fixed denominator; finish_reason must be stop"}
    manifest["run_id"] = sha256(canonical(manifest).encode())
    budget = {"selected_rows": len(rows), "policy_calls": len(rows) * samples if args.task == "prover" else 0,
              "verifier_calls_max": len(rows) * samples * args.verifier_repeats,
              "meta_calls_max": len(rows) * args.verifier_repeats if with_meta else 0,
              "note": "Excludes transport retries; failed generation skips its verifier calls"}
    if args.dry_run:
        print(json.dumps({"dry_run": True, "task": args.task, "budget": budget, "settings": manifest["settings"]}, indent=2))
        return
    output = args.output
    previous = output / "manifest.json"
    if previous.exists():
        if not args.resume:
            raise ValueError("Output exists. Use --resume for the identical run, or choose a new directory")
        if json.loads(previous.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Resume rejected: data, config, prompts, or evaluator code changed")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty and has no matching manifest")
    # Check all API-key environment variables before making any paid requests.
    backends = {role: backend_factory(spec) for role, spec in config.items()}
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".running.lock"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("Run lock exists. Ensure no process is active before removing .running.lock") from None
    os.close(fd)
    records = []
    try:
        write_json(previous, manifest)
        write_json(output / "call_budget.json", budget)
        (output / "records").mkdir(exist_ok=True)
        expected = {f"{i:06d}_{s:03d}.json" for i in range(len(rows)) for s in range(samples)}
        extra = {p.name for p in (output / "records").glob("*.json")} - expected
        if extra:
            raise ValueError("Unexpected records in output; do not mix runs")
        pending = []
        # Read ALL committed records first, so interruption cannot hide later cached records.
        for i, row in enumerate(rows):
            for s in range(samples):
                path = output / "records" / f"{i:06d}_{s:03d}.json"
                if path.exists():
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    if saved.get("run_id") != manifest["run_id"] or saved.get("record_key") != path.stem:
                        raise ValueError("Saved record does not match this run")
                    records.append(saved)
                else:
                    pending.append((i, s, row, path))
        export(output, manifest, rows, sorted(records, key=lambda r: r["record_key"]))
        for i, s, row, path in pending:
            print(f"{args.task}: row {i + 1}/{len(rows)}, sample {s + 1}/{samples}", flush=True)
            result = evaluate(row, args.task, backends, templates, args.verifier_repeats,
                              args.use_reference_solution, s)
            if args.task == "prover":
                trials = result["verifier_trials"]
                result["pessimistic_correct"] = len(trials) == args.verifier_repeats and all(
                    t["valid"] and t["parsed"]["first_error_step"] == -1 for t in trials)
            result.update(run_id=manifest["run_id"], record_key=path.stem,
                          policy=config.get("policy", {}).get("model"), verifier=config["verifier"]["model"])
            write_json(path, result)
            records.append(result)
            export(output, manifest, rows, sorted(records, key=lambda r: r["record_key"]))
        summary = export(output, manifest, rows, sorted(records, key=lambda r: r["record_key"]))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        lock.unlink()


def main():
    args = parser().parse_args()
    try:
        run(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise SystemExit(f"Error: {exc}") from None
    except KeyboardInterrupt:
        raise SystemExit("Interrupted. Completed records are saved; rerun the same command with --resume.") from None
