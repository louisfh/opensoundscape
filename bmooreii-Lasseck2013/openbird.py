#!/usr/bin/env python
''' openbird.py -- OpenBird
Usage:
    openbird.py [-hv]
    openbird.py sampling <dir> [-i <ini>]
    openbird.py spect_gen <file> [-i <ini>]
    openbird.py view <file> [-i <ini>]
    openbird.py model_fit <dir> [-i <ini>]
    openbird.py prediction <model> <dir> [-i <ini>]

Positional Arguments:
    <file>             e.g. 'train/001.wav'
    <dir>              e.g. 'nips4b/'

Options:
    -h --help           Print this screen and exit
    -v --version        Print the version of crc-squeue.py
    -i --ini <ini>      Specify a different ini file [default: openbird.ini]
'''


def generate_config(section):
    '''Get the configuration section

    Simply return a ConfigParser containing the INI section.
    Access elements via `config.get{float,boolean,int}('key')`.

    Args:
        section: The parent section of the INI file

    Returns:
        A ConfigParser instance 

    Raises:
        FileNotFoundError if INI file doesn't exist
    '''
    if isfile(arguments['--ini']):
        config = ConfigParser()
        config.read(arguments['--ini'])
        return config[section]
    else:
        raise FileNotFoundError("File: {} doesn't exist!".format(arguments['--ini']))


from docopt import docopt
from configparser import ConfigParser
from os.path import isfile
from os.path import split as path_split
from glob import glob
from modules.sampling import sampling
from modules.spect_gen import spect_gen
from modules.view import view
from modules.model_fit import model_fit

# From the docstring, generate the arguments dictionary
arguments = docopt(__doc__, version='openbird.py version 0.0.1')

# Get the default config variables
defaults = generate_config('default')

if arguments['sampling']:
    # Preprocess the file with the defaults
    sampling(arguments['<file>'], defaults)

elif arguments['spect_gen']:
    # Preprocess the file with the defaults
    spect_gen(arguments['<file>'], defaults)

elif arguments['view']:
    # Preprocess the file with the defaults
    view(arguments['<file>'], defaults)

elif arguments['model_fit']:
    # Using defined algorithm, create model
    model_fit(arguments['<dir>'], defaults)

elif arguments['prediction']:
    prediction(arguments['<dir>'], defaults)
