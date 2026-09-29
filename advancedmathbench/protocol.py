"""Prompt construction and conservative parsing. No ground truth enters verifier inputs."""
import re
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"
LEVEL_SCORES = {"EXACT_MATCH": 1.0, "BASIC_MATCH": 0.75, "POOR_MATCH": 0.5, "WRONG_POLARITY": 0.0}
_STEP_OPEN = re.compile(r"<step\b[^>]*>", re.IGNORECASE)
_STEP_CLOSE = re.compile(r"(?:</step\s*>|\\end\s*\{?\s*step\s*\}?\s*>|\\endstep\s*>)\s*\Z", re.IGNORECASE)


def strip_thinking(text):
    marker = "<|end|><|start|>assistant<|channel|>final<|message|>"
    if marker in text:
        text = text.rsplit(marker, 1)[1]
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    # Never grade an unfinished reasoning section as a final proof/verdict.
    if re.search(r"<think\s*>", text, re.IGNORECASE):
        return ""
    return text.strip()


def extract_steps(text):
    matches = list(_STEP_OPEN.finditer(text))
    steps = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[match.end():end].strip()
        while True:
            new = _STEP_CLOSE.sub("", chunk).rstrip()
            if new == chunk:
                break
            chunk = new
        if chunk:
            steps.append(chunk)
    return steps


def proof_block(steps):
    return "\n\n".join(f"<step{i}>\n\n{s}\n\n</step{i}>" for i, s in enumerate(steps))


def parse_verdict(text, num_steps):
    text = strip_thinking(text)
    out = {}
    for tag in ("assessment", "errors", "first_error_step"):
        hits = re.findall(rf"<{tag}\s*>(.*?)</\s*{tag}\s*>", text, re.IGNORECASE | re.DOTALL)
        if len(hits) != 1:
            raise ValueError(f"Expected exactly one <{tag}> field")
        out[tag] = hits[0].strip()
    if not out["assessment"]:
        raise ValueError("Empty assessment")
    if not re.fullmatch(r"-?\d+", out["first_error_step"]):
        raise ValueError("first_error_step is not an integer")
    out["first_error_step"] = int(out["first_error_step"])
    if not -1 <= out["first_error_step"] < num_steps:
        raise ValueError("first_error_step is out of range")
    return out


def parse_level(text):
    hits = re.findall(r"<level\s*>\s*(\w+)\s*</level\s*>", strip_thinking(text), re.IGNORECASE)
    if len(hits) != 1 or hits[0].upper() not in LEVEL_SCORES:
        raise ValueError("Expected one valid <level> field")
    return hits[0].upper()


def verifier_prompt(template, row, steps, use_reference):
    return template.format(problem=row["problem"],
                           human_solution=(row["reference_solution"] or "None") if use_reference else "None",
                           solution=proof_block(steps))


def meta_prompt(template, row, parsed, use_reference):
    ann = row["annotation"]
    gt = (
        f'<reviewer_comment>\n\n{ann["reviewer_comment"]}\n\n</reviewer_comment>\n\n'
        f'<first_fatal_error_step>\n\n{ann["first_fatal_error_step"]}\n\n</first_fatal_error_step>\n\n'
        f'<recoverable_error_steps>\n\n{ann["recoverable_error_steps"]}\n\n</recoverable_error_steps>'
    )
    analysis = f'<assessment>\n\n{parsed["assessment"]}\n\n</assessment>\n\n<errors>\n\n{parsed["errors"]}\n\n</errors>'
    # A single substitution pass avoids rewriting placeholders in inserted math text.
    values = {"problem": row["problem"], "human_solution":
              (row["reference_solution"] or "None") if use_reference else "None",
              "solution": proof_block(row["steps"]), "solution_verification": analysis, "human_ground_truth": gt}
    return re.sub(r"\{(problem|human_solution|solution|solution_verification|human_ground_truth)\}",
                  lambda m: values[m.group(1)], template)


def response_error(response):
    if response.get("error"):
        return response["error"]
    if response.get("finish_reason") != "stop":
        return "non_stop_finish"
    if not strip_thinking(response.get("text", "")):
        return "empty_final_answer"
    return None
