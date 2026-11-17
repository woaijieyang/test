# LLM-decompose-v1

从服务器 /data/zy/vln/case1 运行。scripts/dispatch.py 是 CLI 和 API 共用的唯一派发入口。独立记录并行，记录内按 generator → reviewer → 必要时 generator 返修顺序执行。正式主审、回退确认和导航投放属于下游步骤。

|位置|用途|
|---|---|
|scripts/dispatch.py|编译单条输入、调度两个角色、校验 schema 和原文引用、断点恢复、写入待主审结果|
|backends/transport.py|已有 CLI 与 Responses API 调用、独立请求、回执、失败证据|
|generator/、reviewer/|原提示词、schema、10 个模板；generator/repair.md 用于同条返修|
|config/workflow.json|当前唯一生效的派发配置。默认 CLI，4 个 generator 和 4 个 reviewer，3 轮审核（初审加最多 2 次返修）|
|config/credentials.example.json|空值密钥样例。真实密钥只从环境变量或私有文件读取|
|tests/|本地离线验证|
|根目录的 plan.py 等模块|既有导航调用接口；Python 使用 importlib.import_module 加载带连字符的版本路径|
|config/workflow.legacy.toml、README.legacy.md|历史配置与说明，仅供复核|

## 运行

准备 UTF-8 JSONL，每行包含唯一的 record_id 和 original_instruction。例：

    {"record_id":"example-001","original_instruction":"Walk to the stairs and stop."}

从 case1 根目录运行，输入和输出路径换为本批实际位置：

    pkg=src/subtaskAdapter/LLM-decompose-v1
    runtime/awarevln/bin/python -B "$pkg/scripts/dispatch.py" --backend codex_cli --input outputs/instructions.jsonl --run outputs/subtaskAdapter/split-cli-v1

CLI 的 executable 可以是服务器已安装程序的绝对路径，默认查找 codex。每次调用启动全新的 codex exec，完整编译任务通过 stdin 传入。模型参数记录为 declared，子线程 ID 来自真实事件。当前 CLI 传输不会将命令行配置冒充服务端实际模型证明。正式实验如需证明实际模型和 effort，应核对对应会话元数据。

API 与 CLI 的输入、返修上限、角色并发和校验共用；API 使用独立 Responses 请求，store=false，不传 previous_response_id。先复制 config/workflow.json 为 config/workflow.local.json，默认模型为 gpt-6.1-sol，推理强度为 high；CLI 与 API 的 generator 和 reviewer 都继承这组配置。接入方须支持该模型与推理强度。使用下列两种密钥方式之一：

1. 默认从 VLN_SPLITTER_API_KEY 环境变量读取。在交互 shell 可使用 `read -rs VLN_SPLITTER_API_KEY; export VLN_SPLITTER_API_KEY` 隐藏输入。
2. 或者在 case1 建立私有目录，在本包 config/ 下使用被 Git 忽略的 credentials.local.json。先执行 `install -m 600 "$pkg/config/credentials.example.json" "$pkg/config/credentials.local.json"`（仅首次创建时），再用本地编辑器在 api_key 空字符串处填入值。将 workflow.local.json 的 responses.api_key_file 填为该文件的绝对路径，并清除同名环境变量。不得把密钥写进命令参数、workflow 文件、日志、正式输出或提交。不要打印凭据内容。

    runtime/awarevln/bin/python -B "$pkg/scripts/dispatch.py" --backend responses --config "$pkg/config/workflow.local.json" --input outputs/instructions.jsonl --run outputs/subtaskAdapter/split-api-v1

输出按 record_id 的 SHA-256 建目录，attempt0 为首轮。每个角色有 task、原始输出和 receipt；验证完成后才允许继续。reviewer 不通过才回传该条 candidate 和意见；返修次数用尽时建议保留原文。await_primary.json 是待主审记录。相同输入、配置和提示词复跑同一目录时复用已校验的回执，未收齐的调用保留为技术异常，需要核对后处理；同一 run 不可并发派发或切换模型。API 的 response_id 与 CLI 的 child_thread_id 分开记录。现有导航 plan.py 仍要求历史 CLI 审核凭据，本入口不直接发起导航。

离线检查：

    runtime/awarevln/bin/python -B "$pkg/tests/test_transport.py"
    runtime/awarevln/bin/python -B "$pkg/tests/test_dispatch.py"


## D 单条真实导航验收

固定样本为 R2R val_unseen episode 1015。此例复用已核验的单 episode 参考 manifest 和配置，仅更换 run 目录与新审核的静态语言输入，并显式校验两项已迁移源码的前后哈希。需要现有 Case1 数据、模型、冻结参考目录及保护运行时。每次复验选择一个从未使用的 RUN。

服务器从 /data/zy/vln/case1 开始：

    PKG=src/subtaskAdapter/LLM-decompose-v1
    PY=runtime/awarevln/bin/python
    RUN=outputs/subtaskAdapter/d-one-1015-$(date +%Y%m%d-%H%M%S)
    $PY -B "$PKG/scripts/verify_d_episode.py" source "$RUN"
    $PY -B "$PKG/scripts/dispatch.py" --backend codex_cli --input "$RUN/one.jsonl" --run "$RUN/language"

服务器有 Codex CLI 时使用上面的命令。本次使用已登录的 Windows CLI 运行相同版本的 dispatch.py，再将语言回执传回服务器。服务器无 CLI 时，把服务器生成的 one.jsonl 复制到 Windows case1 下同名 RUN，复制 config/workflow.json 为本轮 cli.json，只把 codex_cli.executable 改为 Windows 的 codex.cmd 绝对路径。Windows PowerShell 运行：

    $pkg = 'src/subtaskAdapter/LLM-decompose-v1'
    $run = 'outputs/subtaskAdapter/<替换为服务器本轮目录名>'
    & E:/APP/Anaconda/python.exe -X utf8 -B "$pkg/scripts/dispatch.py" --backend codex_cli --config "$run/cli.json" --input "$run/one.jsonl" --run "$run/language"
    scp -r "$run/language" "codex-server:/data/zy/vln/case1/$run/"

主对话逐条阅读原始指令、candidate 和 reviewer 输出。输出分别在 language/<record_hash>/attemptN/{generator,reviewer}/receipt.json 的 text 字段。只有主审确实同意，才登记以下显式决定。两个哈希使用本次已审阅 receipt 的 output_sha256；不要复制历史例子的哈希。出现 revise 或技术异常时保留该次尝试。

    cat "$RUN"/language/*/await_primary.json
    $PY -B "$PKG/scripts/verify_d_episode.py" approve "$RUN" --candidate-sha256 "$GEN_HASH" --reviewer-sha256 "$REV_HASH" --primary-id "$PRIMARY_ID" --note "$REVIEW_NOTE"
    bash scripts/with_runtime.sh "$PY" -B "$PKG/scripts/verify_d_episode.py" prepare "$RUN"
    LAUNCH=outputs/subtaskAdapter/llm-valunseen-A-def-20261104-r0/navigation-batch004/launcher-cached.py
    bash scripts/with_runtime.sh "$PY" -B "$LAUNCH" --run "$RUN/navigation" --gpu 4 --cpus 26,27 --execute
    bash scripts/with_runtime.sh "$PY" -B "$PKG/scripts/verify_d_episode.py" audit "$RUN"

GPU 和 CPU 只是本次使用的组合，复验时须通过当前资源准入。prepare 使用换行拼接并保留标点和空白；每次自然请求都携带同一文本。audit 用本地模型 tokenizer 从真实 prompt 重建输入 ID，对照模型实收 input_ids，核对每次 input-language-bindings 回执与结果轨迹哈希，并独立复算指标。最终证据位于 RUN/audit.json、RUN/navigation/trace/results.jsonl 和该行指向的 trace.jsonl。

2026-11-06 实测产物为 outputs/subtaskAdapter/d-one-1015-20261106-v1。生成与 reviewer 使用两个独立的 gpt-6.1-sol/high 会话，首轮主审通过，产出两段。40/40 次原生模型调用均通过文本与 token 重建，8 张图像槽位逐次有回执。原生模型 76 步后发出 STOP；独立复算 SR=0、SPL=0、nDTW=0.795870、NE=3.288295 m、Oracle SR=1。该次导航未成功，链路审计通过。
