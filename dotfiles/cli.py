import click

from .exceptions import DotfileException
from .repository import Repositories


def single(repos):
    """Raise an exception if multiple repositories are provided.

    Certain operations (add, remove, etc...) can only be applied to a
    single repository while other operations (list) can be applied
    across multiple repositories.
    """
    if len(repos) > 1:
        raise click.BadParameter('Must specify exactly one repository.',
                                 param_hint=['-r', '--repo'])
    return repos[0]


def confirm(method, files, repo):
    """Return a list of files, or all files if none were specified.

    When no files are specified, all files are assumed.  But before we
    go ahead, confirm to make sure this is the intended operation.
    """
    if files:
        # user has specified specific files, so we are not assuming all
        return files
    # no files provided, so we assume all files after confirmation
    message = 'Are you sure you want to %s all dotfiles?' % method
    click.confirm(message, abort=True)
    return str(repo).split()


def show(repo, state):
    """TODO"""
    for dotfile in repo.contents():
        try:
            display = state[dotfile.state]
        except KeyError:
            continue
        char  = display['char']
        name = dotfile.short_name(repo.home)
        fg = display.get('color', None)
        bg = display.get('bg', None)
        bold = display.get('bold', False)
        click.secho('{0:5s}: {1}'.format(char, name), fg=fg, bg=bg,
                    bold=bold)


def perform(method, files, repo, copy, debug):
    """Perform an operation on one or more dotfiles."""
    for dotfile in repo.dotfiles(files):
        try:
            getattr(dotfile, method)(copy, debug)
            if not debug:
                msg = '%s%s' % (method, 'd' if method[-1] == 'e' else 'ed')
                click.secho('%s %s' % (msg, dotfile.short_name(repo.home)),
                            fg='green')
        except DotfileException as err:
            click.secho(str(err), fg='red', bg='white')


pass_repos = click.make_pass_decorator(Repositories)
CONTEXT_SETTINGS = dict(auto_envvar_prefix='DOTFILES',
                        help_option_names=['-h', '--help'])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--repos', '-r', type=click.Path(), multiple=True,
              help='Repository locations.', default=['~/Dotfiles'],
              show_default=True)
@click.version_option(None, '-v', '--version')
@click.pass_context
def cli(ctx, repos):
    """Dotfiles is a tool to make managing your dotfile symlinks in $HOME easy,
    allowing you to keep all your dotfiles in a single directory.
    """

    # temporary notice for folks tracking git
    import os
    if os.environ.get('DOTFILES_REPO'):
        click.echo("Error: repository variable has changed to \"DOTFILES_REPOS\", please update")
        exit(-1)

    try:
        ctx.obj = Repositories(repos)
    except FileNotFoundError as e:
        raise click.ClickException('Directory not found: %s' % e)


@cli.command()
@click.option('-c', '--copy',  is_flag=True,
              help='Copy files instead of creating symlinks.')
@click.option('-d', '--debug', is_flag=True,
              help='Show what would be executed.')
@click.argument('files', nargs=-1, type=click.Path())
@pass_repos
def add(repos, copy, debug, files):
    """Add dotfiles to a repository."""
    repo = single(repos)
    perform('add', files, repo, copy, debug)


@cli.command()
@click.option('-d', '--debug', is_flag=True,
              help='Show what would be executed.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@pass_repos
def remove(repos, debug, files):
    """Remove dotfiles from a repository."""
    repo = single(repos)
    files = confirm('remove', files, repo)
    perform('remove', files, repo, False, debug)
    if not debug:
        # pruning will remove any remaining empty directories
        repo.prune()


@cli.command()
@click.option('-a', '--all',   is_flag=True, help='Show all dotfiles.')
# @click.option('-c', '--color', is_flag=True, help='Enable color output.')
@pass_repos
def status(repos, all, color=True):
    """Show current status of dotfiles.

    By default only non-OK dotfiles are shown.  This can be overridden
    with the '-a, --all' flag.

    Legend:

      l: symlink  c: copy  e: external symlink

      ?: missing  !: conflict

    Meaning:

      * Missing: Not found in your home directory.

      * Conflict: Different from the file in your home directory.

    By default, color output is enabled. this will have no effect if 
    the terminal does not have ANSI support.
    """
    bold = True if all and not color else False
    state = {
        'missing':  {'char': 'Miss', 'bold': bold},
        'conflict': {'char': 'Confl', 'bold': bold},
    }

    if all:
        state['link'] = {'char': 'Link',
                         'color': 'green'}
        state['copy'] = {'char': 'Copy',
                         'color': 'blue'}
        state['external'] = {'char': 'Extern',
                             'color': 'cyan'}

    # if color:
    # By default, always show missing and conflict files
    state['missing'].update({'color': 'yellow',
                              'bg': 'white'})
    state['conflict'].update({'color': 'red',
                              'bg': 'white'})

    for repo in repos:
        show(repo, state)

@cli.command()
@click.option("-d", "--debug", is_flag=True,
              help="Show what would be executed.")
@click.option("-f", "--forced", is_flag=True,
              help="Force overwrite of conflicting files")
@click.option('-c', '--copy',  is_flag=True,
              help='Copy files instead of creating symlinks.')
@pass_repos
def sync(repos, copy, debug, forced):
    """Syncronize missing and conflicting files
    
    """
    if len(repos) > 1:
        raise NotImplementedError("Not able to treat more than 1 repos for now")

    repo, = repos
    # Check the missing and conflicting files
    missing_dotfiles = []
    conflict_dotfiles = []
    for dotfile in repo.contents():
        state = dotfile.state
        if state == "missing":
            missing_dotfiles.append(dotfile.name)
        elif state == "conflict":
            conflict_dotfiles.append(dotfile.name)

    # Missing files
    if not forced:
        perform("sync", missing_dotfiles, repo, copy, debug)
        if len(conflict_dotfiles) > 0:
            click.echo("Conflicting files not synced. Overwrite them with --forced option")
        if not debug:
            click.echo("\nSyncronized {0:d} missing files.".format(len(missing_dotfiles)))

    else:
    # Conflicting only when forced
        perform("sync", missing_dotfiles + conflict_dotfiles,
                repo, copy, debug)
        if not debug:
            click.echo(("\nSyncronized {0:d} missing "
                       "and {1:d} conflicting files.").format(len(missing_dotfiles),
                                                                                           len(conflict_dotfiles)))



@cli.command()
@click.option('-c', '--copy',  is_flag=True,
              help='Copy files instead of creating symlinks.')
@click.option('-d', '--debug', is_flag=True,
              help='Show what would be executed.')
@click.argument('files', nargs=-1, type=click.Path())
@pass_repos
def enable(repos, copy, debug, files):
    """Link dotfiles into your home directory."""
    repo = single(repos)
    files = confirm('enable', files, repo)
    perform('enable', files, repo, copy, debug)


@cli.command()
@click.option('-d', '--debug', is_flag=True,
              help='Show what would be executed.')
@click.argument('files', nargs=-1, type=click.Path())
@pass_repos
def disable(repos, debug, files):
    """Unlink dotfiles from your home directory."""
    repo = single(repos)
    files = confirm('disable', files, repo)
    perform('disable', files, repo, False, debug)
