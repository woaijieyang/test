"""Storage APIs;ownership metadata remains stdlib-only for trusted launchers."""
__all__=['EpisodeStore','SnapshotReader','load_episode']
def __getattr__(name):
    if name in __all__:
        from . import store
        return getattr(store,name)
    raise AttributeError(name)
