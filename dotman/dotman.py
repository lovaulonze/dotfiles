import os

from click import echo, secho
from hashlib import md5
from pathlib import Path
from shutil import copyfile, SameFileError

from .exceptions import \
    IsSymlink, NotASymlink, Exists, NotFound, Dangling, \
    TargetExists, TargetMissing, InRepository

UNUSED = False


def _move_echo(source, target):
    secho('MOVE  {0} -> {1}'.format(source, target), fg='yellow')


def _copy_echo(source, target):
    secho('COPY  {0} -> {1}'.format(source, target), fg='cyan')


def _link_echo(source, target):
    secho('LINK  {0} -> {1}'.format(source, target), fg='green')


def _mkdir_echo(source):
    secho('MKDIR  {0}'.format(source), fg='black')


def _unlink_echo(source):
    secho('UNLINK  {0}'.format(source), fg='magenta')


class Dotfile(object):
    """A configuration file managed within a repository.

    :param name:   name of the symlink in the home directory (~/.vimrc)
    :param target: where the symlink should point to (~/Dotfiles/vimrc)
    """
    RELATIVE_SYMLINKS = False

    def __init__(self, name, target):
        # if not name.is_file() and not name.is_symlink():
        #     raise NotFound(name)
        self.name = Path(name)
        self.target = Path(target)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return '<Dotfile %r>' % self.name

    def _ensure_dirs(self, debug):
        """Ensure the directories for both name and target are in place.

        This is needed for the 'add' and 'link' operations where the
        directory structure is expected to exist.
        """
        def ensure(dir, debug):
            if not dir.is_dir():
                if debug:
                    _mkdir_echo(dir)
                else:
                    dir.mkdir(parents=True)

        ensure(self.name.parent, debug)
        ensure(self.target.parent, debug)

    def _prune_dirs(self, debug):
        # TODO
        if debug:
            secho('PRUNE  <TODO>', fg='magenta', blink=True)

    def _link(self, debug, home):
        """Create a symlink from name to target, no error checking.
        If file is a symlink to another file,
        copy its true identity to the target
        This feature is desired when using VCS like git etc..
        """
        source = self.name
        target = self.target

        if self.name.is_symlink():
            # source = self.target
            # target = self.name.resolve()
            source_true_identity = self.name.resolve()
            # Often there are bad symlink files that cannot be found
            # Copy only when the true identify exists
            if source_true_identity.exists():
                if debug:
                    _copy_echo(source_true_identity, target)
                else:
                    copyfile(source_true_identity, target)

            if debug:
                _unlink_echo(source)
            else:
                source.unlink()

        elif self.RELATIVE_SYMLINKS:
            target = os.path.relpath(target, source.parent)

        if debug:
            _link_echo(source, target)
        else:
            self._ensure_dirs(debug)
            source.symlink_to(target)

    def _copy(self, debug):
        """Copy the file from name to target without error checking.
        If source file is symlink, do nothing
        """
        source = self.name
        target = self.target

        if self.name.is_symlink():
            raise IsSymlink(self.name.as_posix())
        

        if debug:
            _copy_echo(source, target)
        else:
            self._ensure_dirs(debug)
            try:
                copyfile(source.as_posix(), target.as_posix())
            except SameFileError:
                raise

    def _unlink(self, debug):
        """Remove a symlink in the home directory, no error checking."""
        if debug:
            _unlink_echo(self.name)
        else:
            self.name.unlink()

    def short_name(self, home):
        """A shorter, more readable name given a home directory."""
        return self.name.relative_to(home)

    def _is_present(self):
        """Is this dotfile present in the repository?"""
        return self.name.is_symlink() and (self.name.resolve() == self.target)

    def _same_contents(self):
        return (md5(self.name.read_bytes()).hexdigest() ==
                md5(self.target.read_bytes()).hexdigest())

    def _source_is_newer(self):
        def _ctime(p):
            return p.stat().st_ctime
        return _ctime(self.name) > _ctime(self.target)

    @property
    def state(self):
        """The current state of this dotfile."""
        if self.target.is_symlink():
            return dict(code='external')

        if not self.name.exists():
            # no $HOME file or symlink
            return dict(code='missing')

        if self.name.is_symlink():
            # name exists, is a link, but isn't a link to the target
            if not self.name.samefile(self.target):
                return dict(code='conflict',
                            msg="Source and target links are not same file!")
            return dict(code='link')

        if not self._same_contents():
            # name exists, is a file, but differs from the target
            # TODO: return the status of newer files
            if self._source_is_newer():
                msg=("       The version in your home path is newer. \n"
                     "       Run dotfiles add -cf ~/{0} to overwrite.".
                     format(self.name))
            else:
                msg=("       The version in Dotfiles repo is newer. \n"
                     "       Run dotfiles sync -f {0} to overwrite.".
                     format(self.name))
            return dict(code='conflict',
                        msg=msg)

        return dict(code='copy')

    def add(self, copy=False, debug=False, home=Path.home()):
        """Move a dotfile to its target and create a link.

        The link is either a symlink or a copy.
        """
        if copy:                # Copy to file
            self._copy(debug)
        else:                   # Symlink to target
            if self._is_present():
                raise InRepository(self.short_name(home))
            if self.target.exists():
                raise TargetExists(self.name)
            self._ensure_dirs(debug)
            if not self.name.is_symlink():
                if debug:
                    _move_echo(self.name, self.target)
                else:
                    self.name.replace(self.target)
            self._link(debug, home)

    def remove(self, copy=UNUSED, debug=False):
        """Remove a dotfile and move target to its original location."""
        if not self.name.is_symlink():
            raise NotASymlink(self.name)
        if not self.target.is_file():
            raise TargetMissing(self.name)
        self._unlink(debug)
        if debug:
            _move_echo(self.target, self.name)
        else:
            self.target.replace(self.name)

    def sync(self, copy=False, debug=False, home=Path.home()):
        """ Syncronize missing or conflicting files, no checking
        forced option determined inside cli.sync() method
        """
        state = self.state["code"]
        if state not in ("missing", "conflict"):
            raise ValueError(("Something's wrong with the cli.sync method. "
                              "Should only work on missing and conflicting files"))
        # If conflicting files, remove the ones in home folder
        """TODO backup"""
        # print(self.name, self.state)
        if copy is False:       # only symlink method
            if state == "conflict":
                self._unlink(debug)
            self._ensure_dirs(debug)
            self._link(debug, home)
        else:
            self._copy()

    def enable(self, copy=False, debug=False, home=Path.home()):
        """Create a symlink or copy from name to target."""
        if copy:
            raise NotImplementedError()
        if self.name.exists():
            raise Exists(self.name)
        if not self.target.exists():
            raise TargetMissing(self.name)
        self._ensure_dirs(debug)
        self._link(debug, home)

    def disable(self, copy=UNUSED, debug=False):
        """Remove a dotfile from name to target."""
        if not self.name.is_symlink():
            raise NotASymlink(self.name)
        if self.name.exists():
            if not self.target.exists():
                raise TargetMissing(self.name)
            if not self.name.samefile(self.target):
                raise RuntimeError
        self._unlink(debug)
        self._prune_dirs(debug)
