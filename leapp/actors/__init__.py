import logging
import os
import sys


from leapp.compat import string_types
from leapp.exceptions import MissingActorAttributeError, WrongAttributeTypeError
from leapp.models import Model
from leapp.tags import Tag
from leapp.utils.meta import get_flattened_subclasses
from leapp.models.error_severity import ErrorSeverity


class Actor(object):
    """
    The Actor class represents the smallest step in the workflow. It defines what kind
    of data it expects, it consumes (processes) the given data, and it produces data for other
    actors in the workflow.
    """

    ErrorSeverity = ErrorSeverity
    """ Convenience forward for the :py:class:`leapp.models.error_severity.ErrorSeverity` constants. """

    name = None
    """ Name of the actor that is used to identify data or messages created by the actor. """

    description = None
    """ More verbose actor's description."""

    consumes = ()
    """
    Tuple of :py:class:`leapp.models.Model` derived classes defined in the :ref:`repositories <terminology:repository>`
    that define :ref:`messages <terminology:message>` the actor consumes.
    """

    produces = ()
    """
    Tuple of :py:class:`leapp.models.Model` derived classes defined in the :ref:`repositories <terminology:repository>`
    that define :ref:`messages <terminology:message>` the actor produces.
    """

    tags = ()
    """
    Tuple of :py:class:`leapp.tags.Tag` derived classes by which :ref:`workflow <terminology:workflow>`
    :ref:`phases <terminology:phase>` select actors for execution.
    """

    def __init__(self, messaging=None, logger=None):
        self._messaging = messaging
        self.log = (logger or logging.getLogger('leapp.actors')).getChild(self.name)
        """ A configured logger instance for the current actor. """

    @property
    def actor_files_paths(self):
        """
        Returns the file paths that are bundled with the actor. (Path to the content of the actor's file directory).
        """
        return os.getenv("LEAPP_FILES", "").split(":")

    @property
    def files_paths(self):
        """ Returns all actor file paths related to the actor and common actors file paths. """
        return self.actor_files_paths + self.common_files_paths

    @property
    def common_files_paths(self):
        """ Returns all common repository file paths. """
        return os.getenv("LEAPP_COMMON_FILES", "").split(":")

    def get_folder_path(self, name):
        """
        Finds the first matching folder path within :py:attr:`files_paths`.

        :param name: Name of the folder
        :type name: str
        :return: Found folder path
        :rtype: str or None
        """
        for path in self.files_paths:
            path = os.path.join(path, name)
            if os.path.isdir(path):
                return path
        return None

    def get_file_path(self, name):
        """
        Finds the first matching file path within :py:attr:`files_paths`.

        :param name: Name of the file
        :type name: str
        :return: Found file path
        :rtype: str or None
        """
        for path in self.files_paths:
            path = os.path.join(path, name)
            if os.path.isfile(path):
                return path
        return None

    def run(self, *args):
        """ Runs the actor calling the method :py:func:`process`. """
        os.environ['LEAPP_CURRENT_ACTOR'] = self.name
        try:
            self.process(*args)
        finally:
            os.environ.pop('LEAPP_CURRENT_ACTOR', None)

    def process(self, *args, **kwargs):
        """ Main processing method. In inherited actors, the function needs to be defined to be able to be processed."""
        raise NotImplementedError()

    def produce(self, *models):
        """
        By calling produce, model instances are stored as messages. Those messages can be then consumed by other actors.

        :param models: Messages to be sent (those model types have to be specified in :py:attr:`produces`
        :type models: Variable number of the derived classes from :py:class:`leapp.models.Model`
        """
        if self._messaging:
            for model in models:
                if isinstance(model, type(self).produces):
                    self._messaging.produce(model, self)

    def consume(self, *models):
        """
        Retrieve messages specified in the actors :py:attr:`consumes` attribute, and filter message types by
        models.

        :param models: Models to use as a filter for the messages to return
        :type models: Variable number of the derived classes from :py:class:`leapp.models.Model`
        """
        if self._messaging:
            return self._messaging.consume(self, *models)
        return ()

    def report_error(self, message, severity=ErrorSeverity.ERROR, details=None):
        """
        Reports an execution error

        :param message: A message to print the possible error
        :type message: str
        :param severity: Severity of the error default :py:attr:`leapp.messaging.errors.ErrorSeverity.ERROR`
        :type severity: str with defined values from :py:attr:`leapp.messaging.errors.ErrorSeverity.ERROR`
        :param details: A dictionary where additional context information is passed along with the error
        :type details: dict
        :return: None
        """
        if self._messaging:
            if not ErrorSeverity.validate(severity):
                self.log.warning("report_error: Unknown severity value %s was passed - Falling back to ERROR", severity)
                severity = ErrorSeverity.ERROR
            self._messaging.report_error(
                message=message,
                severity=severity,
                actor=self,
                details=details)


def _is_type(value_type):
    def validate(actor, name, value):
        if not isinstance(value, value_type):
            raise WrongAttributeTypeError('Actor {} attribute {} should be of the type {}'.format(actor, name, value_type))
        return value
    return validate


def _is_tuple_of(value_type):
    def validate(actor, name, value):
        _is_type(tuple)(actor, name, value)
        if not value:
            raise WrongAttributeTypeError(
                'Actor {} attribute {} should contain at least one item of the type {}'.format(actor, name, value_type))
        if not all(map(lambda item: isinstance(item, value_type), value)):
            raise WrongAttributeTypeError(
                'Actor {} attribute {} should contain only values of the type {}'.format(actor, name, value_type))
        return value
    return validate


def _is_model_tuple(actor, name, value):
    if isinstance(value, type) and issubclass(value, Model):
        logging.getLogger("leapp.linter").warning("Actor %s field %s should be a tuple of Models.", actor, name)
        value = value,
    _is_type(tuple)(actor, name, value)
    if not all([True] + list(map(lambda item: isinstance(item, type) and issubclass(item, Model), value))):
        raise WrongAttributeTypeError(
            'Actor {} attribute {} should contain only Models'.format(actor, name))
    return value


def _is_tag_tuple(actor, name, value):
    if isinstance(value, type) and issubclass(value, Tag):
        logging.getLogger("leapp.linter").warning("Actor %s field %s should be a tuple of Tags.", actor, name)
        value = value,
    _is_type(tuple)(actor, name, value)
    if not all([True] + list(map(lambda item: isinstance(item, type) and issubclass(item, Tag), value))):
        raise WrongAttributeTypeError(
            'Actor {} attribute {} should contain only Tags'.format(actor, name))
    return value


def _get_attribute(actor, name, validator, required=False, default_value=None):
    value = getattr(actor, name, None)
    if not value and required:
        raise MissingActorAttributeError('Actor {} is missing attribute {}'.format(actor, name))
    value = validator(actor, name, value)
    if not value and default_value is not None:
        value = default_value
    return name, value


def get_actor_metadata(actor):
    """
    Creates Actor's metadata dictionary

    :param actor: Actor whose metadata are needed
    :type actor: derived class from :py:class:`leapp.actors.Actor`
    :return: Dictionary with the name, tags, consumes, produces, and description of the actor
    """
    return dict([
        ('class_name', actor.__name__),
        ('path', os.path.dirname(sys.modules[actor.__module__].__file__)),
        _get_attribute(actor, 'name', _is_type(string_types), required=True),
        _get_attribute(actor, 'tags', _is_tag_tuple, required=True),
        _get_attribute(actor, 'consumes', _is_model_tuple, required=False, default_value=()),
        _get_attribute(actor, 'produces', _is_model_tuple, required=False, default_value=()),
        _get_attribute(actor, 'description', _is_type(string_types), required=False,
                       default_value='There has been no description provided for this actor.')
    ])


def get_actors():
    """
    :return: All registered actors with their metadata
    """
    actors = get_flattened_subclasses(Actor)
    for actor in actors:
        get_actor_metadata(actor)
    return actors
