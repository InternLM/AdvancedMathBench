"""Local JSONL input, validation, and atomic JSON output. Standard library only."""
import hashlib
import json
from pathlib import Path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_steps(steps):
    if not isinstance(steps, list) or not steps or any(not isinstance(s, str) or not s.strip() for s in steps):
        raise ValueError("steps must be a nonempty list of nonempty strings")


def ground_truth(annotation, steps):
    if not isinstance(annotation, dict):
        raise ValueError("annotation must be an object")
    fatal = annotation["first_fatal_error_step"]
    rec = annotation["recoverable_error_steps"]
    if not isinstance(rec, list) or not rec or (-1 in rec and rec != [-1]):
        raise ValueError("recoverable_error_steps must be [-1] or nonnegative indices")
    labels = [fatal, *rec]
    if any(type(i) is not int or not -1 <= i < len(steps) for i in labels):
        raise ValueError("human step labels must be zero-indexed and in range, or -1")
    errors = [i for i in labels if i >= 0]
    return fatal == -1 and rec == [-1], min(errors) if errors else -1


def load_data(path, task):
    rows, seen, problems = [], set(), {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            problem = raw["problem"]
            if not isinstance(problem, str) or not problem.strip():
                raise ValueError("problem must be a nonempty string")
            if raw["domain"] not in ("ugd", "qe"):
                raise ValueError("domain must be ugd or qe")
            pid = raw.get("problem_id", "amb-p-" + sha256(problem.encode())[:16])
            ref = raw.get("reference_solution", raw.get("solution", ""))
            if not isinstance(pid, str) or not pid or not isinstance(ref, str):
                raise ValueError("problem_id and reference_solution must be strings")
            if pid in problems and problems[pid] != problem:
                raise ValueError("one problem_id maps to different problem texts")
            problems[pid] = problem
            row = {"problem_id": pid, "problem": problem, "reference_solution": ref,
                   "domain": raw["domain"], "subject": raw.get("subject", "")}
            key = pid
            if task == "verifier":
                steps = raw["steps"]
                validate_steps(steps)
                annotation = raw.get("annotation", raw)
                correct, first = ground_truth(annotation, steps)
                if not isinstance(annotation.get("reviewer_comment", ""), str):
                    raise ValueError("reviewer_comment must be text")
                if "is_correct" in raw and (type(raw["is_correct"]) is not bool or raw["is_correct"] != correct):
                    raise ValueError("is_correct conflicts with human annotation")
                if "first_error_step" in raw and (type(raw["first_error_step"]) is not int or raw["first_error_step"] != first):
                    raise ValueError("first_error_step conflicts with human annotation")
                proof_id = raw.get("proof_id", "amb-v-" + sha256(
                    json.dumps([pid, steps], ensure_ascii=False, separators=(",", ":")).encode())[:16])
                if not isinstance(proof_id, str) or not proof_id:
                    raise ValueError("proof_id must be a nonempty string")
                row.update(proof_id=proof_id, steps=steps, is_correct=correct, first_error_step=first,
                           annotation={k: annotation.get(k, "") for k in (
                               "first_fatal_error_step", "recoverable_error_steps", "reviewer_comment",
                               "first_error_reason", "remark")})
                key = proof_id
            if key in seen:
                raise ValueError("duplicate problem_id (prover) or proof_id (verifier)")
            seen.add(key)
            rows.append(row)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid dataset row {line_no}: {exc}") from exc
    if not rows:
        raise ValueError("Dataset is empty")
    return rows
