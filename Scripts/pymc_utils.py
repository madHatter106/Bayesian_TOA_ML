from copy import deepcopy
from datetime import datetime as DT
import pickle

from loguru import logger
from theano import shared
import matplotlib.pyplot as pl

from pymc_models import PyMCModel


def subset_significant_feature(trace, labels_list, alpha=0.05, vars_=None):
    if vars_ is None:
        vars_ = ['sd_beta', 'sigma', 'bias', 'w']
    dsum = pm.summary(trace, varnames=vars_, alpha=alpha)
    lbls_list = ['w[%s]' %lbl for lbl in labels_list]
    dsum.index = vars_[:-1] + lbls_list
    hpd_lo, hpd_hi = 100 * (alpha / 2), 100 * (1 - alpha / 2)
    if str(hpd_lo).split('.')[1] == '0':
        hpd_lo = int(hpd_lo)
    if str(hpd_hi).split('.')[1] == '0':
        hpd_hi = int(hpd_hi)
    dsum_subset = dsum[(((dsum[f'hpd_{hpd_lo}']<0)&
                         (dsum[f'hpd_{hpd_hi}']<0))|
                         ((dsum[f'hpd_{hpd_lo}']>0)&
                         (dsum[f'hpd_{hpd_hi}']>0))
                         )]
    pattern1 = r'w\s*\[([a-z_\sA-Z0-9]+)\]'
    return list(dsum_subset.index.str.extract(pattern1).dropna().values.flatten())


def create_smry(trc, labels, vname=['w']):
    ''' Conv fn: create trace summary for sorted forestplot '''
    dfsm = pm.summary(trc, varnames=vname)
    dfsm.rename(index={wi: lbl for wi, lbl in zip(dfsm.index, feature_labels)},
                inplace=True)
    #dfsm.sort_values('mean', ascending=True, inplace=True)
    dfsm['ypos'] = np.linspace(1, 0, len(dfsm))
    return dfsm


def run_model(model_type, tune_iter=10000, nuts_target_accept=0.95,
              compute_interactions=False, datapath=None):
    if datapath:

    else:
        datapath = '../PickleJar/DataSets/AphiTrainTestSplitDataSets.pkl'

    with open(datapath, 'rb') as fb:
        datadict = pickle.load(fb)

    X_s_train = datadict['x_train_s']
    y_train = datadict['y_train']
    X_s_test = datadict['x_test_s']
    y_test = datadict['y_test']

    bands = [411, 443, 489, 510, 555, 670]
    # create band-keyed dictionary to contain models
    model_dict=dict.fromkeys(bands)


    # create theano shared variable
    if compute_interactions:
        poly_tranf = PolynomialFeatures(interaction_only=True, include_bias=False)

        X_s_train_w_int = pd.DataFrame(poly_tranf.fit_transform(X_s_train),
                                       columns=poly_tranf.get_feature_names(input_features=
                                                                            X_s_train.columns),
                                       index=X_s_train.index)
        X_s_test_w_int = pd.DataFrame(poly_tranf.fit_transform(X_s_test),
                                       columns=poly_tranf.get_feature_names(input_features=
                                                                            X_s_train.columns),
                                       index=X_s_test.index)

        X_shared = shared(X_s_train_w_int.values)


    else:
        X_shared = shared(X_s_train.values)

    y_shared = shared(y_train['log10_aphy%d' % bands[0]].values)

    for band in bands:
        logger.info("processing aphi{band}", band=band)
        # set shared variable to training set
        X_shared.set_value(X_s_train.values)
        y_shared.set_value(y_train['log10_aphy%d' % band].values)
        my_model = PyMCModel(model_type,
                            X_shared, y_shared)
        my_model.model.name = 'hshoe_aphy%d' %band
        my_model.fit(n_samples=2000, cores=4, chains=4, tune=tune_iter,
                     nuts_kwargs=dict(target_accept=0.95))
        try:
            ppc_train = my_model.predict(likelihood_name='likelihood')
        except Exception as e:
            logger.error(f"{e}: failed ppc_train")
        try:
            waic_train = my_model.get_waic()
        except Exception as e:
            logger.error(f"{e}: failed waic_train")
        try:
            loo_train = my_model.get_loo()
        except Exception as e:
            logger.error(f"{e}: failed loo_train")
        model_definition = deepcopy(my_model.model)
        trace = deepcopy(my_model.trace_)
        run_dict = dict(model=model_definition, trace=trace,
                        ppc_train=ppc_train, loo_train=loo_train, waic_train=waic_train)

        # set shared variable to testing set for out-of-sample model evaluation
        X_shared.set_value(X_s_test.values)
        y_shared.set_value(y_test['log10_aphy%d' % band].values)
        try:
            ppc_test = my_model.predict(likelihood_name='likelihood')
        except Exception as e:
            logger.error(f"{e}: failed ppc_test")
        try:
            waic_test = my_model.get_waic()
        except Exception as e:
            logger.error(f"{e}: failed waic_test")
        try:
            loo_test = my_model.get_loo()
        except Exception as e:
            logger.error(f"{e}: failed loo_test")

        run_dict.update(dict(ppc_test=ppc_test, waic_test=waic_test, loo_test=loo_test))
        model_dict[band] = run_dict
        with open('../PickleJar/Results/hshoe_model_dict_%s.pkl' %DT.now(), 'wb') as fb:
            pickle.dump(model_dict, fb, protocol=pickle.HIGHEST_PROTOCOL)