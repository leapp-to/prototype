import pkgutil
import os
import socket
import sys

from leapp import VERSION
from leapp.cli import commands
from leapp.config import get_config
from leapp.utils.clicmd import command
from leapp.utils.libraryfinder import LeappLibrariesFinder
from leapp.utils.repository import find_repos, get_repository_name


@command('')
def cli(args):  # noqa; pylint: disable=unused-argument
    """
        Top level base command dummy function
    """


def _load_commands(base_command):
    pkgdir = os.path.dirname(commands.__file__)
    for entry in os.listdir(pkgdir):
        entry_path = os.path.join(pkgdir, entry)
        if os.path.isdir(entry_path) and os.path.isfile(os.path.join(entry_path, '__init__.py')):
            # We found a package
            package_name = 'leapp.cli.commands.{}'.format(entry)
            package = pkgutil.get_loader(package_name).load_module(package_name)
            register = getattr(package, 'register', None)
            if callable(register):
                register(base_command)


def main():
    """
    leapp entry point
    """
    os.environ['LEAPP_HOSTNAME'] = socket.getfqdn()
    _load_commands(cli.command)
    cli.command.execute('leapp version {}'.format(VERSION))
