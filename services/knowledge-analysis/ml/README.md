# Career-Fit Model — training (`ml/`)

Hand-made (pure NumPy) multinomial-logistic-regression that maps a learner's 8-axis
competency profile → best-fit software role + calibrated confidence. This folder trains it
and exports the serving artifacts. **The model is served by the `knowledge-analysis` service
with numpy alone** — none of the deps here enter the container.

## Files
| File | Role |
|---|---|
| `career_lib.py` | The model core (softmax + gradient descent + calibration + metrics), axes, role taxonomy, O*NET-informed role→competency matrix, synthetic-learner generator. **Single source of truth.** |
| `build_matrix.py` | Writes `role_matrix.json` / `label_map.json` / `feature_axes.json`. `--with-hf` runs the Hugging Face face-validity cross-check. |
| `train.py` | Synthesize → split → train → temperature-calibrate → export artifacts. `--so-csv` adds real class priors. |
| `evaluate.py` | Reproducibility + quality gate: recompute metrics, compare to `metrics.json`. |
| `colab/build_notebook.py` | Assembles `colab/train_career_model.ipynb` from `career_lib.py` (so they never drift). |
| `colab/train_career_model.ipynb` | **The research notebook** — dataset download, EDA, training, all academic graphs, export. |

## Option A — Colab or VS Code/Jupyter (recommended)
1. Open `colab/train_career_model.ipynb` (Colab: Upload or *Open in Colab*; VS Code: just open it).
2. **Run the first cell** ("Setup — install dependencies") — it `%pip install`s everything into
   the kernel. *Locally, if the next cell then errors with ModuleNotFound, restart the kernel once.*
3. **Run All.** The Stack Overflow survey **auto-downloads from a public URL — no Kaggle login /
   token** (cached in `~/.cache/mentora_so`, ~150 MB, one-time). No GPU needed; trains in seconds.
4. The last cell writes **`career_artifacts.zip`**.

> Robust by design: if the download fails or you're offline, it falls back to **uniform priors**
> and still trains + plots everything. To use a CSV you already have, set `SO_CSV` to its path —
> but it must be the **full** survey with a `DevType` column (not a "selected-columns" subset).

## Option B — Local / CI
```bash
pip install -r ml/requirements-ml.txt
python ml/train.py                       # or: --so-csv data/survey_results_public.csv
python ml/evaluate.py                     # reproducibility gate (exits 1 on drift)
python ml/colab/build_notebook.py         # rebuild the .ipynb after editing career_lib.py
```

## Install the trained model into the service
Unzip `career_artifacts.zip` into `app/services/career/artifacts/` (or just run `train.py`,
which writes there directly). The service loads `model_weights.npz` + `scaler.json` +
`role_matrix.json` + `label_map.json` + `feature_axes.json` at startup. Bump `model_version`
in `metrics.json` on each retrain.

## What gets produced
`model_weights.npz` (W, b, T) · `scaler.json` (μ, σ, axis order) · `role_matrix.json` ·
`label_map.json` · `feature_axes.json` · `metrics.json`. All small (KB) and committed.
