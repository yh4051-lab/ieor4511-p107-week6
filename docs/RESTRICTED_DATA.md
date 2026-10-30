# Restricted course data

[Download the restricted Week 6 data package](https://drive.google.com/file/d/1qM3_vRim7PjjDtkDC0bFYVb8deZpJyNk/view) using an authorized Columbia LionMail account. This link is for course review; its contents are not part of the public repository.

The package contains the original `Quantinno_Estimates_Full Extension Range.xlsx`, its extracted estimates and source notes, the original source-based scenario configuration, and reference outputs. The estimates are hypothetical provider assumptions, not historical account data. The public example uses independent illustrative inputs instead.

To reproduce the source-based calculation, extract the package into `private/` inside this repository, then run from the repository root:

```text
python -m p107 --config private/configs/example_hypothetical.json --out private/reproduced
```

Use `--no-charts` if the optional plotting packages are unavailable. Compare the numerical CSV outputs with `private/reference_results/`. Run metadata and chart hashes can differ across code versions or dependency environments; inspect `effective_config` and numeric CSVs when comparing.

The local browser interface uses the public illustrative configuration by default. Use the command above for the original source-based run. Keep source files, private configurations, and source-based results under `private/`, which is ignored by Git. Do not replace the public default configuration with the private file.

LionMail access requires sign-in and does not guarantee access for reviewers outside that domain. Those reviewers should contact the project team for authorized access. A public link to this instruction page does not make the underlying Drive data public.
