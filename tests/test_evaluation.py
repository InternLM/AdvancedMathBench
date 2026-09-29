import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from advancedmathbench.backends import APIBackend, BackendError, TransformersBackend, validate_config
from advancedmathbench.cli import evaluate, parser, run
from advancedmathbench.data import load_data
from advancedmathbench.metrics import harmonic, prover_metrics, summarize, verifier_metrics
from advancedmathbench.protocol import (PROMPTS, extract_steps, meta_prompt, parse_level, parse_verdict,
                                       response_error, strip_thinking, verifier_prompt)


def response(text, finish="stop"):
    return {"text": text, "finish_reason": finish, "error": None}


def verdict(step=-1):
    return f"<assessment>Checked the argument.</assessment><errors>{'Bad step' if step >= 0 else ''}</errors><first_error_step>{step}</first_error_step>"


def trial(step=-1, valid=True, meta_score=None):
    value = {"valid": valid, "parsed": {"first_error_step": step} if valid else None}
    if meta_score is not None:
        value["meta"] = {"valid": True, "score": meta_score}
    return value


def data_row(domain="ugd", correct=True, index=0):
    return {"problem_id": f"p{index}", "proof_id": f"v{index}", "problem": f"Prove that {index}+0={index}.",
            "reference_solution": "REF_ONLY_IN_JUDGE", "domain": domain, "subject": "Algebra",
            "steps": ["Additive identity gives the equality."],
            "annotation": {"first_fatal_error_step": -1 if correct else 0, "recoverable_error_steps": [-1],
                           "reviewer_comment": "GT_MUST_NOT_LEAK", "first_error_reason": "", "remark": ""},
            "is_correct": correct, "first_error_step": -1 if correct else 0}


class FakeBackend:
    def __init__(self, values):
        self.values = iter(values)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        value = next(self.values)
        if isinstance(value, BaseException):
            raise value
        return value


class ProtocolTests(unittest.TestCase):
    def test_strip_thinking(self):
        self.assertEqual(strip_thinking("<think>bad</think>final"), "final")
        self.assertEqual(strip_thinking("unfinished<think>reasoning"), "")
        marker = "<|end|><|start|>assistant<|channel|>final<|message|>"
        self.assertEqual(strip_thinking("reasoning" + marker + "<think>x</think>done"), "done")

    def test_step_segmentation(self):
        self.assertEqual(extract_steps("<step>one</step>\n<step idx='1'>two\\end{step}>"), ["one", "two"])
        self.assertEqual(extract_steps("No tagged proof"), [])
        self.assertEqual(extract_steps("<step>\n</step><step>real</step>"), ["real"])

    def test_last_think_only_is_used(self):
        parsed = parse_verdict("<think>" + verdict(0) + "</think>" + verdict(), 1)
        self.assertEqual(parsed["first_error_step"], -1)

    def test_bad_verdicts(self):
        for text in ["", "<first_error_step>-1</first_error_step>", verdict() + verdict(), verdict(1), verdict(-2),
                     verdict().replace("-1", "1.0"), verdict().replace("Checked the argument.", "")]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_verdict(text, 1)

    def test_localization_and_case(self):
        self.assertEqual(parse_verdict(verdict(0).upper(), 2)["first_error_step"], 0)

    def test_meta_levels(self):
        self.assertEqual(parse_level("<think><level>WRONG_POLARITY</level></think><level>BASIC_MATCH</level>"), "BASIC_MATCH")
        for text in ["EXACT_MATCH", "<level>OTHER</level>", "<level>EXACT_MATCH</level>" * 2]:
            with self.assertRaises(ValueError):
                parse_level(text)

    def test_truncated_and_empty_responses(self):
        self.assertIsNotNone(response_error(response(verdict(), "length")))
        self.assertIsNotNone(response_error(response(verdict(), None)))
        self.assertIsNotNone(response_error(response("")))

    def test_ground_truth_is_only_in_meta_prompt(self):
        row = data_row()
        text = verifier_prompt((PROMPTS / "proof_verifier.md").read_text(), row, row["steps"], False)
        self.assertNotIn("GT_MUST_NOT_LEAK", text)
        self.assertNotIn("REF_ONLY_IN_JUDGE", text)
        parsed = parse_verdict(verdict(), 1)
        mt = meta_prompt((PROMPTS / "meta_verification_v3_w_gt.md").read_text(), row, parsed, False)
        self.assertIn("GT_MUST_NOT_LEAK", mt)
        self.assertNotIn("REF_ONLY_IN_JUDGE", mt)


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_data(self, rows, name="data.jsonl"):
        path = self.root / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path


class DataTests(TempCase):
    def test_nested_and_legacy_annotations(self):
        row = data_row()
        self.assertTrue(load_data(self.write_data([row]), "verifier")[0]["is_correct"])
        row.update(row.pop("annotation"))
        row["solution"] = row.pop("reference_solution")
        self.assertTrue(load_data(self.write_data([row]), "verifier")[0]["is_correct"])

    def test_invalid_labels_not_silently_correct(self):
        for bad in [[], [-1, 0], [1], [True], None]:
            row = data_row()
            row["annotation"]["recoverable_error_steps"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load_data(self.write_data([row]), "verifier")

    def test_bool_fatal_is_invalid(self):
        row = data_row()
        row["annotation"]["first_fatal_error_step"] = False
        with self.assertRaises(ValueError):
            load_data(self.write_data([row]), "verifier")

    def test_recoverable_error_alone_is_incorrect(self):
        row = data_row()
        row["annotation"]["recoverable_error_steps"] = [0]
        row.update(is_correct=False, first_error_step=0)
        self.assertFalse(load_data(self.write_data([row]), "verifier")[0]["is_correct"])

    def test_conflicting_derived_label(self):
        row = data_row()
        row["is_correct"] = False
        with self.assertRaises(ValueError):
            load_data(self.write_data([row]), "verifier")

    def test_duplicate_ids_rejected(self):
        for task in ("prover", "verifier"):
            with self.assertRaises(ValueError):
                load_data(self.write_data([data_row(), data_row()]), task)


class MetricTests(unittest.TestCase):
    def test_all_eight_must_pass(self):
        record = {"problem_id": "p", "generation_error": None, "verifier_trials": [trial()] * 8}
        self.assertEqual(prover_metrics([record], 8)["pessimistic"], 1)
        for replacement in [trial(0), trial(valid=False)]:
            record["verifier_trials"] = [trial()] * 7 + [replacement]
            self.assertEqual(prover_metrics([record], 8)["pessimistic"], 0)
        record["verifier_trials"] = [trial()] * 7
        self.assertEqual(prover_metrics([record], 8)["pessimistic"], 0)

    def test_macro_average_and_pass_any_are_different(self):
        records = [{"problem_id": p, "generation_error": None, "verifier_trials": [trial(step)]}
                   for p, step in [("a", -1), ("a", 0), ("b", 0), ("b", 0)]]
        scores = prover_metrics(records, 1)
        self.assertEqual(scores["pessimistic"], 0.25)
        self.assertEqual(scores["pass_any_sample"], 0.5)

    def test_invalid_outputs_do_not_get_negative_credit(self):
        records = [{"is_correct": truth, "first_error_step": -1 if truth else 0,
                    "verifier_trials": [trial(valid=False)]} for truth in [True, False]]
        scores = verifier_metrics(records, 1, False)
        self.assertEqual(scores["rough_tpr"], 0)
        self.assertEqual(scores["rough_tnr"], 0)
        self.assertEqual(scores["rough_bal_f1"], 0)

    def test_meta_scores_are_not_binary_tnr(self):
        records = [{"is_correct": True, "first_error_step": -1, "verifier_trials": [trial(-1, meta_score=1)]},
                   {"is_correct": False, "first_error_step": 0, "verifier_trials": [trial(0, meta_score=0.5)]}]
        scores = verifier_metrics(records, 1, True)
        self.assertEqual(scores["rough_tnr"], 1)
        self.assertEqual(scores["meta_ver_tnr"], 0.5)
        self.assertAlmostEqual(scores["meta_ver_bal_f1"], 2 / 3)

    def test_one_class_and_partial_summaries(self):
        self.assertIsNone(harmonic(1, None))
        result = summarize("prover", [data_row()], [], 1, 8, False)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["splits"]["all"]["metrics"])
        self.assertIsNone(result["splits"]["qe"]["metrics"])


class APITests(unittest.TestCase):
    def spec(self):
        return {"model": "toy", "base_url": "https://example.invalid/v1", "max_retries": 0}

    def test_request_and_separate_reasoning(self):
        spec = {**self.spec(), "api_key_env": "AMB_TEST_KEY", "generation": {"temperature": 1, "max_tokens": 10}}
        data = {"choices": [{"message": {"content": "final", "reasoning_content": "reasoning"}, "finish_reason": "stop"}]}
        with patch.dict(os.environ, {"AMB_TEST_KEY": "unit-test-not-a-real-key"}), patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as http:
            out = APIBackend(spec).complete("problem")
        req = http.call_args.args[0]
        self.assertEqual(req.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(json.loads(req.data)["messages"], [{"role": "user", "content": "problem"}])
        self.assertEqual(out["text"], "final")
        self.assertNotIn("unit-test-not-a-real-key", json.dumps(out))

    def test_reasoning_only_is_empty_not_answer(self):
        data = {"choices": [{"message": {"content": None, "reasoning_content": verdict()}, "finish_reason": "stop"}]}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            out = APIBackend(self.spec()).complete("x")
        self.assertEqual(response_error(out), "empty_final_answer")

    def test_http_error_redacts_body(self):
        error = urllib.error.HTTPError("https://example.invalid", 401, "secret", {}, io.BytesIO(b"credential"))
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaisesRegex(BackendError, "^HTTP_401$"):
            APIBackend(self.spec()).complete("x")

    def test_transient_retries(self):
        data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        spec = {**self.spec(), "max_retries": 1}
        with patch("urllib.request.urlopen", side_effect=[TimeoutError(), io.BytesIO(json.dumps(data).encode())]) as http, patch("time.sleep"):
            self.assertEqual(APIBackend(spec).complete("x")["text"], "ok")
        self.assertEqual(http.call_count, 2)

    def test_missing_key_and_unsafe_config(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            APIBackend({**self.spec(), "api_key_env": "MISSING"})
        for extra in [{"api_key": "bad"}, {"generation": {"stream": True}},
                      {"base_url": "https://u:p@example.invalid/v1"}, {"base_url": "https://example.invalid/v1?token=x"}]:
            with self.assertRaises(ValueError):
                validate_config({**self.spec(), **extra})

    def test_local_backend_is_lazy(self):
        backend = TransformersBackend({"backend": "transformers", "model": "not-loaded"})
        self.assertIsNone(backend.model)


class CLITests(TempCase):
    def arguments(self, task="prover", rows=None, extra=()):
        data = self.write_data(rows if rows is not None else [data_row()])
        config = self.root / "config.json"
        config.write_text(json.dumps({role: {"model": role, "base_url": "https://example.invalid/v1"}
                                      for role in ("policy", "verifier", "meta")}))
        return parser().parse_args([task, "--data", str(data), "--config", str(config), "--output", str(self.root / "out"), *extra])

    def quiet_run(self, args, clients):
        with contextlib.redirect_stdout(io.StringIO()):
            return run(args, backend_factory=lambda spec: clients[spec["model"]])

    def test_prover_full_run_and_resume_no_new_calls(self):
        args = self.arguments()
        clients = {"policy": FakeBackend([response("<step>proof</step>")]), "verifier": FakeBackend([response(verdict())] * 8)}
        self.quiet_run(args, clients)
        summary = json.loads((args.output / "summary.json").read_text())
        self.assertEqual(summary["splits"]["all"]["metrics"]["pessimistic"], 1)
        self.assertNotIn("REF_ONLY_IN_JUDGE", clients["policy"].prompts[0])
        self.assertNotIn("GT_MUST_NOT_LEAK", clients["verifier"].prompts[0])
        args.resume = True
        self.quiet_run(args, clients)
        self.assertEqual(len(clients["policy"].prompts), 1)
        self.assertEqual(len(clients["verifier"].prompts), 8)
        args.verifier_repeats = 4
        with self.assertRaisesRegex(ValueError, "Resume rejected"):
            self.quiet_run(args, clients)

    def test_generation_failure_skips_verifier(self):
        args = self.arguments()
        clients = {"policy": FakeBackend([response("<step>truncated</step>", "length")]), "verifier": FakeBackend([])}
        self.quiet_run(args, clients)
        summary = json.loads((args.output / "summary.json").read_text())
        self.assertEqual(summary["splits"]["all"]["metrics"]["pessimistic"], 0)
        self.assertFalse(clients["verifier"].prompts)

    def test_verifier_optional_meta_and_domains(self):
        args = self.arguments("verifier", [data_row(index=0), data_row("qe", False, 1)], ["--meta"])
        clients = {"verifier": FakeBackend([response(verdict()), response(verdict(0))]),
                   "meta": FakeBackend([response("<level>EXACT_MATCH</level>"), response("<level>BASIC_MATCH</level>")])}
        self.quiet_run(args, clients)
        summary = json.loads((args.output / "summary.json").read_text())
        self.assertEqual(summary["splits"]["all"]["metrics"]["rough_accuracy"], 1)
        self.assertEqual(summary["splits"]["all"]["metrics"]["meta_ver_tnr"], 0.75)
        self.assertIsNone(summary["splits"]["ugd"]["metrics"]["rough_tnr"])
        self.assertEqual(len(clients["meta"].prompts), 2)

    def test_invalid_meta_stays_in_denominator(self):
        args = self.arguments("verifier", extra=["--meta", "--verifier-repeats", "2"])
        clients = {"verifier": FakeBackend([response(verdict())] * 2),
                   "meta": FakeBackend([response("<level>EXACT_MATCH</level>"), response("invalid")])}
        self.quiet_run(args, clients)
        metrics = json.loads((args.output / "summary.json").read_text())["splits"]["all"]["metrics"]
        self.assertEqual(metrics["meta_ver_tpr"], 0.5)
        self.assertEqual(metrics["meta_valid_rate"], 0.5)

    def test_dry_run_makes_no_calls_or_files(self):
        args = self.arguments(extra=["--dry-run"])
        with contextlib.redirect_stdout(io.StringIO()):
            run(args, backend_factory=lambda _: self.fail("dry run instantiated backend"))
        self.assertFalse(args.output.exists())

    def test_interrupted_resume_only_missing_record(self):
        args = self.arguments(rows=[data_row(), data_row("qe", index=1)], extra=["--verifier-repeats", "1"])
        clients = {"policy": FakeBackend([response("<step>proof</step>"), KeyboardInterrupt()]), "verifier": FakeBackend([response(verdict())])}
        with self.assertRaises(KeyboardInterrupt):
            self.quiet_run(args, clients)
        self.assertFalse(json.loads((args.output / "summary.json").read_text())["complete"])
        self.assertFalse((args.output / ".running.lock").exists())
        args.resume = True
        rest = {"policy": FakeBackend([response("<step>proof</step>")]), "verifier": FakeBackend([response(verdict())])}
        self.quiet_run(args, rest)
        self.assertEqual(len(rest["policy"].prompts), 1)
        self.assertTrue(json.loads((args.output / "summary.json").read_text())["complete"])

    def test_existing_output_is_not_overwritten(self):
        args = self.arguments()
        args.output.mkdir()
        (args.output / "user_file.txt").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.quiet_run(args, {})


if __name__ == "__main__":
    unittest.main()
