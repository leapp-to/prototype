from leapp.utils.clicmd import command, command_opt


@command('modula')
@command_opt('whatever', action='append', help='Help')
def modula(args):
    print('<<<COMMAND>>>: Modula')
