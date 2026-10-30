"""Bounded local file operations. Local OS account access remains the trust boundary."""
import os
from pathlib import Path
import stat
from virtual_lab.pilots.schemas import PilotError


def checked_path(path):
    path = Path(os.path.abspath(Path(path).expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PilotError('UNSAFE_PATH', 'Symbolic links are not permitted in pilot paths')
    return path


def read_bounded(path, limit):
    path = checked_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise PilotError('UNSAFE_PATH', 'Expected a regular file')
            if info.st_size > limit:
                raise PilotError('SIZE_LIMIT', 'File exceeds the supported size limit')
            raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise PilotError('SIZE_LIMIT', 'File exceeds the supported size limit')
            return raw
    except OSError as exc:
        raise PilotError('FILE_ACCESS', 'Cannot read the selected local file') from exc


def write_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
