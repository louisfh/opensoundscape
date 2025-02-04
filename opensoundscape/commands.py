#!/usr/bin/env python3
from subprocess import Popen, PIPE, DEVNULL
from shlex import split


def run_command(cmd):
    """ Run a command returning output, error

    Args:
        cmd: A string containing some command

    Returns:
        (stdout, stderr): A tuple of standard out and standard error
    """

    return Popen(split(cmd), stdout=PIPE, stderr=PIPE).communicate()


def run_command_return_code(cmd):
    """ Run a command returning the return code

    Args:
        cmd: A string containing some command

    Returns:
        return_code: The return code of the function
    """
    proc = Popen(split(cmd), stdout=DEVNULL, stderr=DEVNULL)
    proc.communicate()
    return proc.returncode
