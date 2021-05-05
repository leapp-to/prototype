import pkgutil


class LeappLibrariesFinder(object):
    """
    Implements functionality to dynamically load libraries for actors.
    """

    def __init__(self, module_prefix, paths, name=None):
        """
        :param module_prefix: Prefix string such as 'leapp.libraries.common' or 'leapp.libraries.actor' which is used
                              to filter the modules to handle with this finder.
        :type module_prefix: str
        :param paths: List of paths to search for the matching libraries
        :type paths: List or Tuple
        """
        self._paths = paths
        self._prefix = module_prefix
        self._name = name

    def _implementation(self, method, fullname, path):  # noqa; pylint: disable=unused-argument
        if not fullname.startswith(self._prefix + '.'):
            return None
        module = fullname.split('.')[-1]
        for loader, name, ispkg in pkgutil.iter_modules(self._paths):
            if ispkg and self._name:
                return getattr(loader, method)('{}.{}'.format(self._prefix, self._name))
            if name == module:
                return getattr(loader, method)(fullname)

    def find_spec(self, fullname, path, target=None):  # noqa; pylint: disable=unused-argument
        """ Implementation for python >=3.4 """
        return self._implementation(method='find_spec', fullname=fullname, path=path)

    def find_module(self, fullname, path=None):
        """ Implementation for python <3.4 """
        return self._implementation(method='find_module', fullname=fullname, path=path)
