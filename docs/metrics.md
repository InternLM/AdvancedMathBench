# Metrics and reproducibility

This is a **basic reference implementation**, not a promise of bit-for-bit
reproduction of historical service runs. Scores are fractions in [0, 1].

## ProverBench

Let $c_{i,j}$ be 1 exactly when generated proof $j$ of problem $i$ received
all $R$ requested **valid** judgments and all reported `first_error_step=-1`;
otherwise it is 0. Generation/API/format failure also gives 0.

$$
\mathrm{pessimistic}=\frac{1}{N}\sum_{i=1}^{N}\frac{1}{S}\sum_{j=1}^{S}c_{i,j}.
$$

`--samples` is $S$ and `--verifier-repeats` is $R$. Each problem has equal
weight. `pass_any_sample` is the fraction of problems with at least one
accepted sampled proof, not an unbiased pass@k estimator and not the same as
`pessimistic`. AutoVerifier judgments are fallible, not formal certificates.

## VerifierBench: basic metrics

Positive means a **human-correct proof**, not a proof containing an error.
For a valid prediction, `first_error_step=-1` means predicted correct.

| Field | Definition |
|---|---|
| `rough_accuracy` | Fraction of judgments matching GT correct/incorrect polarity |
| `rough_tpr` | Fraction accepting human-correct proofs |
| `rough_tnr` | Fraction rejecting human-incorrect proofs |
| `rough_bal_f1` | Harmonic mean of `rough_tpr` and `rough_tnr` |
| `balanced_accuracy` | Arithmetic mean of `rough_tpr` and `rough_tnr` |
| `first_error_step_accuracy` | Fraction matching GT's earliest nonnegative fatal/recoverable index, or -1 |
| `first_error_step_accuracy_incorrect` | Same localization metric, restricted to human-incorrect proofs |

An invalid evaluation contributes zero to agreement on **both** GT classes;
it is not mapped to "incorrect proof." Denominators include every requested
repeat. First average within each proof, then average proofs within the
relevant class/domain. The `verifier_valid_rate` exposes response failures.

$$
\mathrm{bal\_f1}=\frac{2\,\mathrm{TPR}\,\mathrm{TNR}}{\mathrm{TPR}+\mathrm{TNR}}.
$$

The historical name `bal_f1` is retained, but this is **not ordinary binary
F1 and not macro-F1**. Return 0 if both rates are 0; return `null` if a class
is absent. Basic polarity agreement does not establish that the verifier
identified the right reason for an error.

## VerifierBench: optional meta metrics

With `--meta`, a separate LLM compares the verifier's assessment/errors with
human ground truth, using the bundled meta prompt. Levels map to:

| Level | Score |
|---|---:|
| EXACT_MATCH | 1.0 |
| BASIC_MATCH | 0.75 |
| POOR_MATCH | 0.5 |
| WRONG_POLARITY | 0.0 |
| Invalid/missing verifier or meta evaluation | 0.0 |

`meta_ver_tpr` is the mean meta score on human-correct proofs;
`meta_ver_tnr` is the mean meta score on human-incorrect proofs;
`meta_ver_bal_f1` is their harmonic mean. In particular, `meta_ver_tnr` is a
**graded explanation-alignment score**, not just the probability of rejection.
`meta_valid_rate` counts valid meta evaluations over all requested verifier
passes, including those whose invalid verifier output prevented a meta call.

## Important differences and limitations

- Historical aggregation could exclude invalid parses from some averages.
  This implementation never drops them from denominators. Compare results
  only with matching failure policies and report valid rates.
- Duplicate XML fields, out-of-range steps, empty assessments, unfinished
  thinking, and non-`stop` finishes are invalid here. The historical regex
  parser was more permissive. XML-like tags are parsed individually to avoid
  rejecting mathematical `<` characters; full XML conformance is not required.
- Ground truth checks fatal **and** recoverable labels; errors after a fatal
  error are handled by the meta prompt's documented completeness cutoff.
- No optimized-voting threshold search, bootstrap confidence intervals,
  scaling curves, XLSX exports, formal theorem proving, or concurrent inference
  are implemented. VerifierBench reports repeat averages, not pessimistic voting.
- No hidden internal API adapters, scheduler, model-name mappings, or secret
  sampling defaults are imported. The submitted config and prompt hashes are
  saved, but server-side defaults may still affect sampling; specify and report
  them as needed. Transport retries can produce additional samples after a timeout.
- Using reference solutions, changing the meta model, altering prompts,
  generation settings, or repeat counts changes the protocol. Record all of these
  before comparing against a paper table. No paper-level reproduction claim is made.
- Human annotations and dataset quality are taken as supplied. This evaluator
  does not resolve the release's documented missing metadata or quality flags.

Both commands only report scores for completed splits. An interrupted run is
not silently presented as a full benchmark score.
