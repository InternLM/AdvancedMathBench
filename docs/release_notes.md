# Release notes

## 0.1.0

This repository provides a standalone evaluator, three task prompts, example
configs, and download helpers for ProverBench, VerifierBench, and AutoVerifier.
It does not include the internal training framework or dataset-construction
pipeline. The code supports sequential API evaluation and optional local
Transformers inference; it is not an optimized inference service.

### Manuscript version

The overview figure, benchmark counts, result tables, and README header author list follow the
author-approved final manuscript dated **2026-09-28**. At preparation time, the
[arXiv record](https://arxiv.org/abs/2607.11849) and
[Hugging Face paper page](https://huggingface.co/papers/2607.11849) still describe
an earlier version with 296 ProverBench problems and 13 authors. The current
release has **245 ProverBench problems** and **888 VerifierBench proofs**.

The final manuscript adds **Zhouqi Hua** as the fifth author. The README header
retains the final 14-author list. Until arXiv is updated, the README's Citation
section, `citation.bib`, and `CITATION.cff` use the current arXiv 13-author list,
with the verified arXiv identifier and DOI. Counts and paper results from
different manuscript versions should not be mixed.

### Pinned artifacts

| Artifact | Hugging Face repository | Revision |
|---|---|---|
| Dataset | [debouter/AdvancedMathBench](https://huggingface.co/datasets/debouter/AdvancedMathBench) | `80abe34097edf2531e3d5b07337c4cc0710bfb24` |
| AutoVerifier | [debouter/AdvancedMathBench-AutoVerifier](https://huggingface.co/debouter/AdvancedMathBench-AutoVerifier) | `2ad58735622f70bbe2f106049bcdf34f5bb93cfd` |

The download scripts use these immutable revisions. Dataset integrity is
checked using [SHA256SUMS](../data/SHA256SUMS). At preparation time on
2026-09-29, both Hub repositories were private; authorized access is required
until the owner changes their visibility. This local release preparation does
not change Hub access settings.

### Evaluation and licensing

Scores in [paper results](results.md) are reported by the final manuscript,
not newly reproduced. Differences in example settings and parser behavior are
documented in [evaluation](evaluation.md) and [metrics](metrics.md). Offline
validation does not establish live-provider or full-checkpoint compatibility.

No code license is declared. Dataset and checkpoint terms are separate; see
[licensing](licensing.md). Publication of the repository does not by itself
grant a new license for any of these artifacts.
