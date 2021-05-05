from leapp.utils.clicmd import command, command_opt


@command('wuzzap')
@command_opt('whatever', action='append', help='Help')
def wuzzap(args):
    print('<<<COMMAND>>>: Wuzzap')
