"""One-way deterministic suggestion stage, with no simulator state mutation."""
class GuardedPrefix:
    def __init__(self, actions):
        if any(type(a) is not int or a not in (1,2,3) for a in actions):
            raise ValueError('Only native movement primitives may enter the prefix')
        self.actions=tuple(actions)
        self.consumed=0
        self.reason=None

    def propose(self, preview, accept=None):
        if self.reason is not None:return None
        if self.consumed==len(self.actions):
            self.reason='source_exhausted';return None
        action=self.actions[self.consumed]
        predicted=preview(action)
        if predicted is None:
            self.reason='proposal_rejected';return None
        if accept is not None:
            reason=accept(action,predicted)
            if reason is not None:
                self.reason=reason;return None
        self.consumed+=1
        return action,predicted
