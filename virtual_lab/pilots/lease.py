"""An OS-owned writer lease for a single local VirtualLab workspace.

The lock is released by the OS on process death. The lock file is never unlinked:
removing a live lock file would allow another process to lock a different inode.
This is local single-writer exclusion, not distributed access control.
"""
import os
from pathlib import Path
import stat

from virtual_lab.pilots.schemas import PilotError
from virtual_lab.pilots.storage import checked_path


class WorkspaceLease:
    def __init__(self, directory):
        self.directory = checked_path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._fd = None
        path = self.directory / '.workspace-writer.lock'
        checked_path(path)
        fd = None
        locking = False
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PilotError('UNSAFE_PATH', 'The workspace lock must be a regular file with one directory entry')
            locking = True
            if os.name == 'nt':
                import msvcrt
                if info.st_size == 0:
                    os.write(fd, b'\0')
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locking = False
                self.directory.chmod(0o700)
                os.fchmod(fd, 0o600)
            locking = False
            self._fd = fd
        except OSError as exc:
            if fd is not None:
                os.close(fd)
            import errno
            if locking and exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise PilotError('WORKSPACE_BUSY', 'This workspace is already open. Close its other VirtualLab window or select a different data directory.') from exc
            raise PilotError('WORKSPACE_ACCESS', 'Cannot obtain the local workspace writer lock') from exc
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise

    @property
    def active(self):
        return self._fd is not None

    def close(self):
        if self._fd is not None:
            fd, self._fd = self._fd, None
            # Closing the descriptor releases both flock and Windows byte locks.
            os.close(fd)

    def __enter__(self):
        if not self.active:
            raise PilotError('WORKSPACE_CLOSED', 'The workspace writer lock is closed')
        return self

    def __exit__(self, *_):
        self.close()
