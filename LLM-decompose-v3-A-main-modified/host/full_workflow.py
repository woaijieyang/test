"""Frozen A workflow: main execution followed by the recorded technical recoveries."""
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import sys

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
import orchestrator.engine as engine
from contracts.common import ContractError, ProvenanceError

BASE_PREPARE = engine.prepare
BASE_REVIEW = engine.validate_review
PROFILES = ('main', 'format_diagnostic', 'specific_diagnostic', 'verified_source_suffix')
FORMAT_DIAGNOSTIC = (
    ' Technical formatting: the host preserves the original instruction outer whitespace. '
    'For multi-stage authored subtasks, each subtask must start and end with a non-whitespace character; '
    'do not append the source trailing space to a subtask. Preserve every route word and all '
    'original_instruction bytes. New EDIT gaps must be one ASCII space. Correct candidate formatting only.'
)
SPECIFIC_DIAGNOSTIC = (
    ' The rejected subtasks array contains an ASCII U+0020 AFTER the period of its final element. '
    'Remove that trailing whitespace from the SUBTASK ELEMENT; retain the identical original_instruction field. '
    'The renderer itself appends the original outer suffix.'
)


def run(record, transport, config, journal=None):
    """Call once per isolated process. Keep every profile and original receipt."""
    runs = []
    cache = {}

    def cached_call(request):
        import json
        key = json.dumps({k: request[k] for k in ('role', 'messages', 'output_schema', 'model', 'effort')}, sort_keys=True)
        if key not in cache:
            cache[key] = deepcopy(transport(request))
        answer = deepcopy(cache[key])
        answer['receipt']['client_request_id'] = request['client_request_id']
        answer['receipt']['request_sha256'] = request['request_sha256']
        return answer

    for profile in PROFILES:
        prepare = BASE_PREPARE
        if profile == 'verified_source_suffix':
            path = PACKAGE / 'recovery-history/renderer_A_final.py'
            assert hashlib.sha256(path.read_bytes()).hexdigest() == '616f011c050885f64deccae13636770f22c4463bc7d1da651a528c47ba2b15f9'
            spec = importlib.util.spec_from_file_location('a_final_suffix_renderer', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            prepare = module.prepare

        def prepared(source, candidate, **kwargs):
            try:
                return prepare(source, candidate, **kwargs)
            except ProvenanceError as error:
                suffix = FORMAT_DIAGNOSTIC
                if profile in ('specific_diagnostic', 'verified_source_suffix'):
                    suffix += SPECIFIC_DIAGNOSTIC
                raise ProvenanceError(str(error) + suffix) from error

        def reviewed(source, candidate, value):
            try:
                return BASE_REVIEW(source, candidate, value)
            except Exception as error:
                covered = {check for finding in value.get('findings', []) if finding.get('severity') == 'material'
                           for check in [finding.get('check_id'), *finding.get('related_check_ids', [])]}
                missing = [check for check, status in value.get('checklist', {}).items()
                           if status in ('issue', 'source_limited') and check not in covered]
                raise ContractError(str(error) + ' Checklist evidence coverage missing for ' + str(missing) +
                                    '. Ensure each flagged check is supported by a matching material finding check_id or related_check_ids. '
                                    'Reconcile your own evidence and checklist without inventing route facts.') from error

        engine.prepare = BASE_PREPARE if profile == 'main' else prepared
        engine.validate_review = reviewed if profile in ('specific_diagnostic', 'verified_source_suffix') else BASE_REVIEW
        try:
            output = engine.run_record(record, cached_call, config, journal=journal)
        finally:
            engine.prepare = BASE_PREPARE
            engine.validate_review = BASE_REVIEW
        output['host_profile'] = profile
        output['host_profile_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        renderer_path = (PACKAGE / 'recovery-history/renderer_A_final.py' if profile == 'verified_source_suffix'
                         else PACKAGE / 'renderer/freeze.py')
        output['effective_renderer_sha256'] = hashlib.sha256(renderer_path.read_bytes()).hexdigest()
        output['execution_override'] = {
            'renderer': renderer_path.relative_to(PACKAGE).as_posix(),
            'technical_format_diagnostic': profile != 'main',
            'review_checklist_diagnostic': profile in ('specific_diagnostic', 'verified_source_suffix'),
        }
        runs.append(output)
        if output['result']['state'] != 'fallback_technical_failure':
            break

    final = deepcopy(runs[-1])
    final['profile_history'] = runs
    return final
