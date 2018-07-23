import pandas as pd
import numpy as np
from modules.db_utils import cursor_item_to_data
from modules.db_utils import cursor_item_to_stats
from modules.db_utils import read_spectrogram
from modules.db_utils import return_cursor
from modules.db_utils import write_file_stats
from modules.db_utils import write_model
from modules.spect_gen import spect_gen
from modules.view import extract_segments
from modules.utils import return_cpu_count
from modules.image_utils import apply_gaussian_filter
from scipy import stats
from cv2 import matchTemplate, minMaxLoc
from concurrent.futures import ProcessPoolExecutor
import progressbar
from itertools import repeat
from copy import copy
import json
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.model_selection import GridSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.metrics import confusion_matrix
from sklearn.metrics import recall_score
from sklearn.metrics import precision_score
from sklearn.metrics import f1_score


def file_stats(label, config):
    '''Generate the first order statistics

    Given a single label, generate the statistics for the corresponding file

    Args:
        label: A file label from the training set
        config: The parsed ini configuration

    Returns:
        The bounding box DF, spectrogram, and normalization factor for the input
        label

    Raises:
        Nothing.
    '''

    # Generate the df, spectrogram, and normalization factor
    # -> Read from MongoDB or preprocess
    if config['general'].getboolean('db_rw'):
        df, spec, normal = read_spectrogram(label, config)
    else:
        df, spec, normal = spect_gen(label, config)

    # Generate the Raw Spectrogram
    raw_spec = spec * normal

    # Raw Spectrogram Stats
    raw_spec_stats = stats.describe(raw_spec, axis=None)

    # Frequency Band Stats
    freq_bands = np.array_split(raw_spec, config['model_fit'].getint('num_frequency_bands'))
    freq_bands_stats = [None] * len(freq_bands)
    for idx, band in enumerate(freq_bands):
        freq_bands_stats[idx] = stats.describe(band, axis=None)

    # Segment Statistics
    df['width'] = df['x_max'] - df['x_min']
    df['height'] = df['y_max'] - df['y_min']
    df_stats = df[['width', 'height', 'y_min']].describe()

    # Generate the file_row
    # Raw Spectrogram Stats First
    row = np.array([raw_spec_stats.minmax[0], raw_spec_stats.minmax[1],
        raw_spec_stats.mean, raw_spec_stats.variance])

    # Followed by the band statistics
    row = np.append(row, [[s.minmax[0], s.minmax[1], s.mean, s.variance]
        for s in freq_bands_stats])

    # Finally the segment statistics
    # -> If the len(df_stats) == 2, it contains no segments append zeros
    if len(df_stats) == 2:
        row = np.append(row, np.zeros((3, 4)))
    else:
        row = np.append(row, (df_stats.loc['min'].values,
            df_stats.loc['max'].values,
            df_stats.loc['mean'].values,
            df_stats.loc['std'].values))

    # The row is now a complicated object, need to flatten it
    row = np.ravel(row)

    return df, spec, normal, row


def file_file_stats(df_one, spec_one, normal_one, labels_df, config):
    '''Generate the second order statistics

    Given a df, spec, and normal for label_one, generate the file-file statistics
    for all files (or downselect w/ template_pool.csv file)

    Args:
        monotonic_idx_one: The monotonic index for df_one
        df_one: The bounding box dataframe for label_one
        spec_one: The spectrum for label_one
        normal_one: The normalization factor for label_one
        labels_df: All other labels
        config: The parsed ini configuration

    Returns:
        match_stats_dict: A dictionary which contains template matching statistics
         of all segments in labels_df slid over spec_one. Keys are the labels

    Raises:
        Nothing.
    '''

    # Get the MongoDB Cursor, indices is a Pandas Index object -> list
    # -> If template_pool defined:
    # -> 1. Generate a pools dataframe and convert string to [int]
    # -> 2. Read items from template_pool_db if necessary
    if config['general'].getboolean('db_rw'):
        if config['model_fit']['template_pool']:
            pools_df = pd.read_csv(config['model_fit']['template_pool'], index_col=0)
            pools_df.templates = pools_df.templates.apply(lambda x: json.loads(x))

            if config['model_fit']['template_pool_db']:
                items = return_cursor(pools_df.index.values.tolist(),
                    'spectrograms', config, config['model_fit']['template_pool_db'])
            else:
                items = return_cursor(pools_df.index.values.tolist(),
                    'spectrograms', config)
        else:
            items = return_cursor(labels_df.index.values.tolist(),
                'spectrograms', config)
    else:
        items = {'label': x for x in labels_df.index.values.tolist()}

    match_stats_dict = {}

    # Iterate through the cursor
    for item in items:
        # Need to get the index for match_stats
        idx_two = item['label']
        # monotonic_idx_two, = np.where(get_segments_from == idx_two)
        # monotonic_idx_two = monotonic_idx_two[0]

        if config['general'].getboolean('db_rw'):
            df_two, spec_two, normal_two = cursor_item_to_data(item, config)
        else:
            df_two, spec_two, normal_two = spect_gen(idx_two, config)

        spec_two = apply_gaussian_filter(spec_two, config['model_fit']['gaussian_filter_sigma'])

        # Extract segments
        # -> If using template_pool, downselect the dataframe before extracting segments
        if config['model_fit']['template_pool']:
            df_two = df_two.iloc[pools_df.loc[idx_two].values[0]]
        df_two['segments'] = extract_segments(spec_two, df_two)

        # Generate the np.array to append
        match_stats_dict[idx_two] = np.zeros((df_two.shape[0], 3))

        # Slide segments over all other spectrograms
        frequency_buffer = config['model_fit'].getint('template_match_frequency_buffer')
        for idx, (_, item) in enumerate(df_two.iterrows()):
            # Determine minimum y target
            y_min_target = 0
            if item['y_min'] > frequency_buffer:
                y_min_target = item['y_min'] - frequency_buffer

            # Determine maximum y target
            y_max_target = spec_two.shape[0]
            if item['y_max'] < spec_two.shape[0] - frequency_buffer:
                y_max_target = item['y_max'] + frequency_buffer

            # If the template is small enough, do the following:
            # -> Match the template against the stripe of spec_one with the 5th
            # -> algorithm of matchTemplate, then grab the max correllation
            # -> max location x value, and max location y value
            if y_max_target - y_min_target <= spec_one.shape[0] and \
                item['x_max'] - item['x_min'] <= spec_one.shape[1]:
                output_stats = matchTemplate(
                    spec_one[y_min_target: y_max_target, :], item['segments'], 5)
                min_val, max_val, min_loc, max_loc = minMaxLoc(output_stats)
                match_stats_dict[idx_two][idx][0] = max_val
                match_stats_dict[idx_two][idx][1] = max_loc[0]
                match_stats_dict[idx_two][idx][2] = max_loc[1] + y_min_target
    return match_stats_dict


def run_stats(idx_one, labels_df, config):
    '''Wrapper for parallel stats execution

    Run within a parallel executor to generate file and file-file Statistics
    for a given label.

    Args:
        idx_one: The label for the file
        labels_df: Passed through to `file_file_stats` function
        config: The parsed ini file for this run

    Returns:
        Nothing, writes to MongoDB

    Raises:
        Nothing.
    '''
    monotonic_idx_one = labels_df.index.get_loc(idx_one)
    df_one, spec_one, normal_one, row_f = file_stats(idx_one, config)
    # Blur spec_one before feeding to file_file_stats
    spec_one = apply_gaussian_filter(spec_one, config['model_fit']['gaussian_filter_sigma'])
    match_stats = file_file_stats(df_one, spec_one, normal_one, labels_df, config)
    write_file_stats(idx_one, row_f, match_stats, config)


def build_X_y(labels_df, config):
    '''Build X and y from labels_df

    Build X and y to fit a DecisionTree Classifier

    Args:
        labels_df: labels dataframe for this particular bird

    Returns:
        X: dataframe containing data to fit on
        y: series containing the labels

    Raises:
        Nothing.
    '''

    if config['model_fit']['template_pool']:
        pools_df = pd.read_csv(config['model_fit']['template_pool'], index_col=0)
        pools_df.templates = pools_df.templates.apply(lambda x: json.loads(x))
        get_file_file_stats_for = [x for x in pools_df.index]
    else:
        get_file_file_stats_for = [x for x in labels_df.index if labels_df[x] == 1]

    items = return_cursor(labels_df.index.values.tolist(), 'statistics', config)

    file_stats = [None] * labels_df.shape[0]
    file_file_stats = [None] * labels_df.shape[0]
    for item in items:
        mono_idx = labels_df.index.get_loc(item['label'])
        file_stats[mono_idx], file_file_stats[mono_idx] = cursor_item_to_stats(item)
        file_file_stats[mono_idx] = [file_file_stats[mono_idx][x] for x in get_file_file_stats_for]

    # Shape: (num_files, 80), 80 is number of file statistics
    # -> sometimes garbage data in file_stats
    file_stats = np.nan_to_num(np.array(file_stats))

    # Reshape file_file_stats into 3D numpy array
    # -> (num_files, num_templates, 3), 3 is the number of file-file statistics
    _tmp = [None] * labels_df.shape[0]
    for o_idx, _ in enumerate(file_file_stats):
        _tmp[o_idx] = np.vstack([file_file_stats[o_idx][x] for x in
            range(len(file_file_stats[o_idx]))])
    file_file_stats = np.array(_tmp)

    return pd.DataFrame(np.hstack(
        (file_stats, file_file_stats.reshape(file_file_stats.shape[0], -1)))), pd.Series(labels_df.values)


def fit_model(X, y, config):
    '''Fit model on X, y

    Given X, y perform train/test split, scaling, and model fitting

    Args:
        X: dataframe containing model data
        y: labels series

    Returns:
        model: The sklearn model

    Raises:
        Nothing.
    '''
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.33,
        stratify=y)

    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    classifier = RandomForestClassifier()

    params = {
        "n_estimators": [config['model_fit'].getint('n_estimators')],
        "max_features": [config['model_fit'].getint('max_features')],
        "min_samples_split": [config['model_fit'].getint('min_samples_split')]
    }

    grid_search = GridSearchCV(classifier, params, cv=y_train.sum(), n_jobs=1)
    grid_search.fit(X_train, y_train)

    y_train_pred = grid_search.best_estimator_.predict(X_train)
    y_test_pred = grid_search.best_estimator_.predict(X_test)
    print("ROC AUC Train: {}".format(roc_auc_score(y_train, y_train_pred)))
    print("ROC AUC Test: {}".format(roc_auc_score(y_test, y_test_pred)))
    print("Precision Train: {}".format(precision_score(y_train, y_train_pred)))
    print("Precision Test: {}".format(precision_score(y_test, y_test_pred)))
    print("Recall Train: {}".format(recall_score(y_train, y_train_pred)))
    print("Recall Test: {}".format(recall_score(y_test, y_test_pred)))
    print("F1 Score Train: {}".format(f1_score(y_train, y_train_pred)))
    print("F1 Score Test: {}".format(f1_score(y_test, y_test_pred)))
    print("Confusion Matrix Train:")
    print(confusion_matrix(y_train, y_train_pred))
    print("Confusion Matrix Test:")
    print(confusion_matrix(y_test, y_test_pred))
    return grid_search.best_estimator_, scaler


def model_fit_algo(config):
    '''Fit the lasseck2013 model

    We were directed here from model_fit to fit the lasseck2013 model.

    Args:
        config: The parsed ini file for this run

    Returns:
        Something or possibly writes to MongoDB

    Raises:
        Nothing.
    '''

    # First, we need labels and files
    labels_df = pd.read_csv("{}/{}".format(config['general']['data_dir'],
        config['general']['train_file']), index_col=0)

    # Get the processor counts
    nprocs = return_cpu_count(config)

    # For each file, we need to create a new DF with first and second order
    # statistics
    with progressbar.ProgressBar(max_value=labels_df.shape[0]) as bar:
        with ProcessPoolExecutor(nprocs) as executor:
            for idx, ret in zip(np.arange(labels_df.shape[0]),
                    executor.map(run_stats, labels_df.index,
                        repeat(labels_df), repeat(config))):
                bar.update(idx)

    # Serial code for debugging
    # print("Running serial code...")
    # for idx, item in enumerate(labels_df.index):
    #     run_stats(item, labels_df, config)
    #
    # Now that file stats are available, build the models in parallel
    for bird in labels_df.columns:
        X, y = build_X_y(labels_df[bird], config)
        # print("Bird: {}".format(bird))
        # print("---")
        model, scaler = fit_model(X, y, config)
        write_model(bird, model, scaler, config)
