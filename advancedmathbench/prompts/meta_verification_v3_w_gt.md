You are an **expert meta-verifier for math-proof verification quality**.

You are given:

- a **Problem Statement**
- a **Reference Solution** (Optional)
- a **Proof Solution** (structured as `<step idx> ... </step idx>`)
- a **Solution Verification** (the verifier’s XML output)
- **Human Ground Truth (GT)** labels

Your task is to evaluate the **verifier output** against the **GT oracle**.

## Core Rule

Human GT is the **oracle ground truth**. Evaluate the verifier **strictly against GT**.
Do **not** re-grade the proof independently.

Step indices refer to `<step idx> ... </step idx>`, starting from 0.

## Verifier Output Format

The `Solution Verification` is an XML output with:

- `<assessment>`: a detailed step-by-step analysis that may reference proof steps by `idx`
- `<errors>`: a list of specific issues; it is empty if the verifier judges the proof fully correct

For this task, infer the verifier’s overall status primarily from `<errors>`:

- if `<errors>` is empty, treat the verifier as judging the proof **correct**
- if `<errors>` contains one or more substantive issues, treat the verifier as judging the proof **incorrect**
- use `<assessment>` to determine which claimed issues were identified, how they are justified, and whether they align with GT

## GT Fields

- `reviewer_comment`: oracle explanation of the real issue(s)

  > **Note on `reviewer_comment`**: When reading this field, disregard any numeric scores (e.g., "得X分", "X/7分", "满分X"), references to a scoring rubric or marking scheme (e.g., "按评分标准", "采分点", "marking scheme"), or citations of a reference/model solution used purely for scoring purposes. Focus only on the substantive step-by-step verification reasoning.
  >
- `first_fatal_error_step`: first fatal error step index; `-1` means no fatal error
- `recoverable_error_steps`: recoverable error step indices before the first fatal error; `[-1]` means none

A **fatal error** is a serious error that breaks global correctness.
A **recoverable error** is a local, minor, fixable issue that does not break the whole proof, such as a typo, a minor technical slip, a small omitted detail, a local under-justification, or a small local defect.

GT says correct if and only if both `first_fatal_error_step == -1` and `recoverable_error_steps == [-1]`, otherwise incorrect.

## What to Evaluate

1. whether GT treats the proof as correct or incorrect
2. whether the verifier treats the proof as correct or incorrect
3. which verifier-identified errors actually match GT
4. whether the verifier found the GT first fatal error, if any
5. whether the verifier found all relevant GT recoverable errors
6. whether the verifier introduced false positives
7. the verifier’s overall correctness and completeness relative to GT

## Matching Rule

A verifier-identified issue counts as a correct GT match only if:

1. **Step match**: it points to the same GT-labeled erroneous step
2. **Reason match**: its reason is materially aligned with `reviewer_comment`
3. **Grounding**: the claim is supported by the Proof Solution text

Exact wording is not required, but the underlying issue must materially match GT.

## False Positives and Misses

A verifier claim is a **false positive** if:

- it flags a step not labeled erroneous by GT, or
- its reason does not materially align with GT, or
- the claim is not supported by the Proof Solution text

A GT issue is **missed** if:

- the verifier does not identify it, or
- points to the wrong step, or
- gives a materially wrong reason

## First Fatal Error

If `first_fatal_error_step != -1`, judge whether the verifier correctly identifies the GT first fatal error under the matching rule above.

If `first_fatal_error_step == -1`, treat first-fatal matching as not applicable.

The verifier does **not** need to explicitly call the error “fatal”.

## Completeness Cutoff

- If a fatal error exists, only GT recoverable errors **before** the first fatal error matter for completeness evaluation
- Errors after the first fatal error are irrelevant for completeness evaluation
- If the verifier also raises issues **after** the first fatal error, do not count them as false positives merely because GT does not annotate them
- However, post-fatal claims that are unsupported by the Proof Solution text may still count as false positives
- If no fatal error exists, evaluate completeness over all GT recoverable errors

## Feedback Levels

Assign exactly one:

### EXACT_MATCH

Use when:

- GT says correct and verifier also says correct, **or**
- GT says incorrect and the verifier finds **all GT-relevant errors that matter**, including:
  - the first fatal error if one exists
  - all relevant recoverable errors under the cutoff rule
- the verifier’s reasons are materially aligned with GT
- there are **no material false positives**

Notes:

- Any **material** false positive disqualifies `EXACT_MATCH`.
- Minor wording differences are acceptable if the underlying issue still matches GT.

### BASIC_MATCH

Use when:

- GT says incorrect
- verifier also says incorrect
- and the verifier’s overall judgment is **basically aligned** with GT

More specifically:

- if GT has a fatal error, the verifier correctly finds the **first fatal error**
- but the verifier may miss some relevant GT recoverable errors
- and/or introduce **limited false positives** that do not overturn the main GT alignment

If GT has **no fatal error**, use this level when:

- the verifier correctly finds **some but not all** GT recoverable errors,
- and the overall match to GT is still reasonably solid

Notes on false positives:

- `BASIC_MATCH` can still apply if false positives are **minor, limited, and secondary**
- if false positives are numerous, central, or substantially distort the verifier’s reasoning, do **not** use `BASIC_MATCH`

### POOR_MATCH

Use when:

- GT says incorrect
- verifier also says incorrect
- but the verifier’s match to GT is **weak, incomplete, or poorly aligned**

This includes cases where:

- if GT has a fatal error, the verifier does **not** correctly find the **first fatal error**
- it only finds recoverable issues, later issues, or weakly related issues instead of the true key issue
- its matching to GT is substantially incomplete or poorly grounded
- it introduces **material or numerous false positives**
- the false positives partially replace, obscure, or distort the real GT issues

If GT has **no fatal error**, use this level when:

- the verifier’s matching to GT recoverable errors is weak,
- or it is heavily mixed with false positives,
- or the overall alignment with GT is not reliable enough for `BASIC_MATCH`

### WRONG_POLARITY

Use when:

- GT says correct but verifier says incorrect, **or**
- GT says incorrect but verifier says correct

This is the worst level.

## Required Output

Return only well-formed XML in exactly this structure:

<assessment>
Explain step-by-step:
1. whether GT treats the Proof Solution as correct or incorrect,
2. whether the verifier treats it as correct or incorrect,
3. which verifier-claimed errors match GT in step and reason,
4. whether the GT first fatal error was found,
5. which GT recoverable errors were matched or missed,
6. whether there are false positives,
7. why the final feedback level was assigned.

Mention step indices explicitly when discussing matched, missed, or false-positive errors.

<level>EXACT_MATCH|BASIC_MATCH|POOR_MATCH|WRONG_POLARITY</level>

## INPUT

## Problem Statement

{problem}

## Reference Solution (Optional)

{human_solution}

## Proof Solution

{solution}

## Solution Verification

{solution_verification}

## Human Ground Truth

{human_ground_truth}
