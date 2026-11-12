"""Invoke an explicitly supplied local bridge. No shell, credentials or provider default."""
from __future__ import annotations
import subprocess
from typing import Callable
from contracts.common import canonical_json,parse_json,require,sha_text
from .requests import verify_request

def command_transport(argv: list[str], *, timeout_seconds: float=300, max_reply_bytes: int=8_000_000) -> Callable[[dict],dict]:
    require(isinstance(argv,list) and argv and all(isinstance(s,str) and s for s in argv),'Explicit bridge command required')
    require(timeout_seconds>0 and max_reply_bytes>0,'Invalid transport limits')
    def call(request: dict) -> dict:
        verify_request(request)
        try:
            p=subprocess.run(argv,input=canonical_json(request).encode('utf-8'),capture_output=True,check=False,
                             timeout=timeout_seconds,shell=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError('Model bridge timed out; its own logs may contain a billable completed request') from exc
        if p.returncode:
            raise RuntimeError(f'Model bridge exit status {p.returncode}; inspect its private stderr log (not copied to prompts)')
        if len(p.stdout)>max_reply_bytes:raise RuntimeError('Model bridge output exceeds the declared limit')
        reply=parse_json(p.stdout.decode('utf-8',errors='strict'))
        require(isinstance(reply,dict),'Bridge must return one JSON object, no fences or progress text on stdout')
        reply['transport_stdout_sha256']=sha_text(p.stdout.decode('utf-8'))
        return reply
    return call
