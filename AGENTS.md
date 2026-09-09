# AGENTS.md

`efny-pipeline` 仓库的 AI 协作执行规则。

本仓库用于科研分析与可复现研究开发。优先保证科学正确性、分析透明性和代码可读性，而不是面向任意用户构建通用软件。

本仓库将 `ARCHITECTURE.md` 视为稳定目录结构的唯一事实来源；除非用户明确要求，否则不要提出结构性改动。

## 1. Basic workflow

1) 在规划或编辑前，先阅读项目根目录下的 `ARCHITECTURE.md`。
2) 仅按 `PLAN.md` 或用户的明确指令执行变更。
3) 若变更影响代码的用法或结构，需同步更新 `README.md`。
3.1) 只要代码被修改或生成了新结果，必须新增或更新补充文档进行说明。
3.2) 运行时间短且不需并行的脚本可直接执行；否则在同环境做少量验证，并提供提交命令或 sbatch 脚本（读取`docs/cluster_usage.md`规则）。
4) 当任务修改代码、修改项目文档、运行分析、生成结果，
   或形成影响后续分析的重要决策时，
   在 `docs/sessions/` 下新增或更新当天日志。
   单纯阅读、解释、代码审查或回答问题时，不要求创建 session log。
5) 只要修改了代码或文档，需要进行 git commit。
6) 若使用 `create-plan` 技能，需将计划写入仓库根目录 `PLAN.md`。

## 2. Scope

- 默认范围为仅文档，除非用户明确要求工程改动。
- 不要修改 `data/` 或 `outputs/` 下的运行时产物。
- 非用户明确要求时，不要改动目录命名或结构。
- 保持最小差异；避免与当前请求无关的重构。
- 验证后立即清理 `temp/` 下临时冒烟测试产物（如 `temp/smoke_*`），不要在仓库中残留测试垃圾。

## 3. Scientific coding style

本项目是科研分析代码库，不是通用软件包或生产服务。

代码应优先：

1. scientific correctness
2. readability
3. reproducibility
4. explicit analysis logic
5. minimal implementation

正式脚本内全部使用英文。

优先使用：

- 函数式 / 面向过程代码
- 少量具有明确数据语义的 `dataclass`
- 显式的数据流和统计操作
- 简单、局部、容易检查的函数

避免：

- 不必要的 class hierarchy
- manager / handler / wrapper 等抽象层
- 不要仅为了抽象少量代码而创建只使用一次的 helper function；
  如果函数对应明确的科学操作、提高可读性或便于验证，则可以保留。
- speculative abstraction
- premature generalization
- 与当前分析无关的配置系统
- 为未来可能需求预留接口
- 不计算、保存或比较文件内容 SHA-256，也不将哈希一致性作为 manifest、QC 或流程就绪条件；应使用科学语义检查和必要的来源信息。

如果三行清晰代码可以解决问题，不要创建一个新的 abstraction。

### Comments and docstrings

- 重要函数必须有简洁、准确的 docstring，说明其科学目的、关键输入输出，以及适用时的单位、
  时间零点或分析假设。
- 对不直观但会影响科学含义的实现添加少量行内注释，重点解释为什么采用该规则，而不是复述
  代码正在执行什么操作。
- 简单工具函数和显而易见的语句不要求逐行注释；避免冗余、过时或无法由代码验证的叙述性注释。
- 正式脚本中的 docstring 和代码注释统一使用英文。

## 4. Validation and error handling

采用 fail fast and fail loudly 原则。

默认假设：

- 输入数据符合项目已记录的数据格式；
- 上游 pipeline 已正常完成；
- 内部函数按照约定方式调用；
- 配置文件和 `ARCHITECTURE.md` 中定义的路径正确。

不要为这些已知前置条件重复添加防御式检查。

只有当检查能够防止 **silent scientific error** 时才添加 validation，例如：

- subject / sample 顺序错位；
- BOLD volume 与 event / confound 时间轴错位；
- feature 与 label 对应错误；
- atlas / ROI 数量违反分析假设；
- train/test data leakage；
- array orientation 会改变统计含义；
- 必需实验条件缺失。

对于简单 scientific invariant，优先使用简洁的 `assert`。

除非用户明确要求，不要添加：

- 重复的文件存在性检查；
- 内部函数的重复类型检查；
- 已由上游保证的 shape 检查；
- broad `try/except`；
- catch-all exception handling；
- fallback code paths；
- 自动寻找备用文件；
- 自动猜测列名或输入格式；
- silent skipping；
- silent coercion；
- 自动删除异常 subject / trial / row；
- 自动填充 NaN；
- 自动修改输入数据以避免报错。

如果数据违反分析假设，应明确报错，而不是猜测用户意图后继续运行。

## 5. Dependencies and environment

- 统一使用 `uv` 管理 Python 依赖。
- 项目虚拟环境固定为仓库根目录 `.venv`。
- 新增依赖使用：

  ```bash
  uv add <package>
  ```
- 不要直接使用 pip install 修改项目环境。
- 优先使用项目已有依赖，不要为了少量功能新增依赖。
- 避免临时 sys.path hack。
- 如果入口脚本确实无法避免 sys.path 调整，只允许在入口脚本中使用，并用简短注释说明原因。

## 6. Documentation

- 使用精确、科学的表述。
- `docs/` 下文档全部使用中文，文件名保持英文。
- 仓库根目录文件夹名称保持英文。

### Output organization

运行产物应按其生产模块组织，不要将新文件直接平铺到共享输出目录。

- 新产物默认写入 `outputs/<type>/<module>/`，例如 `outputs/tables/variability/`。
- 每个产物应有明确的生产模块；跨模块分析应建立独立分析模块，而不是随意归入某个已有模块。
- 输出路径应使用项目已有的统一配置或路径常量；不要在不同脚本中重复硬编码输出目录。
- 修改输出路径时，应同步修改生产端和所有直接依赖该路径的读取代码，不保留静默读取旧路径的兼容回退。
- 清理或覆盖结果时，只能操作当前模块明确拥有的输出目录。

具体目录结构以 `ARCHITECTURE.md` 为准。
