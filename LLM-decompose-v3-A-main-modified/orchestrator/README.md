# Orchestrator：确定性调用编排，不作语义判断

核心接口：

```python
from orchestrator.engine import run_record
from orchestrator.requests import RuntimeConfig
result = run_record(record, call, config)
```

call接收请求dict并返回`{"output": 模型JSON, "receipt": 真实回执}`。完整request/receipt合同见docs/INTEGRATION.md。回执必须包括request_id、client_request_id、request_sha256、execution_kind、实际model与effort，且不能标记截断。可用实际别名必须在配置allowlist中显式记录。宿主桥接器是信任边界，本模块不验证供应商签名。

engine.py执行G0→R0以及必要G1→R1；最多一次语义改写，最大技术重试按配置固定。freeze、bound review和commit严格对应。R1不接收旧finding或G1辩护。事件日志在外部调用前记录call_started，返回后记录成功/错误；不能将技术错误冒称源文语义缺陷。

requests.py只传授权字段，锁定模型、effort、generation_parameters、system、Schema、nonce与run_kind。compile.py实际装载共用标准和manifest中的15例，--check不改文件，默认显式编译。baseline不运行。

transport.py使用明确命令、stdin JSON、stdout单JSON、shell=False；stderr应由桥接器写到自己的诊断日志，stdout禁止进度文字。超时/非零退出/过大stdout/非JSON属于技术失败。超时不保证远端未收费；没有内置provider客户端、账户或模型名。

run.py提供串行批处理和可审计恢复：预检全体任务身份、exclusive锁、按任务身份命名结果、原子不覆盖写入、请求日志与结果checksum、整个实验manifest。--resume只允许相同记录集合/顺序、配置、提示词、Schema与runtime代码。未完成日志要显式--retry-incomplete；已完成结果包括技术回退不重新采样。

运行命令、真实桥接与离线fixture参照根README。run_record只返回编译结果，不运行导航。navigation_witness登记执行端真实instruction/prompt/token IDs，不能自己制造这些值。统计真实导航用evaluation，不以accepted充当成功。
