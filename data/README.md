# Benchmark data

Dataset: [debouter/AdvancedMathBench](https://huggingface.co/datasets/debouter/AdvancedMathBench).
Data files are downloaded separately and are not stored in this Git repository.

From the repository root:

```bash
python -m pip install -e '.[hub]'
bash scripts/download_data.sh
```

If required, run `hf auth login` using an account with repository access.
The script pins revision `80abe34097edf2531e3d5b07337c4cc0710bfb24` and verifies
both files against [SHA256SUMS](SHA256SUMS). To choose a different download root,
pass it as the first argument: `bash scripts/download_data.sh /path/to/benchmarks`.

```text
data/
├── proverbench/test.jsonl      # 245 problems: 200 ugd, 45 qe
└── verifierbench/test.jsonl    # 888 proofs: 168 ugd, 720 qe
```

## Schema

Both splits use UTF-8 JSONL, one record per line. Common fields are
`problem_id`, `problem`, `reference_solution`, `reference_answer`, `domain`,
`subject`, and `source_id`. `ugd` is the UG domain in the paper; `qe` is QE.
ProverBench has one record per problem; VerifierBench has one record per proof,
so several records can share a `problem_id`.

VerifierBench additionally provides `proof_id`, `steps`, `policy`, `annotation`,
`is_correct`, and `first_error_step`. The annotation contains
`first_fatal_error_step`, `recoverable_error_steps`, and expert commentary.
Step indices are zero-based. A proof is correct only when the fatal index is
`-1` **and** the recoverable indices are exactly `[-1]`.

For complete field definitions and data-specific terms, see the
[dataset card](https://huggingface.co/datasets/debouter/AdvancedMathBench/blob/main/README.md).
Reference solutions and human annotations are not supplied to the tested prover.
Human annotations are not supplied to the tested verifier; they are used for
scoring and, optionally, by the separate meta-verifier.
