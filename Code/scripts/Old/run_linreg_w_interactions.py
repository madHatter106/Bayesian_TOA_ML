"""Runs ARD BNN"""

import pickle
from datetime import datetime as DT
from loguru import logger
from copy import deepcopy
import pandas as pd
from theano import shared
from pymc_models import PyMCModel
from pymc_models import hs_regression
from sklearn.preprocessing import PolynomialFeatures


def run_model():
    # load datasets
    with open('../PickleJar/DataSets/AphiTrainTestSplitDataSets.pkl', 'rb') as fb:
        datadict = pickle.load(fb)
    X_s_train = datadict['x_train_s']
    y_train = datadict['y_train']
    X_s_test = datadict['x_test_s']
    y_test = datadict['y_test']

    poly_tranf = PolynomialFeatures(interaction_only=True, include_bias=False)

    X_s_train_w_int = pd.DataFrame(poly_tranf.fit_transform(X_s_train),
                                   columns=poly_tranf.get_feature_names(input_features=
                                                                        X_s_train.columns),
                                   index=X_s_train.index)
    X_s_test_w_int = pd.DataFrame(poly_tranf.fit_transform(X_s_test),
                                   columns=poly_tranf.get_feature_names(input_features=
                                                                        X_s_train.columns),
                                   index=X_s_test.index)
    bands = [411, 443, 489, 510, 555, 670]
    # create band-keyed dictionary to contain models
    model_dict=dict.fromkeys(bands)

    # create theano shared variable
    X_shared = shared(X_s_train_w_int.values)
    y_shared = shared(y_train['log10_aphy%d' % bands[0]].values)
    # Fitting aphi411 model:
    # Instantiate PyMC3 model with bnn likelihood
    for band in bands:
        logger.info("processing aphi{band}", band=band)
        X_shared.set_value(X_s_train_w_int.values)
        y_shared.set_value(y_train['log10_aphy%d' % band].values)
        hshoe_wi_ = PyMCModel(hs_regression, X_shared, y_shared )
        hshoe_wi_.model.name = 'hshoe_wi_aphy%d' %band
        hshoe_wi_.fit(n_samples=2000, cores=4, chains=4, tune=10000,
                    nuts_kwargs=dict(target_accept=0.95))
        ppc_train_ = hshoe_wi_.predict(likelihood_name='likelihood')
        waic_train = hshoe_wi_.get_waic()
        loo_train = hshoe_wi_.get_loo()
        model = deepcopy(hshoe_wi_.model)
        trace = deepcopy(hshoe_wi_.trace_)
        run_dict = dict(model=model, trace=trace,
                        ppc_train=ppc_train_, loo_train=loo_train, waic_train=waic_train)
        X_shared.set_value(X_s_test_w_int.values)
        y_shared.set_value(y_test['log10_aphy%d' % band].values)
        model_test = deepcopy(hshoe_wi_.model)
        ppc_test_ = hshoe_wi_.predict(likelihood_name='likelihood')
        waic_test = hshoe_wi_.get_waic()
        loo_test = hshoe_wi_.get_loo()
        run_dict.update(dict(model_test=model_test, ppc_test=ppc_test_,
                             waic_test=waic_test, loo_test=loo_test))
        model_dict[band] = run_dict
        with open('../PickleJar/Results/hshoe_wi_model_dict_%s.pkl' %DT.now(), 'wb') as fb:
            pickle.dump(model_dict, fb, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    logger.add("linreg_wi_{time}.log")
    run_model()
    logger.info("done!")
