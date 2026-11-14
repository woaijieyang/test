"""Graph memory injection. Heavy host and private-worker imports are role-local."""
from .protocol import FrozenMemoryRead, retrieval_settings, sample_native_rgb

__all__ = ["FrozenMemoryRead", "retrieval_settings", "sample_native_rgb", "HostInjection", "WorkerRetrieval"]


def __getattr__(name):
    if name == "HostInjection":
        from .host_decision import HostInjection
        return HostInjection
    if name == "WorkerRetrieval":
        from .session import WorkerRetrieval
        return WorkerRetrieval
    raise AttributeError(name)
