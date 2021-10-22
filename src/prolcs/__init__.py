from sklearn.base import BaseEstimator, RegressorMixin  # type: ignore
from sklearn.utils.validation import check_is_fitted, check_X_y  # type: ignore

from .search.ga.drugowitsch import GADrugowitsch
from .search.operators.drugowitsch import DefaultToolbox

search_methods = {"drugowitsch": GADrugowitsch}


class ProLCS(BaseEstimator, RegressorMixin):
    """
    TODO
    """
    def __init__(self,
                 toolbox=DefaultToolbox,
                 search="drugowitsch",
                 n_iter=100):
        """
        Parameters
        ----------
        toolbox : Toolbox object
            A DEAP ``Toolbox`` object that specifies all the operators required
            by the selected search algorithm (``search`` parameter).
        """
        self.toolbox = toolbox
        self.search = search
        self.n_iter = n_iter

    def fit(self, X, y):
        """
        Note: Input is assumed to be standardized.
        """
        # TODO Consider to perform input checking only here (and not in
        # classifier/mixing etc. as well)
        X, y = check_X_y(X, y, multi_output=True)

        searchcls = search_methods[self.search]
        self.search_ = searchcls(self.toolbox, n_iter=self.n_iter)

        self.search_ = self.search_.fit(X, y)

        return self

    def predict(self, X):
        check_is_fitted(self)

        return self.search_.predict(X)

    def predict_mean_var(self, X):
        check_is_fitted(self)

        return self.search_.predict_mean_var(X)

    def predicts(self, X):
        check_is_fitted(self)

        return self.search_.predicts(X)

    # TODO Implement predict_distribution
    def predict_distribution(self, X):
        check_is_fitted(self)

        raise NotImplementedError()

