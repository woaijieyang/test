# 源码来源与适配

官方来源：https://github.com/GWxuan/AwareVLN
当前固定SHA：8f14eb8450cdd14ff4e3ba1ea04824255121e6be。
只读参考副本在upstream，实际运行源码在src并进入Git。保留llava/habitat_extensions/vlnce_baselines包名。导入程序生成原路径、目标路径及SHA清单。
必要补丁保存在patches，记录原始哈希、原因、回归和最终身份；不引入旧case1研究模块。保留上游Apache-2.0 LICENSE，依赖来源见THIRD_PARTY.md。实际验证状态见conclusion。

## 官方模型来源

权重来源为 https://huggingface.co/gwx22/AwareVLN-ck/tree/59149329064237529deb66862a11d21c139f4827/awarevln 。公开元数据已冻结到 configs/locks/model-source.json，共16个文件。现有全局文件的集合、大小及10个配置/tokenizer文件的Git blob身份已核对；六个权重文件的完整LFS SHA-256在freeze_model.py阶段核验。模型文件不复制或下载到Git，正式来源匹配以新环境预检回执为准。

## 本次实际适配

configs/source-import.json记录219个导入文件；configs/source-patches.json及patches记录4个实际源码文件的变更：模型配置注册别名、跨episode状态清理及证据采集、评测专用状态RPC、辅助动作中的等价NumPy float别名兼容。模型prompt、八帧采样、贪心解码和动作解析规则保留。

脚本层移除未被AwareVLN读取的辅助Oracle/数字instruction观测，避免RxR缺失geodesic_distance或tokens=None造成运行错误。指令仍直接取原episode文本，RGB/depth及评测measure不变。环境内官方Transformers/DeepSpeed替换与Habitat兼容修正由install_compatibility.py在独立环境应用，逐文件记录输出；pybind11缺失cstdint的原生补丁单独保留。所有变化以最终实际链路和独立审计验收，不以静态源码声明代替运行证明。
