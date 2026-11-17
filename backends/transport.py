"""Provider-neutral, one-task transport. No semantic review or navigation state."""
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Protocol
import hashlib
import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Task:
    role: str
    compiled_prompt: str
    schema: dict

    def validate(self):
        if self.role not in ('generator', 'reviewer') or not self.compiled_prompt.strip():
            raise ValueError('INVALID_SINGLE_RECORD_TASK')
        if not isinstance(self.schema, dict) or self.schema.get('type') != 'object':
            raise ValueError('INVALID_OUTPUT_SCHEMA')


@dataclass(frozen=True)
class Result:
    text: str
    backend: str
    declared_model: str
    declared_effort: str
    reported_model: str | None
    reported_effort: str | None
    response_id: str | None
    child_thread_id: str | None
    usage: dict | None
    evidence: str


class Backend(Protocol):
    def complete(self, task: Task, directory: Path) -> Result: ...


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('API_REDIRECT_REJECTED')


class ResponsesBackend:
    def __init__(self, *, endpoint, api_key_env, model, effort, api_key_file='', timeout_seconds=300,
                 max_output_tokens=8192, structured_output=False, send=None):
        url = urlsplit(endpoint)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('HTTPS_ENDPOINT_WITHOUT_EMBEDDED_CREDENTIALS_REQUIRED')
        if not model or not api_key_env or timeout_seconds <= 0 or max_output_tokens <= 0:
            raise ValueError('INVALID_API_CONFIGURATION')
        self.endpoint, self.api_key_env, self.model, self.effort = endpoint, api_key_env, model, effort
        self.api_key_file = api_key_file
        self.timeout, self.limit, self.structured = timeout_seconds, max_output_tokens, structured_output
        self.send = send or self._send

    def _key(self):
        key = os.environ.get(self.api_key_env)
        if self.api_key_file:
            if key:
                raise RuntimeError('AMBIGUOUS_KEY_SOURCES')
            path = Path(self.api_key_file)
            if not path.is_absolute() or path.is_symlink():
                raise RuntimeError('KEY_FILE_REQUIRES_ABSOLUTE_NON_SYMLINK_PATH')
            try:
                if os.name != 'nt' and path.stat().st_mode & 0o077:
                    raise ValueError('private permissions required')
                if path.stat().st_size > 16384:
                    raise ValueError('oversized key file')
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(data, dict) or set(data) != {'api_key'}:
                    raise ValueError('invalid key file schema')
                key = data['api_key']
            except Exception:
                raise RuntimeError('KEY_FILE_INVALID_OR_NOT_PRIVATE') from None
        if not key:
            raise RuntimeError('MISSING_API_KEY_ENVIRONMENT_VARIABLE')
        if not isinstance(key, str) or key != key.strip() or any(c.isspace() for c in key):
            raise RuntimeError('INVALID_KEY_VALUE')
        return key

    def _send(self, payload):
        key = self._key()
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def complete(self, task, directory):
        # Single isolated input. No previous_response_id, conversation, tools or source metadata.
        payload = dict(model=self.model, input=task.compiled_prompt, store=False,
                       max_output_tokens=self.limit)
        if self.effort:
            payload['reasoning'] = dict(effort=self.effort)
        if self.structured:
            payload['text'] = dict(format=dict(type='json_schema', name=task.role,
                                              schema=task.schema, strict=True))
        write_new(directory/'request.json', payload)
        try:
            response = self.send(payload)  # Exactly one network attempt; no hidden retry.
        except Exception:
            # Suppress exception chaining: a provider error can echo authorization headers.
            raise RuntimeError('API_TRANSPORT_FAILED_DETAILS_REDACTED') from None
        key = self._key() if self.api_key_file else os.environ.get(self.api_key_env)
        if key and key in json.dumps(response, ensure_ascii=False):
            raise RuntimeError('API_RESPONSE_CONTAINS_SECRET_NOT_SAVED')
        write_new(directory/'response.json', response)
        if response.get('status') != 'completed':
            raise RuntimeError('API_RESPONSE_NOT_COMPLETED')
        blocks = [b for item in response.get('output', []) if item.get('type') == 'message'
                  for b in item.get('content', [])]
        if any(b.get('type') == 'refusal' for b in blocks):
            raise RuntimeError('API_REFUSAL')
        texts = [b['text'] for b in blocks if b.get('type') == 'output_text']
        if len(texts) != 1 or not response.get('id') or not response.get('model'):
            raise RuntimeError('API_OUTPUT_OR_IDENTITY_MISSING')
        return Result(texts[0], 'responses', self.model, self.effort,
                      response['model'], (response.get('reasoning') or {}).get('effort'),
                      response['id'], None, response.get('usage'), 'response.json')


class CodexCLIBackend:
    def __init__(self, *, executable, model, effort, cwd):
        self.executable, self.model, self.effort, self.cwd = executable, model, effort, Path(cwd)

    def complete(self, task, directory):
        output = directory/'output.txt'
        args = [self.executable, 'exec', '-m', self.model, '-c',
                'model_reasoning_effort='+json.dumps(self.effort), '-c', 'approval_policy="never"',
                '--sandbox', 'read-only', '--skip-git-repo-check', '--json', '--color', 'never',
                '--output-last-message', str(output), '-']
        write_new(directory/'request.json', dict(argv=args, input=task.compiled_prompt))
        with (directory/'events.jsonl').open('x', encoding='utf-8') as stdout, \
             (directory/'stderr.txt').open('x', encoding='utf-8') as stderr:
            p = subprocess.Popen(args, cwd=self.cwd, stdin=subprocess.PIPE, stdout=stdout,
                                 stderr=stderr, text=True, encoding='utf-8')
            write_new(directory/'process.json', dict(pid=p.pid, started_at=time.time()))
            p.communicate(task.compiled_prompt)
        write_new(directory/'exit.json', dict(exit_code=p.returncode))
        if p.returncode:
            raise RuntimeError('CLI_TECHNICAL_FAILURE')
        events = [json.loads(line) for line in (directory/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        tid = next((e['thread_id'] for e in events if e.get('type') == 'thread.started'), None)
        if not tid or not any(e.get('type') == 'turn.completed' for e in events):
            raise RuntimeError('CLI_TERMINAL_OR_THREAD_MISSING')
        # CLI flags alone do not prove actual model/effort. Host must bind real session metadata.
        return Result(output.read_text(encoding='utf-8'), 'codex_cli', self.model, self.effort,
                      None, None, None, tid, None, 'events.jsonl; MODEL_UNVERIFIED until session audit')


def execute_once(backend: Backend, task: Task, directory: Path, validate: Callable):
    """Exclusive attempt directory; validator must enforce original schema AND source quotes.

    Returns a structurally checked candidate/reviewer result, never primary acceptance.
    A timeout/disconnect is execution-unknown, not proof that the request never ran.
    """
    task.validate()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.time()
    write_new(directory/'task.json', dict(role=task.role, compiled_prompt=task.compiled_prompt,
        compiled_prompt_sha256=digest(task.compiled_prompt.encode('utf-8')),
        schema_sha256=digest(json.dumps(task.schema, sort_keys=True).encode('utf-8'))))
    try:
        result = backend.complete(task, directory)
        write_new(directory/'receipt.json', dict(**asdict(result), elapsed_seconds=time.time()-started,
            output_sha256=digest(result.text.encode('utf-8')), primary_accepted=False))
        value = json.loads(result.text)
        validate(value)
        write_new(directory/'validation.json', dict(status='STRUCTURE_AND_SOURCE_CHECKED_NOT_SEMANTIC_PASS'))
        return result
    except Exception as exc:
        # No exception string, headers or key value in failure receipts.
        write_new(directory/'failure.json', dict(error_type=type(exc).__name__,
            execution_status='UNKNOWN_OR_FAILED_REQUIRES_RECONCILIATION',
            elapsed_seconds=time.time()-started, automatic_retry=False, primary_accepted=False))
        raise
