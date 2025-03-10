import random
from functools import wraps
from time import asctime, localtime, time
from typing import *

import numpy as np  # type: ignore
import scipy.stats as st  # type: ignore
import scipy.optimize  # type: ignore
import scipy.special as sp  # type: ignore
from deap import tools

# np.seterr(all="raise", under="ignore")


def randseed(random_state: np.random.RandomState):
    """
    Sometimes we need to generate a new random seed from a ``RandomState`` due
    to different APIs (e.g. NumPy wants the new rng API, scikit-learn uses the
    legacy NumPy ``RandomState`` API, DEAP uses ``random.random``).
    """
    # Highest possible seed is `2**32 - 1` for NumPy legacy generators.
    return random_state.randint(2**32 - 1)


def randseed_legacy():
    """
    Sometimes we need to generate a new random seed for a ``RandomState`` from
    the standard random library due to different APIs (e.g. NumPy wants the new
    rng API, scikit-learn uses the legacy NumPy ``RandomState`` API, DEAP uses
    ``random.random``).
    """
    # Highest possible seed is `2**32 - 1` for NumPy legacy generators.
    return random.randint(0, 2**32 - 1)


def logstartstop(f):
    """
    Simple decorator for adding stdout prints when the given callable is called
    and when it returns.
    """
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        print(f"Start {f.__name__} at {asctime(localtime(ts))}")
        r = f(*args, **kw)
        te = time()
        print(f"Stop {f.__name__} after %2.4f s" % (te - ts))
        return r

    return wrap


def get_ranges(X: np.ndarray):
    """
    Computes the value range for each dimension.

    :param X: input data as an ``(N, DX)`` matrix

    :returns: a ``(DX, 2)`` matrix where each row consists the minimum and
        maximum in the respective dimension
    """
    return np.vstack([np.min(X, axis=0), np.max(X, axis=0)]).T


def add_bias(X: np.ndarray):
    """
    Prefixes each input vector (i.e. row) in the given input matrix with 1 for
    fitting the intercept.

    :param X: input data as an ``(N, DX)`` matrix

    :returns: a ``(N, DX + 1)`` matrix where each row is the corresponding
        original matrix's row prefixed with 1
    """
    N, DX = X.shape
    return np.hstack([np.ones((N, 1)), X])


def pr_in_sd1(r=1):
    """
    Expected percentage of examples falling within one standard deviation of a
    one-dimensional Gaussian distribution. See ``pr_in_sd``.

    Parameters
    ----------
    r : float
        Radius (in multiples of standard deviation).
    """
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.erf.html
    return sp.erf(r / np.sqrt(2))


def pr_in_sd2(r=1):
    """
    Expected percentage of examples falling within one standard deviation of a
    two-dimensional Gaussian distribution. See ``pr_in_sd``.

    Parameters
    ----------
    r : float
        Radius (in multiples of standard deviation).
    """
    return 1 - np.exp(-(r**2) / 2)


def pr_in_sd(n=3, r=1):
    """
    Expected percentage of examples falling within multiples of a standard
    deviation of a multivariate Gaussian distribution.

    Reference for the used formulae:
    https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118537 .

    Parameters
    ----------
    n : positive int
        Dimensionality of the Gaussian.
    r : float greater than 1
        Factor for standard deviation radius. Numerical issues(?) if radius too
        close to zero. We probably never want require r < 1, though, so this is
        probably fine.
    """
    if r < 1:
        raise ValueError(f"r = {r} < 1 may result in numerical issues")

    if n == 1:
        return pr_in_sd1(r=r)
    elif n == 2:
        return pr_in_sd2(r=r)
    elif n >= 3:
        ci = pr_in_sd(n=n - 2, r=r) - (r / np.sqrt(2))**(n - 2) * np.exp(
            -(r**2) / 2) / sp.gamma(n / 2)
        if ci < 0 and np.isclose(ci, 0):
            return 0
        else:
            return ci
    else:
        raise ValueError("n must be positive")


pr_in_sd_ = np.vectorize(pr_in_sd)


def radius_for_ci(n=3, ci=0.5):
    """
    Calculate how many standard deviations are required to fulfill the given
    confidence interval for a multivariate Gaussian of the given dimensionality.
    """
    # Other than in this German Wikipedia article we actually need to use
    # SciPy's inverse of the *lower* incomplete gamma function:
    # https://de.wikipedia.org/wiki/Mehrdimensionale_Normalverteilung
    return np.sqrt(2 * sp.gammaincinv(n / 2, ci))
    # NOTE We could also use chi2.ppf instead; the result is the same.


radius_for_ci_ = np.vectorize(radius_for_ci)


def ball_vol(r: float, n: int):
    """
    Volume of an n-ball with the given radius.

    Parameters
    ----------
    r : float
        Radius.
    n : int
        Dimensionality.
    """
    return np.pi**(n / 2) / sp.gamma(n / 2 + 1) * r**n


def ellipsoid_vol(rs: np.ndarray, n: int):
    """
    Volume of an ellipsoid with the given radii.

    Parameters
    ----------
    rs : array of shape ``(n)``
        Radius.
    n : int
        Dimensionality.
    """
    return np.pi**(n / 2) / sp.gamma(n / 2 + 1) * np.prod(rs)


def ranges_vol(ranges):
    return np.prod(np.diff(ranges))


def space_vol(dim):
    """
    The volume of an ``[-1, 1]^dim`` space.
    """
    return 2.**dim


def check_phi(phi, X: np.ndarray):
    """
    Given a mixing feature mapping ``phi``, compute the mixing feature matrix
    ``Phi``.

    If ``phi`` is ``None``, use the default LCS mixing feature mapping, i.e. a
    mixing feature vector of ``phi(x) = 1`` for each data point ``x``.

    Parameters
    ----------
    phi : callable receiving ``X`` or ``None``
        Mixing feature extractor (N × DX → N × DV); if ``None`` uses the
        default LCS mixing feature matrix based on ``phi(x) = 1``.
    X : array of shape (N, DX)
        Input matrix.

    Returns
    -------
    Phi : array of shape (N, DV)
        Mixing feature matrix.
    """
    # NOTE This is named like this in order to stay close to sklearn's naming
    # scheme (e.g. check_random_state etc.).

    N, _ = X.shape

    if phi is None:
        Phi = np.ones((N, 1))
    else:
        Phi = phi(X)

    return Phi


def matching_matrix(matchs: List, X: np.ndarray):
    """
    :param ind: an individual for which the matching matrix is returned
    :param X: input matrix (N × DX)

    :returns: matching matrix (N × K)
    """
    # TODO Can we maybe vectorize this?
    return np.hstack([m.match(X) for m in matchs])


def initRepeat_binom(container, func, n, p, random_state, kmin=1, kmax=100):
    """
    Alternative to `deap.tools.initRepeat` that samples individual sizes from a
    binomial distribution B(n, p).
    """
    size = np.clip(random_state.binomial(n, p), kmin, kmax)
    return tools.initRepeat(container, func, size)


def known_issue(expl, variables, report=False):
    """
    Document a known issue.
    """
    print(f"Warning: {expl}.")
    if report:
        print("This should not have occurred, please report it!")
    else:
        print("This is a known issue and can probably be ignored.")
    print(f"Relevant variables: {variables}.")


def t(mu, prec, df):
    """
    Alternative form of the Student's t distribution used by Drugowtisch (see
    e.g. (Bishop, 2006)).

    Parameters
    ----------
    mu : float or array
        Mean of the distribution.
    prec : float or array
        “Precision” of the distribution (although “not in general equal to the
        inverse of the variance”, see (Bishop, 2006)).
    df : float or array
        Degrees of freedom.

    Returns
    -------
    callable
        A probability density function.
    """
    def pdf(X):
        # Repeat X so that we can perform vectorized calculation.
        X = X[:,np.newaxis].repeat(len(mu),axis=1)
        return sp.gamma((df + 1) / 2) / sp.gamma(df / 2) * np.sqrt(
            prec / (np.pi * df)) * (1 + (prec *
                                         (X - mu)**2) / df)**(-(df + 1) / 2)

    return pdf
