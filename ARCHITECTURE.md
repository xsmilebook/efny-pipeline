# Project Structure

正式流程和推荐入口见 `README.md`，本地与集群执行约定见 `docs/cluster_usage.md`。
当前使用 `scripts/` 下的专用入口；目录结构与输出归属以本文为准。
下列目录约定保留原有命名，尚未使用的目录及 `PLAN.md`、方法文档不要求提前创建。

```
efny-pipeline/                  # 项目根目录
├── README.md                   # 项目简介与快速入口
├── AGENTS.md                   # AI 协作与修改约束
├── PLAN.md                     # 计划与任务拆解
├── ARCHITECTURE.md             # 结构说明（本文）
├── configs/                    # 项目配置文件
│   └── neuroimaging.json        # THU/XY 影像输入、集群根目录、工具与分析参数
│
├── docs/                       # 方法、流程与决策记录
│   ├── data_dictionary.md      # 数据字典（数据说明）
│   ├── workflow.md             # 可复现流程（预留）
│   ├── cluster_usage.md        # 本地与集群开发、环境和 Slurm 约定
│   ├── neuroimaging_preprocessing.md # 静息态 fMRIPrep、XCP-D、头动与 FC
│   ├── methods.md              # 方法学细节
│   ├── reports/                # 研究计划、阶段性总结与正式文档
│   └── sessions/               # 会话记录
│
├── src/                        # 可复用模块（不含硬编码路径）
│   ├── imaging/                # 影像预处理与影像指标提取
│   │   ├── config.py           # 统一配置与模块输出路径
│   │   ├── pipeline.py         # 输入清单、Slurm 提交与结果完成审计入口
│   │   └── rest.py             # 头动 QC 与被试级 CIFTI 功能连接
│   ├── behavior/               # 行为任务与人口学预处理
│   └── inventory/              # 问卷与量表处理（预留）
│
├── scripts/                    # 执行入口（本地/HPC/主流程脚本）
│   ├── neuroimaging/           # fMRIPrep／XCP-D 完整命令及四阶段 sbatch 入口
│   ├── behavior/
│   └── inventory/              # 量表处理入口（预留）
│
│
├── data/                       # 项目分析数据（不纳入版本控制），用于存放数据型对象：预处理结果、connectivity matrix、analysis-ready tables
│   ├── external/               # 外部第三方输入
│   ├── raw/                    # 原始输入（非脚本产出）
│   │   ├── app_data/       # 原始的行为任务数据
│   │   ├── inventory/      # 原始的量表数据
│   │   ├── neuroimaging/
│   │   │   ├── BIDS/       # 原始 BIDS 影像数据
│   │   │   ├── PHYSIO/     # 原始生理日志（预留）
│   │   │   └── PSYCH/      # 心理任务原始文件（预留）
│   │   └── metadata/
│   ├── interim/                # 中间衍生结果
│   └── processed/              # 可复用清洗结果
│
├── outputs/                    # 运行产物（不纳入版本控制）；各类型下必须继续按生产模块分目录
│   ├── figures/                # 图形；按生产模块分目录
│   ├── tables/                 # CSV/XLSX 表格；共享根目录不直接放文件
│   ├── logs/                   # JSON manifest 与作业日志；采用与生产模块相同的层级
│   ├── results/                # 模型等非表格结果；按生产模块分目录
│   └── reports/                # 正式交付附件；继续按报告模块组织
│
├── tests/                      # 合成数据的科学定向验证
└── notebooks/                  # 探索性分析（不纳入版本控制）
```

`outputs/<type>/` 是共享类型根目录，不是生产模块。新增产物必须进入上述模块目录；若新增
跨模块分析，应先在本节登记其独立模块。生产端与直接读取端必须共同使用配置或路径常量中
记录的新路径，不读取旧的平铺位置作为兼容回退。模块级清理只能删除该模块拥有的目录。

当前序列目录清单由 `neuroimaging/series_folder_inventory` 生产，分别写入
`outputs/logs/neuroimaging/series_folder_inventory/` 和
`outputs/tables/neuroimaging/series_folder_inventory/`。MATLAB 转换的输入、NIfTI、BIDS
及事件替换目录由入口显式指定，当前 Windows 示例使用仓库外路径；部署集群时需单独确认。
`temp/` 仅用于短时开发验证，验证后清理，不纳入版本控制。

## 静息态影像生产模块

集群项目根目录由 `configs/neuroimaging.json` 统一指定，默认
`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
外部 BIDS 根目录按数据集独立配置，只读使用，不复制到 `data/raw/`。
模块路径由 `src/imaging/config.py` 统一生成，`<dataset>` 为 THU 或 XY。
fMRIPrep／XCP-D 的分析参数选择和完整容器命令直接保存在对应 sbatch 脚本中；
统一配置保留路径及需供审计、头动和 FC 读取的参数值，`src/` 不组装容器分析命令。

| 生产模块 | 产物 | 归属路径（相对项目根目录） |
| --- | --- | --- |
| fmriprep | BIDS derivatives、HTML 报告 | `data/interim/neuroimaging/fmriprep/<dataset>/rest/` |
| freesurfer | 解剖重建，由 fMRIPrep 生产 | `data/interim/neuroimaging/freesurfer/<dataset>/` |
| xcpd | BIDS derivatives、ptseries 与逐 run FC | `data/interim/neuroimaging/xcpd/<dataset>/rest/` |
| fmriprep／xcpd | 可复用工作目录 | `data/interim/neuroimaging/<module>/<dataset>/work/<subject>/` |
| head_motion | 被试 FD 表、run／subject QC、阈值表 | `outputs/tables/neuroimaging/head_motion/<dataset>/rest/` |
| rest_fc | 被试 Pearson r／Fisher z 矩阵 | `data/processed/neuroimaging/rest_fc/<dataset>/rest/<subject>/<atlas>/{raw,fisher_z}/` |
| rest_fc | 输入 run、帧数与 ROI 来源表 | `outputs/tables/neuroimaging/rest_fc/<dataset>/rest/subjects/` |
| 各影像模块 | Slurm 日志、完成记录、提交与审计清单 | `outputs/logs/neuroimaging/<module>/<dataset>/rest/` |
| fmriprep／xcpd | 容器临时目录 | `temp/neuroimaging/<module>/<dataset>/rest/<subject>/<job_id>/` |

正式工作目录和容器临时目录不自动删除，便于诊断与恢复；清理仅限明确完成任务的自有目录。
本地合成验证另使用 `temp/smoke_neuroimaging_*`，测试结束立即清理。
