from __future__ import print_function

import datetime
import os
import sys

from leapp.exceptions import CommandError, LeappError
from leapp.logger import configure_logger
from leapp.repository.scan import find_and_scan_repositories
from leapp.snactor.commands.workflow import workflow
from leapp.snactor.context import with_snactor_context
from leapp.utils.clicmd import command_arg, command_opt
from leapp.utils.output import beautify_actor_exception, report_deprecations, report_errors
from leapp.utils.repository import find_repository_basedir, requires_repository

_LONG_DESCRIPTION = '''
Executes the given workflow.

Using --until-phase the workflow will be only executed until including
the given phase.

Using --until-actor the workflow will be only executed until including
the first occurrence of the given actor name.

For more information please consider reading the documentation at:
https://red.ht/leapp-docs
'''


@workflow.command('run', help='Execute a workflow with the given name', description=_LONG_DESCRIPTION)
@command_arg('name')
@command_opt('until-phase', help='Runs until including the given phase but then exits')
@command_opt('until-actor', help='Runs until including the given actor but then exits')
@command_opt('save-output', is_flag=True,
             help='Saves the output for actors to be consumable when executed with snactor run')
@command_opt('--whitelist-experimental', action='append', metavar='ActorName',
             help='Enables experimental actors')
@requires_repository
def cli(params):
    def impl(context=None):
        start = datetime.datetime.utcnow()
        configure_logger()
        repository = find_and_scan_repositories(find_repository_basedir('.'), include_locals=True)
        try:
            repository.load()
        except LeappError as exc:
            sys.stderr.write(exc.message)
            sys.stderr.write('\n')
            sys.exit(1)

        wf = repository.lookup_workflow(params.name)
        if not wf:
            raise CommandError('Could not find any workflow named "{}"'.format(params.name))

        instance = wf()
        for actor_name in params.whitelist_experimental or ():
            actor = repository.lookup_actor(actor_name)
            if actor:
                instance.whitelist_experimental_actor(actor)

        with beautify_actor_exception():
            instance.run(context=context, until_phase=params.until_phase, until_actor=params.until_actor)

        report_errors(instance.errors)
        report_deprecations(os.getenv('LEAPP_EXECUTION_ID'), start=start)

        if instance.failure:
            sys.exit(1)

    @with_snactor_context
    def snactor_context_impl():
        impl(context=os.getenv('LEAPP_EXECUTION_ID'))

    if params.save_output:
        snactor_context_impl()
    else:
        impl()
