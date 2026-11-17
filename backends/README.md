# 调用后端

transport.py 实现 CLI 和 Responses API 的单次请求、独占尝试目录、请求回执和失败记录。两种入口都由 ../scripts/dispatch.py 调用，工作流参数集中在 ../config/workflow.json，密钥填入规则和服务器命令见 ../README.md。每轮通过独立上下文发送单条完整任务；API 返回 response_id，CLI 返回 child_thread_id。
