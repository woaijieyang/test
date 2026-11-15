# 本次核查的外部依据（2026-11-08）

以下为主张对应的原始论文/官方文档入口。方法适配不等于复现其训练模型和分数。

1. Ferraz et al. LLM Self-Correction with DeCRIM. Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.458/ — 约束提取、核查、修复。
2. Saha et al. Learning to Plan & Reason for Evaluation with Thinking-LLM-as-a-Judge. ICML2025. https://proceedings.mlr.press/v267/saha25b.html — 评价计划与评价执行分离；模型经过训练。
3. Zhou et al. Evaluating Judges as Evaluators: JETTS. ICML2025. https://proceedings.mlr.press/v267/zhou25af.html — critique应按实际修复效果评估。
4. Seleznyov et al. When Punctuation Matters. Findings of EMNLP2025. https://aclanthology.org/2025.findings-emnlp.1109/ — 格式扰动与鲁棒性实验。
5. Hua et al. Flaw or Artifact? Rethinking Prompt Sensitivity. EMNLP2025. https://aclanthology.org/2025.emnlp-main.1006/ — 区分真实敏感性与评价伪影。
6. Hong et al. Sub-Instruction Aware Vision-and-Language Navigation. EMNLP2020. https://aclanthology.org/2020.emnlp-main.271/ — 既有子指令、路径对齐与阶段切换。
7. Ku et al. Room-Across-Room. EMNLP2020. https://aclanthology.org/2020.emnlp-main.356/ — RxR可见实体描述与时空对齐。
8. Xin et al. Instruction Decomposition and Action Alignment for Vision-and-Language Navigation. ICML2026. https://proceedings.mlr.press/v306/xin26a.html — 语义分解与动作对齐的相关研究。
9. Hugging Face Tokenizers: Pre-tokenizers. https://huggingface.co/docs/tokenizers/v0.23.3/en/api/pre-tokenizers — 空白/前缀空格与预分词接口。它不证明用户checkpoint采用其中哪一具体设置，实际tokenizer必须读取部署版本。

检索未确认“只针对R2R/RxR段边界与原生空白的完整研究”是否已有穷尽覆盖，不能声称首次。未以二手博客替代论文结果，也没有为本项目执行上述仓库。
