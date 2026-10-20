"""Linux write confinement, inherited by exec/fork; read-only global assets remain readable."""

import ctypes, os, platform
from pathlib import Path

O_PATH = getattr(os, "O_PATH", 0o10000000)  # Linux asm-generic/fcntl.h; absent in this CPython 3.10 build.
WRITE_FILE = 1 << 1
WRITE_BITS = sum(1 << i for i in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def restrict(writable):
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("Unsupported Landlock platform")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("Landlock ABI >=3 required, got " + str(abi))
    rules = Ruleset(WRITE_BITS)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    try:
        for p in writable:
            p = Path(p).resolve()
            pfd = os.open(p, O_PATH | os.O_CLOEXEC)
            try:
                rule = PathBeneath(WRITE_BITS if p.is_dir() else WRITE_FILE, pfd)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) < 0:
                    raise OSError(ctypes.get_errno(), "landlock_add_rule " + str(p))
            finally:
                os.close(pfd)
        if libc.prctl(38, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
        if libc.syscall(446, fd, 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    finally:
        os.close(fd)
    return int(abi)
