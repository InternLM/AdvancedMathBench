# Paper results

The tables below transcribe Table 1 of the final AdvancedMathBench manuscript
dated September 28, 2026. They are **paper-reported measurements**, not results
produced by running this standalone repository. All values are percentages.
The [arXiv page](https://arxiv.org/abs/2607.11849) may serve an earlier manuscript;
see [release notes](release_notes.md).

## ProverBench

The released split contains 200 UG and 45 QE problems. A proof is accepted only
when all eight AutoVerifier judgments accept it; scores average across samples
and problems.

| Model | UG | QE |
|---|---:|---:|
| **Proprietary models** | | |
| GPT-5.5-xhigh | **64.5** | **48.9** |
| GPT-5.5-high | 53.3 | 46.1 |
| GPT-5.2 | 53.0 | 26.7 |
| Gemini-3.1-Pro-Preview | 46.5 | 17.8 |
| Claude-Opus-4.8 | 59.0 | 40.0 |
| **Open-source models** | | |
| DeepSeek-V4-Pro | 54.0 | 40.0 |
| Qwen3.5-397B-A17B | 40.0 | 33.5 |
| Kimi-K2.6 | 48.0 | 20.0 |
| GLM-5.2 | 44.5 | 28.9 |
| gpt-oss-120b | 20.5 | 2.2 |
| Intern-S2-Preview-35B | 27.0 | 16.7 |

## VerifierBench

The split contains 888 annotated proofs. Rough metrics assess correct/incorrect
polarity. Meta metrics additionally assess the alignment of error analyses with
expert annotations, using gpt-oss-120b as the meta-verifier. Positive denotes a
human-correct proof; BalF1 is the harmonic mean of TPR and TNR, not ordinary
binary F1 or macro-F1.

| Model | Rough TPR | Rough TNR | Rough BalF1 | Meta TPR | Meta TNR | Meta BalF1 |
|---|---:|---:|---:|---:|---:|---:|
| **Proprietary models** | | | | | | |
| GPT-5.5-xhigh | 78.9 | 73.3 | **76.0** | 78.9 | 55.1 | 64.9 |
| GPT-5.5-high | 78.4 | **73.8** | **76.0** | 78.3 | 53.6 | 63.6 |
| GPT-5.2 | 66.9 | 65.0 | 65.9 | 66.9 | 50.8 | 57.7 |
| Gemini-3.1-Pro-Preview | 94.0 | 49.0 | 64.4 | 94.0 | 39.1 | 55.2 |
| Claude-Opus-4.8 | **96.4** | 37.9 | 54.4 | 93.8 | 35.0 | 51.0 |
| **Open-source models** | | | | | | |
| DeepSeek-V4-Pro | 78.1 | 70.6 | 74.1 | 78.1 | **55.8** | **65.1** |
| Qwen3.5-397B-A17B | 91.5 | 55.2 | 68.9 | 91.5 | 43.0 | 58.5 |
| Kimi-K2.6 | 80.8 | 63.1 | 70.9 | 80.8 | 50.3 | 62.0 |
| GLM-5.2 | 82.5 | 66.9 | 73.9 | 82.3 | 51.5 | 63.3 |
| gpt-oss-120b | 95.2 | 38.7 | 55.0 | **95.3** | 32.0 | 47.9 |
| Intern-S2-Preview-35B | 95.2 | 38.7 | 55.0 | 95.2 | 30.7 | 46.4 |

The results illustrate two distinct gaps: proof-generation rankings do not
directly predict verification rankings, and agreeing with an expert's binary
verdict does not guarantee identifying the right error. In particular, the
lower meta TNRs highlight the additional difficulty of explaining invalid proofs.

## Reproduction scope

The manuscript reports four independent responses, temperature 1.0, a maximum
output length of 128k tokens, and the highest reasoning effort unless specified
otherwise. The CLI defaults to one proof sample; example configs use 65,536
tokens and require provider-specific settings to be filled in. The reference
implementation also applies strict invalid-output handling. See the
[evaluation guide](evaluation.md) and [metric definitions](metrics.md) before
comparing a new run with these tables.
