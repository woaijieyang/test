"""A pair of authored reply fixtures passed through the real host. Offline; no model."""
from pathlib import Path
import json,sys
from adapter.source import from_record
from host.run import run_record
from shared.identity import canonical
HERE=Path(__file__).resolve().parent

def main():
    record=json.loads((HERE/'record.json').read_bytes());fixture=json.loads((HERE/'fixture_replies.json').read_bytes());
    def transport(q):
        # Test-only transport: deliberately does not infer or call any provider.
        assert q['phase'] in ('initial','review');return {'output':fixture[q['role']],'receipt':{'model':'offline-fixture','effort':'none','request_id':'demo-'+q['role']}}
    result=run_record(from_record(record),transport,pins={r:{'model':'offline-fixture','effort':'none'} for r in ['generator','reviewer']});assert result['disposition']=='accepted_candidate';print(json.dumps({k:result[k] for k in ['disposition','render_mode','instruction','instruction_sha256','semantic_correctness_verified','navigation_evaluated']},ensure_ascii=False,indent=2));return result
if __name__=='__main__':main()
