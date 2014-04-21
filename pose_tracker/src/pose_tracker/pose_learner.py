#!/usr/bin/env python

from __future__ import (print_function, division)

import itertools as it
from functools import partial
import numpy as np
import pandas as pd

from sklearn.grid_search import GridSearchCV
from sklearn.metrics import f1_score

from PoseDatasetIO import PoseDatasetIO
#import user_data_loader as udl

HEADER = tuple(['h_seqNum', 'h_stamp', 'user_id'])
JOINTS = tuple(['head', 'neck', 'torso',
                'left_shoulder', 'left_elbow', 'left_hand',
                'right_shoulder', 'right_elbow', 'right_hand',
                'left_hip', 'left_knee', 'left_foot',
                'right_hip', 'right_knee', 'right_foot'])
ATTRIBS = tuple(['confidence', 'pos_x', 'pos_y', 'pos_z',
                 'orient_x', 'orient_y', 'orient_z', 'orient_w'])

COLUMNS = list(it.chain(HEADER,
                      it.imap('_'.join, it.product(JOINTS, ATTRIBS)),
                      ['pose', ]))

positions = [i for i in COLUMNS if '_pos_' in i]
orientations = [i for i in COLUMNS if '_orient_' in i]
confidences = [i for i in COLUMNS if '_confidence' in i]
pose = COLUMNS[-1]


DEFAULT_NAME = 'pose_learner'
COLS_TO_CLEAN=confidences   


def _clean_prefix(text, prefix): 
    return text.lstrip(prefix)

_rm_stand_pref = partial(_clean_prefix, prefix='STAND_')


def prepare_dataset(filename, group_name):
    ''' Loads the file filename and returns all the tables contained in the 
        group 'group_name' in form of a unified dataset
        prior to returning it, the dataset is grouped by pose, to 
    '''
    with PoseDatasetIO(dataset=filename, columns=COLUMNS, mode='r') as dataset:
        dataset = {node._v_name: dataset.store.select(node._v_pathname). \
                                              groupby('pose').mean(). \
                                              rename(_rm_stand_pref)
                  for node in dataset.store.get_node(group_name) }
        return pd.concat(dataset)


def drop_columns(dataset, cols=COLS_TO_CLEAN):
    ''' Drops the entered dataset columns. 
        @type dataset: pandas.DataFrame
        @param dataset: the dataset which columns are going to be dropped 
        @param cols: the list of column names to be dropped.
                     Default: L{COLS_TO_CLEAN}
        @return: A copy of the dataset without the columns
    '''
    return dataset.drop(cols, axis=1)


def numerize_y(y):
    ''' Converts vector y to nums'''
    labels = sorted(set(y))
    return np.array(map(labels.index, y))


def df_to_Xy(dataframe):
    ''' Converts a dataframe to scikitlearn's compatible X and y
        @param dataframe: DataFrame to be converted to scikit-learn X,y format
        @type dataframe: pandas.DataFrame
        @return: a tuple (X, y)
    '''
    y = zip(*dataframe.index)[1]
    y_num = numerize_y(y)
    return (dataframe.values, y_num)


def fit_clf(X, y, **kwargs):
    '''
        Trains a classifier with the entered data
        @param X: numpy.array of shape (m,n)
        @type X: Dataset
        @param y: Labels of the dataset
        @type y: numpy array of shape (m,)
        @keyword estimator: the full name of the algorithm to fit the dataset 
                            Should be any scikit-learn supervised algorithm 
                            that implements the fit() method.
                            E.g. 'sklearn.ensemble.RandomForestClassifier'
        @type estimator: string 
        @keyword param_grid: hyperparameters of the model to be optimized
        @type param_grid: dict
        @return: the classifier already fitted to the input data
    '''
    estimator = kwargs.get('estimator', __get_default_classifier())
    if kwargs['param_grid']:
        estimator = GridSearchCV(estimator, 
                                 kwargs['param_grid'], cv=3, score_func=f1_score)
    estimator.fit(X, y)
    return estimator

def __get_default_classifier():
    ''' Helper function that returns a default classifier'''
    clf = load_class_from_name('sklearn.ensemble.RandomForestClassifier')
    return clf(oob_score=True)

def save_clf(classifier, filename):
    ''' Saves a classifier to a file
        @param classifier: the classifier
        @param filename: the path where to save the classifier
    '''
    from sklearn.externals import joblib
    joblib.dump(classifier, filename, compress=9)


def load_clf(filename):
    '''Loads a classifier from a file
       @param filename: file path where to load the classifier
       @return: the loaded classifier. 
    '''
    from sklearn.externals import joblib
    loaded_model = joblib.load(filename)
    return loaded_model


def load_class_from_name(full_name):
    '''
        Returns an instance of a Python class from its qualified full name.

        Adapted from this SO Answer: http://stackoverflow.com/a/547867/630598
        @type full_name: string
        @param full_name: Class full name: foo.bar.klass
        @return: an instance of foo.bar.Klass. It has to be called just
        
        Example:
        --------
        >>> # Assume we already are in module foo.bar
        >>> Class Klass:
        >>>     __init__():
        >>>         print('klass instantiated')

        >>> my_class = load_class_from_name('foo.bar.Klass')
        >>> my_class()

        ... 'klass instantiated'

    '''
    module_name, klass_name = full_name.rsplit('.', 1)
    mod = __import__(module_name, fromlist=[klass_name])
    klass = getattr(mod, klass_name)
    return klass