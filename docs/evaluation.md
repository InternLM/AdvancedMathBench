# Evaluation guide

Minimal, standalone evaluation code for advanced mathematical proof generation
and verification. Python **3.10+**; API evaluation uses only the standard library.
No internal inference framework, cluster launcher, account, or repository is required.

Dataset files and model weights are distributed through the linked Hugging Face
repositories. This guide documents the standalone implementation; see
[release notes](release_notes.md) for pinned artifacts and paper-version details.

| Task | Input | Model calls | Output |
|---|---|---|---|
| ProverBench | Mathematical problems | Prover → AutoVerifier, 8 judgments per generated proof by default | Pessimistic proof-generation score |
| VerifierBench | Problems, candidate proofs, human annotations | Verifier under test; optional meta-verifier | Polarity, first-error localization, optional explanation-quality scores |

The selected release has 245 ProverBench problems (200 UGD / 45 QE) and 888
VerifierBench proofs (168 UGD / 720 QE). These are different evaluation units.

## Quick start

Run from this repository's root; installation is optional for API evaluation:

```bash
python -m advancedmathbench --help
python -m unittest discover -s tests -v
```

For an installed command, optionally run `python -m pip install -e .`, then
use `advancedmathbench` instead of `python -m advancedmathbench`.

### 1. Obtain the benchmark data

The evaluator accepts local JSONL files. From the repository root:

```bash
python -m pip install -e '.[hub]'
bash scripts/download_data.sh
```

The download script pins a dataset commit and verifies both files with SHA256.
Its equivalent download command is:

```bash
hf download debouter/AdvancedMathBench \
  data/proverbench/test.jsonl data/verifierbench/test.jsonl \
  --repo-type dataset \
  --revision 80abe34097edf2531e3d5b07337c4cc0710bfb24 --local-dir .
```

The examples use `data/proverbench/test.jsonl` and `data/verifierbench/test.jsonl`.
For a private or gated repository, first run `hf auth login` with an account that
has access. See [data documentation](../data/README.md) for the schema and labels.

### 2. Configure model endpoints

```bash
cp configs/prover_api.example.json configs/prover_api.local.json
export POLICY_API_KEY="YOUR_API_KEY"
```

Edit the local copy's model names, endpoint URLs, and generation settings.
The policy is the prover being evaluated; `verifier` is the deployed
AutoVerifier used to grade its proofs. API keys are read exclusively from the
environment variable named by `api_key_env`. Omit that key for an unauthenticated
local server. Never put real keys into tracked configuration files.

The HTTP backend sends non-streaming `POST /v1/chat/completions` requests with
one user message and `n=1`. It accepts `base_url` ending in `/v1` or the full
`/v1/chat/completions` path. Compatible hosted APIs and public serving engines
can be used; native provider-specific APIs need an adapter.
See the [vLLM compatibility documentation](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/).
This describes the wire protocol, not a tested serving recipe for the released checkpoint.

`generation` is forwarded as request-body parameters. For example, providers
may accept `reasoning_effort`, `top_p`, or `chat_template_kwargs`. If your
provider uses `max_completion_tokens`, replace `max_tokens`; do not set both.
Parameters are provider-dependent. There are no hidden provider-name heuristics.

`reasoning_content` is stored separately and is never substituted for an empty
final answer. Raw response text, finish reason, usage when available, and
parse status are saved. API error bodies and authentication headers are not logged.

### 3. Run ProverBench

Validate inputs and inspect the call budget first; this makes **no API/model
calls and writes no output files**:

```bash
python -m advancedmathbench prover \
  --data data/proverbench/test.jsonl \
  --config configs/prover_api.local.json \
  --output outputs/prover \
  --samples 4 --verifier-repeats 8 --dry-run
```

First test an endpoint on a small subset using a different output directory:

```bash
python -m advancedmathbench prover \
  --data data/proverbench/test.jsonl \
  --config configs/prover_api.local.json \
  --output outputs/prover-smoke --limit 2 \
  --samples 1 --verifier-repeats 8
```

Run the full benchmark by removing `--dry-run` from the first command.
The default is **1 generated proof per problem**, each judged **8 times**.
`--samples 4` means four independent proofs, each receiving eight judgments:
245 × 4 = 980 prover calls, and at most 7,840 AutoVerifier calls before HTTP
retries. It does not mean four judgments of one proof.

Use `--domain ugd` or `--domain qe` to select a domain. Every run also reports
`all`, `ugd`, and `qe` separately; absent classes/domains produce `null`, not NaN.

### 4. Run VerifierBench

Here `verifier` means the **model being evaluated as a verifier**, which can be
any compatible model, not necessarily the released AutoVerifier. Ground-truth
labels are used for scoring but are never sent to that model.

```bash
cp configs/verifier_api.example.json configs/verifier_api.local.json
export VERIFIER_API_KEY="YOUR_VERIFIER_KEY"
python -m advancedmathbench verifier \
  --data data/verifierbench/test.jsonl \
  --config configs/verifier_api.local.json \
  --output outputs/verifier --verifier-repeats 1
```

To evaluate explanation quality as well, make a local copy of
`configs/verifier_meta.example.json`, configure both models and their key
environment variables, and enable meta verification:

```bash
cp configs/verifier_meta.example.json configs/verifier_meta.local.json
export VERIFIER_API_KEY="YOUR_VERIFIER_KEY"
export META_API_KEY="YOUR_META_KEY"
python -m advancedmathbench verifier \
  --data data/verifierbench/test.jsonl \
  --config configs/verifier_meta.local.json \
  --output outputs/verifier-meta \
  --verifier-repeats 8 --meta
```

The meta-verifier sees the human annotation **after** the tested verifier has
produced its judgment. This requires up to 7,104 verifier and 7,104 meta calls
for all 888 proofs at repeat 8. The final manuscript uses **gpt-oss-120b** as the
meta-verifier; configure the corresponding deployment name at your provider and
report its revision and generation settings. The example is not a hosted service.

## Scoring protocol

All reported scores are on **0–1**, not percentages. See [metrics](metrics.md)
for definitions and differences from historical aggregation scripts.

- A proof is human-correct only if `first_fatal_error_step == -1` **and**
  `recoverable_error_steps == [-1]`. Indices are zero-based.
- ProverBench accepts a generated proof only if **all requested verifier
  passes are valid and have `first_error_step == -1`**. Average these binary
  scores across samples within each problem, then equally across problems.
- VerifierBench averages each proof's repeat scores, then equally averages
  proofs. Basic metrics measure polarity and first-error-step agreement.
  Meta metrics score the alignment of error explanations with human annotation.
- Empty replies, non-`stop` finishes (including truncation), malformed/duplicate
  tags, and out-of-range indices are invalid. Invalid/missing evaluations receive
  zero credit in fixed denominators; an invalid reply is **not** a correct rejection.
- Transport retries apply only to transient HTTP/network errors. Invalid
  mathematical/XML outputs are not resampled.

ProverBench supplies a reference solution to its AutoVerifier when available;
VerifierBench defaults to no reference solution. Change this explicitly with
`--use-reference-solution` / `--no-use-reference-solution`. Reference answers
are not silently substituted for reference solutions. The prover never sees
either the reference solution or human annotation.

The three historical task prompts are bundled. The historical generation
prompt includes a restriction on advanced theorems; it is preserved verbatim,
not silently relaxed. If that restriction is inappropriate for your experiment,
use `--generation-prompt` with a reviewed alternative and report the protocol
change. `--verifier-prompt` and `--meta-prompt` allow analogous overrides.
The verifier parser reads only the final text after `</think>` or the Harmony
final marker; proof steps follow the historical `<step>...</step>` splitting rule.

## Outputs and resuming

```text
outputs/prover/
├── manifest.json       # data/code/prompt hashes, model configs, protocol
├── call_budget.json
├── records/            # one atomically saved JSON per completed proof evaluation
│   ├── 000000_000.json
│   └── ...
├── results.jsonl       # consolidated records in input/sample order
└── summary.json        # scores for all / ugd / qe
```

Add `--resume` to the **identical command** to reuse committed records. A
changed dataset, selection, model config, repeat count, prompt, or evaluator
code is rejected. Completed invalid records are also retained, so resuming
does not preferentially resample failures. Use a new output directory for a
deliberate rerun. Changing only the secret's value does not change the run ID.

Checkpointing is per proof evaluation, not per individual API call. Interrupting
mid-proof repeats that unfinished unit when resumed and can incur extra calls.
Scores for incomplete splits are `null`; `complete` and record counts distinguish
partial outputs from final results. Do not run multiple writers in one output
directory. After a hard process kill, remove `.running.lock` **only after
confirming no process is still using that output directory**.

## Optional: use local Transformers for AutoVerifier

The HTTP route needs no PyTorch. For direct checkpoint loading instead:

```bash
python -m pip install -e '.[local]'
cp configs/local_autoverifier.example.json configs/local_autoverifier.local.json
```

The example pins `debouter/AdvancedMathBench-AutoVerifier` to a specific commit.
Alternatively, run `bash scripts/download_verifier.sh`, set `verifier.model` to
`./models/autoverifier`, and remove `revision` for a local directory. The bundled
scientific tokenizer requires `trust_remote_code=true`:
review its code and trust its source before enabling that option.

Use this config with the same `prover` command. The backend lazily loads public
`Qwen3_5MoeForConditionalGeneration` and `AutoTokenizer`, then generates
sequentially. Generic text causal models may use `model_class=causal`.
API and local backends can be mixed by role.

**The released checkpoint is approximately 68 GiB before runtime/KV-cache
memory. Full weight loading and GPU generation have not been validated by this
repository's offline tests.** Its core parameter shapes and tokenizer were
checked separately, but it also contains 785 MTP tensors outside the tested
public core architecture. This example is not a performance-tested deployment
recipe. Validate a single short request on suitable hardware before a full run.
The local example's top-p/top-k are checkpoint defaults, not a claim about
historical server defaults.

## Tests and protocol differences

`advancedmathbench/` contains the evaluator and bundled prompts; `configs/`
contains placeholder-only examples; `tests/` uses toy math and mock API
responses, requiring neither credentials nor a model. The GitHub Actions
workflow runs the same tests. See [validation](validation.md) for their scope.

No data, weights, private IP pools, or internal library code are bundled.
Keep personal configs (`*.local.json`), keys, caches, and outputs out of Git.
The final manuscript reports four responses, temperature 1.0, a maximum output
length of 128k tokens, and the highest available reasoning effort unless otherwise
specified. The CLI defaults to one proof sample and the example configurations
use 65,536 tokens. Adjust these explicitly for a paper-aligned experiment;
provider-specific limits and reasoning-effort options are not inferred.
Strict invalid-output handling also differs from some historical aggregation;
see [metrics](metrics.md). Offline tests are not a paper-score reproduction.
