"""Additional structural checks only on the RxR production path.

Shared schemas and R2R behavior stay unchanged. These checks do not infer
navigation semantics, choose targets or certify natural-language entailment.
"""
from __future__ import annotations

from host import protocol


def _accepted(candidate):
    if candidate['status'] != 'ok':
        return
    expected = [(i, i + 1) for i in range(len(candidate['subtasks']) - 1)]
    actual = [(h['from_subtask_index'], h['to_subtask_index']) for h in candidate['handoffs']]
    protocol.check(actual == expected,
                   'RxR accepted candidate must cover each adjacent handoff exactly once in order',
                   code='RXR_HANDOFF_SEQUENCE_INVALID', path='/handoffs',
                   expected=expected, actual=actual)
    for i, stage in enumerate(candidate['stage_audit']):
        target = stage['target']
        protocol.check(isinstance(target['text'], str) and bool(target['text'].strip())
                       and bool(target['candidate_quotes']),
                       'RxR accepted audit must identify its source-supported objective; it may be a movement or orientation, not necessarily an object',
                       code='RXR_TARGET_EVIDENCE_MISSING',
                       path=f'/stage_audit/{i}/target', stage_index=i)


def generator(source, candidate):
    protocol.generator(source, candidate)
    _accepted(candidate)


def feedback(source, review, answer):
    protocol.feedback(source, review, answer)
    _accepted(answer['candidate'])
