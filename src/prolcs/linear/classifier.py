import numpy as np  # type: ignore
import scipy.special as ss  # type: ignore
from sklearn.utils.validation import check_is_fitted # type: ignore


class Classifier():
    # NOTE We drop the k subscript for brevity (i.e. we write W instead of
    # W_k etc.).
    def __init__(self,
                 match,
                 A_ALPHA=10**-2,
                 B_ALPHA=10**-4,
                 A_TAU=10**-2,
                 B_TAU=10**-4,
                 DELTA_S_L_K_Q=10**-4,
                 MAX_ITER=20,
                 **kwargs):
        """
        A local linear regression model (in LCS speak, a “linear regression
        classifier”) based on the provided match function.

        :param match: ``match.match`` is this classifier's match function.
            According to Drugowitsch's framework (or mixture of experts), each
            classifier should get assigned a responsibility for each data point.
            However, in order to be able to train the classifiers independently,
            that responsibility (which depends on the matching function but
            also on the other classifiers' responsibilities) is replaced with
            the matching function.
        :param A_ALPHA: Scale parameter of weight vector variance prior.
        :param B_ALPHA: Shape parameter of weight vector variance prior.
        :param A_TAU: Scale parameter of noise variance prior.
        :param B_TAU: Shape parameter of noise variance prior.
        :param DELTA_S_L_K_Q: Stopping criterion for variational update loop.
        :param MAX_ITER: Only perform up to this many iterations of variational
            updates (abort then, even if stopping criterion is not yet met).
        :param **kwargs: This is here so that we don't need to repeat all the
            hyperparameters in ``Mixture``, ``RandomSearch`` etc. ``Mixture``
            simply passes through ``**kwargs`` to both ``Mixing`` and
            ``Classifier``.
        """
        self.match = match
        self.A_ALPHA = A_ALPHA
        self.B_ALPHA = B_ALPHA
        self.A_TAU = A_TAU
        self.B_TAU = B_TAU
        self.DELTA_S_L_K_Q = DELTA_S_L_K_Q
        self.MAX_ITER = MAX_ITER

    def fit(self, X: np.ndarray, y: np.ndarray):
        """
        Fits this classifier to the provided data.
        """

        self.m_ = self.match.match(X)

        N, self.D_X_ = X.shape
        N, self.D_y_ = y.shape
        X_ = X * np.sqrt(self.m_)
        y_ = y * np.sqrt(self.m_)

        self.a_alpha_, self.b_alpha_ = self.A_ALPHA, self.B_ALPHA
        self.a_tau_, self.b_tau_ = self.A_TAU, self.B_TAU
        self.L_q_ = -np.inf
        delta_L_q = self.DELTA_S_L_K_Q + 1

        # Since this is constant, there's no need to put it into the loop.
        self.a_alpha_ = self.A_ALPHA + self.D_X_ * self.D_y_ / 2
        self.a_tau_ = self.A_TAU + 0.5 * np.sum(self.m_)

        iter = 0
        while delta_L_q > self.DELTA_S_L_K_Q and iter < self.MAX_ITER:
            iter += 1
            # print(f"train_classifier: {delta_L_k_q} > {DELTA_S_L_K_Q}")
            E_alpha_alpha = self.a_alpha_ / self.b_alpha_
            self.Lambda_ = np.diag([E_alpha_alpha] * self.D_X_) + X_.T @ X_
            # While, in theory, Lambda is always invertible here and we thus
            # should be able to use inv (as it is described in the algorithm we
            # implement), we (seldomly) get a singular matrix, probably due to
            # numerical issues. Thus we simply use pinv which yields the same
            # result as inv anyways if the matrix is in fact non-singular. Also,
            # in his own code, Drugowitsch always uses pseudo inverse here.
            self.Lambda_1_ = np.linalg.pinv(self.Lambda_)
            self.W_ = y_.T @ X_ @ self.Lambda_1_
            self.b_tau_ = self.B_TAU + 1 / (2 * self.D_y_) * (
                np.sum(y_ * y_) - np.sum(self.W_ * (self.W_ @ self.Lambda_)))
            E_tau_tau = self.a_tau_ / self.b_tau_
            # D_y factor in front of trace due to sum over D_y elements (7.100).
            self.b_alpha_ = self.B_ALPHA + 0.5 * (E_tau_tau * np.sum(
                self.W_ * self.W_) + self.D_y_ * np.trace(self.Lambda_1_))
            L_q_prev = self.L_q_
            self.L_q_ = self.var_bound(
                X=X,
                y=y,
                # Substitute r by m in order to train classifiers independently
                # (see [PDF p. 219]). After having trained the mixing model
                # we finally evaluate the classifier using r=R[:,[k]] though.
                r=self.m_)
            delta_L_q = self.L_q_ - L_q_prev

        return self

    def predict(self, X):
        """
        This model's mean at the given positions; may serve as a prediction.

        :param X: input vector (N × D_X)

        :returns: mean output vector (N × D_y)
        """
        check_is_fitted(self)

        return X @ self.W_.T

    def predict_var(self, X):
        """
        This model's variance at the given positions; may serve as some kind of
        confidence for the prediction.

        The model currently assumes the same variance in all dimensions; thus
        the same value is repeated for each dimension.

        :param X: input vector (N × D_X)

        :returns: variance vector (N × D_y)
        """
        check_is_fitted(self)

        # TODO Check whether this is correct
        # The sum corresponds to x @ self.Lambda_1 @ x for each x in X.
        var = 2 * self.b_tau_ / (self.a_tau_
                                 - 1) * (1 + np.sum(X * X @ self.Lambda_1_, 1))
        return var.reshape((len(X), self.D_y_)).repeat(self.D_y_, axis=1)

    def var_bound(self, X: np.ndarray, y: np.ndarray, r: np.ndarray):
        E_tau_tau = self.a_tau_ / self.b_tau_
        L_1_q = self.D_y_ / 2 * (ss.digamma(self.a_tau_) - np.log(self.b_tau_)
                                 - np.log(2 * np.pi)) * np.sum(r)
        # We reshape r to a NumPy row vector since NumPy seems to understand
        # what we want to do when we multiply two row vectors (i.e. a^T a).
        L_2_q = (-0.5 * r).reshape(
            (-1)) @ (E_tau_tau * np.sum((y - X @ self.W_.T)**2, 1)
                     + self.D_y_ * np.sum(X * (X @ self.Lambda_1_), 1))
        L_3_q = -ss.gammaln(self.A_ALPHA) + self.A_ALPHA * np.log(
            self.B_ALPHA) + ss.gammaln(self.a_alpha_) - self.a_alpha_ * np.log(
                self.b_alpha_
            ) + self.D_X_ * self.D_y_ / 2 + self.D_y_ / 2 * np.log(
                np.linalg.det(self.Lambda_1_))
        L_4_q = self.D_y_ * (
            -ss.gammaln(self.A_TAU) + self.A_TAU * np.log(self.B_TAU) +
            (self.A_TAU - self.a_tau_) * ss.digamma(self.a_tau_)
            - self.A_TAU * np.log(self.b_tau_) - self.B_TAU * E_tau_tau
            + ss.gammaln(self.a_tau_) + self.a_tau_)
        return L_1_q + L_2_q + L_3_q + L_4_q
