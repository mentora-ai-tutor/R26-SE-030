# Dataset reference — career-fit model

The career-fit classifier is trained on **synthetic, weak-supervision profiles** generated
from the O\*NET/ESCO-informed role→competency matrix in `career_lib.py`. The dataset below is
**auxiliary real-world data** used only for (a) class priors and (b) a Cohen's-κ face-validity
check — it is **not** training data, and the currently shipped model (`numpy-softmax-seed42`)
was trained with uniform priors, so it does not depend on this file.

## Stack Overflow Annual Developer Survey 2023

| | |
|---|---|
| File | `ml/data/results_2023.csv` (git-ignored — see below) |
| Source URL | https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2023/results.csv |
| LFS media URL | https://media.githubusercontent.com/media/StackExchange/Survey/refs/heads/main/packages/archive/2023/results.csv |
| Size | ~159 MB (151 MiB) |
| SHA-256 | `828874a3cf0fa1bbb4c3da6a87e5822b8563bbc04b21f9869479480dbcff410c` |
| Shape | 89,184 rows (one developer per row) × 84 columns |
| Publisher / license | Stack Overflow — released under the Open Database License (ODbL 1.0); verify terms at the official survey page |

## What the project actually uses from it
Only the **`DevType`** column (76,872 non-empty). Free-text job titles are collapsed into the
five model roles via `career_lib.DEVTYPE_TO_ROLE` (first substring hit wins) to produce class
priors. Approximate counts from this file:

| Model role | Prior count |
|---|---|
| General SE | 38,173 |
| Junior Java / Backend | 13,745 |
| DSA / Algorithms | 4,541 |
| Systems / Concurrency | 3,975 |
| QA / Test Automation | 586 |

The other 83 columns are ignored. There are **no competency-axis measurements** in this survey,
which is why it cannot serve as training features.

## Why it is not committed
`ml/.gitignore` excludes `data/` and `*.csv` on purpose (a 159 MB file exceeds GitHub's 100 MB
limit and would bloat the repo). This datasheet is the portable reference; the raw file is
fetched on demand.

## Re-download / restore the file
```bash
# from the knowledge-analysis service dir:
mkdir -p ml/data
curl -L -o ml/data/results_2023.csv \
  "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2023/results.csv"
# verify integrity:
shasum -a 256 ml/data/results_2023.csv   # expect 828874a3cf0fa1bbb4c3da6a87e5822b8563bbc04b21f9869479480dbcff410c
```

## Use it to actually influence the model (optional)
```bash
python ml/train.py --so-csv ml/data/results_2023.csv   # retrains with SO-derived class priors
python ml/evaluate.py                                   # reproducibility gate
```
