"""Laplace inference for the Bradley-Terry model.

Fits a Gaussian posterior ``beta ~ N(mu, Sigma)`` over latent item scores from a
log of graded pairwise answers. ``mu`` is the MAP estimate (Newton's method on the
strictly concave log-posterior); ``Sigma`` is the inverse of the negative Hessian at
the MAP (the Laplace covariance).

Comparison convention (matches the rest of the package):
each comparison is ``(a, b, y)`` where ``a`` is the left item index, ``b`` the right
item index, and ``y in [0, 1]`` is the user's *preference for the right item* ``b``
(``y = 1`` means b fully preferred, ``y = 0`` means a fully preferred, ``0.5`` a tie).

Likelihood per comparison, with mistake floor ``eta`` and ``A = 1 - 2*eta``::

    p = eta + A * sigmoid(beta_b - beta_a)        # modelled prob. of preferring b
    log L = y * log(p) + (1 - y) * log(1 - p)     # continuous-target cross-entropy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Posterior:
    """Gaussian posterior over latent scores."""

    mu: np.ndarray  # (n,) MAP scores
    cov: np.ndarray  # (n, n) Laplace covariance

    @property
    def sd(self) -> np.ndarray:
        return np.sqrt(np.clip(np.diag(self.cov), 0.0, None))


def _grad_hess(
    beta: np.ndarray,
    comps: Sequence[Tuple[int, int, float]],
    eta: float,
    prior_sd: float,
) -> Tuple[float, np.ndarray, np.ndarray]:
    """Return (neg_log_post, grad, hess) of the NEGATIVE log-posterior at ``beta``.

    The negative log-posterior is convex, so ``hess`` is positive (semi-)definite.
    """
    n = beta.shape[0]
    A = 1.0 - 2.0 * eta
    inv_var = 1.0 / (prior_sd * prior_sd)

    # Prior N(0, prior_sd^2): contributes 0.5 * inv_var * ||beta||^2 to the NLL.
    nll = 0.5 * inv_var * float(beta @ beta)
    grad = inv_var * beta.copy()
    hess = inv_var * np.eye(n)

    eps = 1e-12
    for a, b, y in comps:
        u = beta[b] - beta[a]
        s = float(_sigmoid(u))
        p = eta + A * s
        p = min(max(p, eps), 1.0 - eps)

        # log-likelihood and its derivatives w.r.t. u = beta_b - beta_a
        nll -= y * np.log(p) + (1.0 - y) * np.log(1.0 - p)

        dlogL_dp = y / p - (1.0 - y) / (1.0 - p)
        d2logL_dp2 = -y / (p * p) - (1.0 - y) / ((1.0 - p) ** 2)
        dp_du = A * s * (1.0 - s)
        d2p_du2 = A * s * (1.0 - s) * (1.0 - 2.0 * s)

        dlogL_du = dlogL_dp * dp_du
        d2logL_du2 = d2logL_dp2 * dp_du * dp_du + dlogL_dp * d2p_du2

        # Map u-derivatives back to (a, b). Negate for the NLL.
        grad[b] -= dlogL_du
        grad[a] += dlogL_du
        h = -d2logL_du2
        hess[b, b] += h
        hess[a, a] += h
        hess[a, b] -= h
        hess[b, a] -= h

    return nll, grad, hess


def fit(
    n_items: int,
    comparisons: Sequence[Tuple[int, int, float]],
    *,
    eta: float = 0.05,
    prior_sd: float = 1.5,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> Posterior:
    """Fit the Laplace posterior over ``n_items`` scores from ``comparisons``.

    With no comparisons this returns the prior ``N(0, prior_sd^2 I)``.
    """
    beta = np.zeros(n_items, dtype=float)
    comps = list(comparisons)

    for _ in range(max_iter):
        _, grad, hess = _grad_hess(beta, comps, eta, prior_sd)
        # Newton step on the convex NLL: beta <- beta - H^{-1} grad.
        step = np.linalg.solve(hess, grad)
        beta = beta - step
        if np.max(np.abs(step)) < tol:
            break

    _, _, hess = _grad_hess(beta, comps, eta, prior_sd)
    cov = np.linalg.inv(hess)
    return Posterior(mu=beta, cov=cov)
