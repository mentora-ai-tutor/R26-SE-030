"""career_lib — hand-made career-fit model core (NumPy only).

Single source of truth shared by the Colab notebook, ``train.py`` and ``evaluate.py``.
Deliberately depends on **numpy only** so it runs unchanged on Google Colab and inside
the ``knowledge-analysis`` service container (which already ships numpy).

What lives here:
  * the 8 competency axes and the role taxonomy (§3 of the plan);
  * a default O*NET/ESCO-informed role -> competency-importance matrix (the "knowledge");
  * a weak-supervision synthetic-learner generator (labels by competency *shape*);
  * a from-scratch multinomial-logistic-regression trainer (softmax + cross-entropy +
    batch gradient descent + L2) — written out by hand, no sklearn/torch;
  * temperature-scaling calibration and Expected-Calibration-Error;
  * standardisation + inference helpers used by both training and serving.

Nothing here imports matplotlib/sklearn — those are *instrumentation* used only in the
notebook/eval for plots and scoring curves, never by the model itself.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

# --------------------------------------------------------------------------- axes
# Order is the contract: the trained weight columns, the scaler, and the service
# featuriser must all use THIS order. It is exported to feature_axes.json.
FEATURE_AXES: List[str] = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]
AXIS_NAMES: Dict[str, str] = {
    "A1": "Programming Fundamentals",
    "A2": "OOP & Design",
    "A3": "Data Structures",
    "A4": "Algorithms & Complexity",
    "A5": "Robustness / Error Handling",
    "A6": "Concurrency",
    "A7": "Problem-solving Fluency",
    "A8": "Independent Authorship",
}

# Roles the classifier is allowed to output. These are SE-scoped: every one of them
# is *justifiable from Java signal*. Cross-domain roles (Data/ML, Frontend, Mobile,
# DevOps) are intentionally NOT classes here — the service surfaces them only as
# low-confidence "aspirational" matches, because a Java quiz cannot evidence them.
ROLES: List[str] = [
    "Junior Java / Backend Developer",
    "General Software Engineer",
    "DSA / Algorithms-focused Engineer",
    "Systems / Concurrency Engineer",
    "QA / Test Automation Engineer",
]

# Role -> per-axis *importance/requirement* in [0, 1]. O*NET/ESCO-informed expert
# weights (e.g. O*NET 15-1252 Software Developers rates Programming / Complex Problem
# Solving highly). Treated as both the requirement profile (for gap analysis) and the
# competency *shape* used to label synthetic learners. build_matrix.py writes this to
# role_matrix.json; it can be cross-checked against fazni/roles-based-on-skills.
DEFAULT_ROLE_MATRIX: Dict[str, List[float]] = {
    # A1    A2    A3    A4    A5    A6    A7    A8
    "Junior Java / Backend Developer":   [0.70, 0.80, 0.72, 0.58, 0.72, 0.50, 0.62, 0.62],
    "General Software Engineer":         [0.72, 0.72, 0.62, 0.60, 0.62, 0.45, 0.72, 0.62],
    "DSA / Algorithms-focused Engineer": [0.80, 0.50, 0.90, 0.95, 0.50, 0.40, 0.88, 0.70],
    "Systems / Concurrency Engineer":    [0.80, 0.62, 0.72, 0.72, 0.70, 0.95, 0.72, 0.70],
    "QA / Test Automation Engineer":     [0.62, 0.62, 0.52, 0.42, 0.88, 0.32, 0.62, 0.60],
}

# Map a free-text Stack Overflow DevType onto our role taxonomy (for priors + the
# face-validity cross-check in the notebook). Substring match, first hit wins.
DEVTYPE_TO_ROLE: Dict[str, str] = {
    "back-end": "Junior Java / Backend Developer",
    "embedded": "Systems / Concurrency Engineer",
    "system": "Systems / Concurrency Engineer",
    "devops": "Systems / Concurrency Engineer",
    "qa": "QA / Test Automation Engineer",
    "test": "QA / Test Automation Engineer",
    "academic": "DSA / Algorithms-focused Engineer",
    "scientist": "DSA / Algorithms-focused Engineer",
    "engineer, data": "DSA / Algorithms-focused Engineer",
    "full-stack": "General Software Engineer",
    "developer, ": "General Software Engineer",
}


# ----------------------------------------------------------------- matrix helpers
def matrix_to_array(role_matrix: Dict[str, List[float]], roles: List[str]) -> np.ndarray:
    """Return the (K, 8) requirement matrix in canonical role/axis order."""
    return np.array([role_matrix[r] for r in roles], dtype=float)


def role_index(roles: List[str]) -> Dict[str, int]:
    return {r: i for i, r in enumerate(roles)}


# --------------------------------------------------------- synthetic training data
def _cosine_rows(X: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between every learner (X) and every role (M)."""
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return Xn @ Mn.T  # (N, K)


def sample_synthetic_learners(
    M: np.ndarray,
    n_samples: int = 12000,
    priors: np.ndarray | None = None,
    label_noise: float = 0.08,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate (X, y) synthetic learners by weak supervision.

    We have no real (student-profile -> job) labels, so we *encode domain knowledge*:
    a learner is labelled with the role whose competency **shape** they best match
    (cosine similarity to the requirement matrix). Magnitude (overall level) is varied
    independently so the classifier learns *specialisation shape*, not just "strong vs
    weak" — overall level is reported separately as readiness.

    Coverage is guaranteed by drawing half the pool around scaled role prototypes
    (varying level, preserving shape) and half from a broad Beta spread (boundary
    cases). ``label_noise`` flips a fraction of labels to the runner-up role so the
    problem is not linearly trivial — this keeps the loss curves, confusion matrix and
    calibration diagram realistic.
    """
    rng = np.random.default_rng(seed)
    K, d = M.shape
    half = n_samples // 2

    # (a) prototype-anchored: random role, random overall level, shape preserved + jitter
    proto_roles = rng.integers(0, K, size=half)
    levels = rng.uniform(0.40, 1.10, size=(half, 1))
    X_proto = np.clip(M[proto_roles] * levels + rng.normal(0, 0.10, size=(half, d)), 0, 1)

    # (b) broad coverage: Beta(2,2) per axis spreads across [0,1], centred ~0.5
    X_beta = rng.beta(2.0, 2.0, size=(n_samples - half, d))

    X = np.vstack([X_proto, X_beta])
    rng.shuffle(X)

    # Label every learner by best-matching competency shape.
    sims = _cosine_rows(X, M)
    y = sims.argmax(axis=1)

    # Inject label noise -> flip to the runner-up role for a fraction of rows.
    flip = rng.random(len(y)) < label_noise
    runner_up = sims.argsort(axis=1)[:, -2]
    y[flip] = runner_up[flip]

    # Optionally bias class proportions toward real-world priors (SO DevType).
    # Soften 50/50 toward uniform so a dominant class (e.g. back-end) doesn't starve the
    # minority roles of training data — keeps macro-F1 and calibration healthy while still
    # reflecting real base rates.
    if priors is not None:
        priors = priors / priors.sum()
        uniform = np.ones_like(priors) / len(priors)
        priors = 0.5 * priors + 0.5 * uniform
        idx = _resample_to_priors(y, priors, rng)
        X, y = X[idx], y[idx]

    return X.astype(float), y.astype(int)


def _resample_to_priors(y: np.ndarray, priors: np.ndarray, rng) -> np.ndarray:
    """Resample row indices (with replacement) so class freq ≈ priors, keeping size."""
    n = len(y)
    by_class = [np.where(y == k)[0] for k in range(len(priors))]
    target = (priors * n).astype(int)
    target[-1] += n - target.sum()  # fix rounding
    out = []
    for k, cnt in enumerate(target):
        if len(by_class[k]) == 0:
            continue
        out.append(rng.choice(by_class[k], size=cnt, replace=True))
    idx = np.concatenate(out)
    rng.shuffle(idx)
    return idx


# ------------------------------------------------------------- standardisation
def fit_standardizer(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sd = X.std(axis=0) + 1e-8
    return mu, sd


def apply_standardizer(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return (X - mu) / sd


# --------------------------------------------------- hand-written softmax + GD
def softmax(Z: np.ndarray) -> np.ndarray:
    """Numerically stable row-wise softmax."""
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


def one_hot(y: np.ndarray, K: int) -> np.ndarray:
    return np.eye(K)[y]


def cross_entropy(P: np.ndarray, Y: np.ndarray) -> float:
    return float(-np.mean(np.sum(Y * np.log(P + 1e-12), axis=1)))


def accuracy(P: np.ndarray, y: np.ndarray) -> float:
    return float((P.argmax(axis=1) == y).mean())


def train_softmax(
    Xz: np.ndarray,
    y: np.ndarray,
    K: int,
    lr: float = 0.5,
    lam: float = 1e-3,
    epochs: int = 1500,
    Xval: np.ndarray | None = None,
    yval: np.ndarray | None = None,
    class_weight: np.ndarray | None = None,
    seed: int = 42,
) -> Dict[str, object]:
    """Multinomial logistic regression by **full-batch gradient descent**, by hand.

    Returns weights and a per-epoch history (train/val loss & accuracy, gradient norm)
    so the notebook can draw the gradient-descent and train-vs-validation curves.
    """
    rng = np.random.default_rng(seed)
    N, d = Xz.shape
    W = rng.normal(0, 0.01, size=(K, d))
    b = np.zeros(K)
    Y = one_hot(y, K)
    cw = np.ones(K) if class_weight is None else class_weight
    sample_w = cw[y][:, None]  # (N,1) per-row weight

    hist = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": [], "grad_norm": []}
    for _ in range(epochs):
        Z = Xz @ W.T + b
        P = softmax(Z)
        # weighted cross-entropy gradient + L2
        G = (P - Y) * sample_w / N
        gW = G.T @ Xz + lam * W
        gb = G.sum(axis=0)
        W -= lr * gW
        b -= lr * gb

        hist["train_loss"].append(cross_entropy(P, Y) + lam * float(np.sum(W * W)))
        hist["train_acc"].append(accuracy(P, y))
        hist["grad_norm"].append(float(np.linalg.norm(gW)))
        if Xval is not None and yval is not None:
            Pv = softmax(Xval @ W.T + b)
            hist["val_loss"].append(cross_entropy(Pv, one_hot(yval, K)))
            hist["val_acc"].append(accuracy(Pv, yval))

    return {"W": W, "b": b, "history": hist}


# ------------------------------------------------------- temperature calibration
def logits(X: np.ndarray, W: np.ndarray, b: np.ndarray) -> np.ndarray:
    return X @ W.T + b


def fit_temperature(val_logits: np.ndarray, yval: np.ndarray, iters: int = 300, lr: float = 0.01) -> float:
    """Fit a single scalar temperature T>0 minimising validation NLL (Platt-style).

    Optimised in log-space so T stays positive. T>1 softens over-confident probs.
    """
    logT = 0.0
    Y = one_hot(yval, val_logits.shape[1])
    for _ in range(iters):
        T = np.exp(logT)
        P = softmax(val_logits / T)
        # dNLL/dT via chain rule; collapse to a scalar gradient on logT
        # grad of NLL wrt logits scaled by -logits/T^2; aggregate then * dT/dlogT (=T)
        grad_logits = (P - Y) / len(yval)
        gT = np.sum(grad_logits * (-val_logits / T))
        logT -= lr * gT * T
    return float(np.exp(logT))


def expected_calibration_error(probs: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """ECE: gap between confidence and accuracy, averaged over confidence bins."""
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == y).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            ece += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(ece)


# --------------------------------------------------------------------- inference
def predict_proba(
    X_raw: np.ndarray, W: np.ndarray, b: np.ndarray, mu: np.ndarray, sd: np.ndarray, T: float = 1.0
) -> np.ndarray:
    """Full inference path used identically by the service: standardise -> calibrated softmax."""
    Xz = apply_standardizer(np.atleast_2d(X_raw), mu, sd)
    return softmax(logits(Xz, W, b) / T)


def readiness_level(overall_0_100: float, difficulty_reached: str = "medium") -> str:
    """Coarse readiness from overall mastery + the hardest quiz rung answered."""
    ceiling = {"easy": 0, "medium": 1, "hard": 2}.get(difficulty_reached, 1)
    if overall_0_100 >= 75 and ceiling >= 2:
        return "Strong Junior"
    if overall_0_100 >= 55 and ceiling >= 1:
        return "Job-ready (Junior)"
    return "Foundational"


# ------------------------------------------------------ metrics (numpy-only)
def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, K: int) -> np.ndarray:
    cm = np.zeros((K, K), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    return cm


def precision_recall_f1(cm: np.ndarray) -> Dict[str, np.ndarray | float]:
    """Per-class precision/recall/F1 plus macro-F1 from a confusion matrix."""
    tp = np.diag(cm).astype(float)
    prec = tp / (cm.sum(axis=0) + 1e-12)
    rec = tp / (cm.sum(axis=1) + 1e-12)
    f1 = 2 * prec * rec / (prec + rec + 1e-12)
    return {"precision": prec, "recall": rec, "f1": f1, "macro_f1": float(f1.mean())}


def topk_accuracy(probs: np.ndarray, y: np.ndarray, k: int = 3) -> float:
    topk = np.argsort(-probs, axis=1)[:, :k]
    return float(np.mean([yi in row for yi, row in zip(y, topk)]))


def stratified_split(y: np.ndarray, fracs=(0.7, 0.15, 0.15), seed: int = 42):
    """Return index arrays (train, val, test) keeping class proportions."""
    rng = np.random.default_rng(seed)
    tr, va, te = [], [], []
    for k in np.unique(y):
        idx = np.where(y == k)[0]
        rng.shuffle(idx)
        n = len(idx)
        n_tr = int(fracs[0] * n)
        n_va = int(fracs[1] * n)
        tr.append(idx[:n_tr]); va.append(idx[n_tr:n_tr + n_va]); te.append(idx[n_tr + n_va:])
    out = [np.concatenate(s) for s in (tr, va, te)]
    for s in out:
        rng.shuffle(s)
    return out
