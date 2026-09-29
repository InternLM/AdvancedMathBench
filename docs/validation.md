# Validation and testing

Prepared and tested locally on 2026-09-29. These checks do not make paid API
calls, load the full AutoVerifier, or establish paper-score reproduction.

| Check | Result |
|---|---|
| 38 evaluator/release tests, Python 3.13.5 | Passed |
| Same 38 tests, Python 3.10.18 | Passed |
| Offline wheel and source-distribution builds, with no dependency downloads | Passed |
| Wheel installed into an isolated temporary directory | Passed |
| 32 evaluator tests using only the installed package, outside the source directory | Passed |
| Three prompts included in the installed package | Passed |
| Source distribution includes docs, configs, citation, figure, and download helpers; excludes benchmark records and weights | Passed |
| Full ProverBench input validation / call-budget dry run | 245 records; 980 policy + at most 7,840 verifier calls at samples=4, repeat=8 |
| Full VerifierBench input validation / call-budget dry run | 888 records; at most 7,104 verifier + 7,104 meta calls at repeat=8 |
| Both dataset SHA256 hashes and domain counts checked against the pinned release | Passed |
| Download helper tested offline, including paths with spaces and checksum failure | Passed |
| Shell syntax, configuration validation, and local documentation links | Passed |
| CITATION.cff checked against the official CFF 1.2.0 schema | Passed |
| README citation, BibTeX, and CFF use the arXiv 13-author list; README header retains the final 14 authors | Passed |
| All 88 result-table values checked against final manuscript Table 1 | Passed |
| Runtime import audit | Standard library; optional public torch/transformers only |
| Scan of release files for internal absolute paths, internal imports, and key-like secrets | No matches in the checked patterns |

The tests cover step segmentation, thinking removal, strict verdict parsing,
human-label validation, missing/duplicate labels, invalid/truncated/empty
responses, eight-pass pessimistic scoring, problem-macro averaging, per-domain
and absent-class behavior, optional graded meta scores, fixed denominators,
HTTP request/response handling with mocks, transient retries, redacted HTTP
errors, reference/GT isolation, completed-run and interrupted-run resume,
configuration mismatch rejection, and read-only dry runs.

The full-data dry runs use local copies of the pinned dataset files; they do not constitute
model evaluation results. Unit tests create their own toy data in temporary
directories and require no access to the author's filesystem.

## Not yet tested

- Live remote-provider compatibility, quotas, model versions, or provider-specific parameters.
- An end-to-end network run of the new download helpers (their argument handling
  and checksum behavior were tested with a local mock).
- Full AutoVerifier weight loading, memory requirements on a chosen device,
  MTP extra-key handling during actual loading, or GPU generation.
- Agreement with the original hosted service or published paper tables.
- The GitHub Actions workflow on an actual remote repository.

The optional local backend has only lazy-initialization/configuration tests
here; it must not be described as a validated full-model inference deployment.

Run the offline suite again after any change:

```bash
python -m unittest discover -s tests -v
```

CI uses the public [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions. Publishing the
repository and executing its remote workflow remain owner actions.
