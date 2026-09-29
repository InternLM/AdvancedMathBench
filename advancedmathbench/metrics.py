"""Scores in [0, 1]. Invalid outputs earn no credit; no rows are silently dropped."""
from collections import defaultdict


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def harmonic(tpr, tnr):
    if tpr is None or tnr is None:
        return None
    return 2 * tpr * tnr / (tpr + tnr) if tpr + tnr else 0.0


def prover_metrics(records, repeats):
    grouped = defaultdict(list)
    for record in records:
        passes = record["verifier_trials"]
        correct = len(passes) == repeats and all(p["valid"] and p["parsed"]["first_error_step"] == -1 for p in passes)
        grouped[record["problem_id"]].append(int(correct))
    return {
        "problems": len(grouped), "proofs": len(records),
        "pessimistic": mean(mean(v) for v in grouped.values()),
        "pass_any_sample": mean(max(v) for v in grouped.values()),
        "generation_failure_rate": mean(bool(r["generation_error"]) for r in records),
        "verifier_valid_rate": sum(t["valid"] for r in records for t in r["verifier_trials"]) / (len(records) * repeats),
    }


def verifier_metrics(records, repeats, with_meta):
    per_proof = []
    for record in records:
        trials = record["verifier_trials"]
        truth = record["is_correct"]
        rough = sum(t["valid"] and ((t["parsed"]["first_error_step"] == -1) == truth) for t in trials) / repeats
        precise = sum(t["valid"] and t["parsed"]["first_error_step"] == record["first_error_step"] for t in trials) / repeats
        meta = sum(t["meta"]["score"] if t.get("meta") and t["meta"]["valid"] else 0.0 for t in trials) / repeats
        per_proof.append({"truth": truth, "rough": rough, "precise": precise, "meta": meta})
    positive = [r for r in per_proof if r["truth"]]
    negative = [r for r in per_proof if not r["truth"]]
    tpr, tnr = mean(r["rough"] for r in positive), mean(r["rough"] for r in negative)
    result = {
        "proofs": len(records), "correct_proofs": len(positive), "incorrect_proofs": len(negative),
        "rough_accuracy": mean(r["rough"] for r in per_proof),
        "rough_tpr": tpr, "rough_tnr": tnr, "rough_bal_f1": harmonic(tpr, tnr),
        "balanced_accuracy": (tpr + tnr) / 2 if tpr is not None and tnr is not None else None,
        "first_error_step_accuracy": mean(r["precise"] for r in per_proof),
        "first_error_step_accuracy_incorrect": mean(r["precise"] for r in negative),
        "verifier_valid_rate": sum(t["valid"] for r in records for t in r["verifier_trials"]) / (len(records) * repeats),
    }
    if with_meta:
        mtpr, mtnr = mean(r["meta"] for r in positive), mean(r["meta"] for r in negative)
        result.update(meta_ver_tpr=mtpr, meta_ver_tnr=mtnr, meta_ver_bal_f1=harmonic(mtpr, mtnr),
                      meta_valid_rate=sum(bool(t.get("meta") and t["meta"]["valid"]) for r in records for t in r["verifier_trials"]) / (len(records) * repeats))
    return result


def summarize(task, rows, records, samples, repeats, with_meta):
    splits = {}
    units = samples if task == "prover" else 1
    for domain in ("all", "ugd", "qe"):
        selected = rows if domain == "all" else [r for r in rows if r["domain"] == domain]
        done = records if domain == "all" else [r for r in records if r["domain"] == domain]
        expected = len(selected) * units
        complete = len(done) == expected
        metrics = None
        if complete and done:
            metrics = prover_metrics(done, repeats) if task == "prover" else verifier_metrics(done, repeats, with_meta)
        splits[domain] = {"selected_rows": len(selected), "expected_records": expected,
                          "completed_records": len(done), "complete": complete, "metrics": metrics}
    return {"task": task, "complete": splits["all"]["complete"], "score_scale": "0-1",
            "invalid_output_policy": "zero_credit_in_fixed_denominator",
            "splits": splits}
