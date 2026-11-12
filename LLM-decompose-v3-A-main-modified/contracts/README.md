# Contracts：统一标准与技术一致性

execution_standard.md是generator/reviewer共同加载的唯一执行标准。Schema分布在对应角色目录；本目录validate.py执行跨字段一致性、引文、索引、阶段/边界覆盖、quality/checklist/finding关系、反馈ID等检查。

检查通过只说明结构与被引用字符串存在。程序不能证明英语蕴含、物理可达、真实完成，也不根据关键字替代generator分割。一个证据串存在并不意味着它支持model的解释。

common.py统一UTF-8、严格JSON和哈希：拒绝重复JSON键、NaN、Infinity，不静默规范化原文。canonical_json用于结构化身份，不声称等于真实tokenizer或服务端prompt格式。

三维质量与实质finding相互一致；一个根因允许关联多个检查/维度。实际候选缺失的要素不能只在审核摘要补全后pass。可选建议允许与pass共存，不触发强制返修。candidate与repair的ok/needs_review、空数组、issues和逐finding独立判断都有合同检查。
