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
│   ├── neuroimaging_stc.json    # STC 主分析：THU/XY 输入、工具与分析参数
│   ├── neuroimaging.json        # 历史 no-STC 配置，供未结束作业继续读取
│   └── xcpd_36p_task_background.yml # 36P 与任务效应联合回归配置
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
│   │   ├── rest.py             # 头动 QC 与被试级 CIFTI 功能连接
│   │   └── background.py       # 任务协变量审计与逐 run background FC
│   ├── behavior/               # 行为任务与人口学预处理
│   └── inventory/              # 问卷与量表处理（预留）
│
├── scripts/                    # 执行入口（本地/HPC/主流程脚本）
│   ├── neuroimaging/           # rest／task fMRIPrep、XCP-D 与下游 sbatch 入口
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

集群项目根目录由主配置 `configs/neuroimaging_stc.json` 统一指定，默认
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

上表是 STC 静息态主分析路径。2026-10-21 起，默认配置为
`configs/neuroimaging_stc.json`，`fmriprep.ignore=[]`，静息态和任务态均启用 STC。
任务态使用 `--scope task` 和 `scripts/neuroimaging/run_fmriprep_task.sbatch`，
下游通过 `--stage xcpd --task <task>` 进入独立 background 分支，不套用静息态头动／FC 规则。

| 任务态用途 | 路径（相对项目根目录） |
| --- | --- |
| fMRIPrep 衍生数据 | `data/interim/neuroimaging/fmriprep/<dataset>/task/` |
| 任务态专用工作缓存 | `data/interim/neuroimaging/fmriprep/<dataset>/work_task/<subject>/` |
| 输入清单、BIDS 过滤文件、作业日志与完成记录 | `outputs/logs/neuroimaging/fmriprep/<dataset>/task/` |
| 容器临时目录 | `temp/neuroimaging/fmriprep/<dataset>/task/<subject>/<job_id>/` |
| FreeSurfer | 沿用 STC 目录 `data/interim/neuroimaging/freesurfer/<dataset>/` |

任务态不写入静息态衍生结果或静息态工作缓存。共享 FreeSurfer 是同被试的解剖重建，
与是否 STC 无关；本轮任务态准备不重新启动静息态任务。

## 任务态 background FC 生产模块

THU 任务态下游使用 `--scope task --task sst|nback|switch`，读取上表 task fMRIPrep。
`configs/neuroimaging_stc.json` 的独立 `task_xcpd` 设置保存只读协变量目录与回归 YAML 路径。
36P 与已有 HRF 任务效应在 XCP-D 内联合回归，完整命令位于
`scripts/neuroimaging/run_xcpd_task_background.sbatch`；三个任务分别提交，互不合并。

| 生产模块／用途 | 路径（相对项目根目录） |
| --- | --- |
| xcpd derivatives、残差 ptseries、逐 run 相关及报告 | `data/interim/neuroimaging/xcpd/THU/task_background/<task>/` |
| xcpd 专用缓存 | `data/interim/neuroimaging/xcpd/THU/work_task_background/<task>/<subject>/` |
| xcpd 清单、过滤文件、协变量／设计审计、锁与完成记录 | `outputs/logs/neuroimaging/xcpd/THU/task_background/<task>/` |
| xcpd 输入就绪汇总 | `outputs/tables/neuroimaging/xcpd/THU/task_background/<task>/input_readiness.csv` |
| xcpd 容器临时目录 | `temp/neuroimaging/xcpd/THU/task_background/<task>/<subject>/<job_id>/` |
| head_motion 逐 run 描述表 | `outputs/tables/neuroimaging/head_motion/THU/task_background/<task>/subjects/<subject>.csv` |
| background_fc 逐 run r／z 矩阵 | `data/processed/neuroimaging/background_fc/THU/task_background/<task>/<subject>/<scan_id>/<atlas>/{raw,fisher_z}/` |
| background_fc 逐 run 汇总表，图谱并列为列 | `outputs/tables/neuroimaging/background_fc/THU/task_background/<task>/subjects/<subject>.csv` |
| head_motion／background_fc 日志、来源及完成记录 | `outputs/logs/neuroimaging/<module>/THU/task_background/<task>/` |

`background_fc` 为独立生产模块。输入准备另存 task 子集，不改写原 fMRIPrep 完整清单；
上游完成记录仍按完整被试输入验证。协变量采样偏移必须匹配 STC BOLD 的 `StartTime`，
不自动修正外部协变量，不静默排除缺失 run。使用说明与当前输入限制见
[任务态 background FC](docs/task_background_fc.md)。

2026-10-20 的历史配置 `configs/neuroimaging.json` 仍保留 `fmriprep.ignore=["slicetiming"]`。
统一路径函数在所有影像模块的 `<dataset>/` 后插入 `no_slicetiming/`，
包括衍生数据、FC、QC、日志、工作目录及容器临时目录。例如新的 fMRIPrep 结果为
`data/interim/neuroimaging/fmriprep/THU/no_slicetiming/rest/`，工作目录为
`data/interim/neuroimaging/fmriprep/THU/no_slicetiming/work/<subject>/`。
FreeSurfer 独立写入 `data/interim/neuroimaging/freesurfer/THU/no_slicetiming/`。
旧路径保留；后续阶段只读取同一分析版本的上游结果，不回退到旧路径。
该版本当前不用于主分析。取消其等待任务，但正在运行和已经完成的结果、缓存均保留。
不修改历史配置，确保仍在运行的任务结束时继续写入自己的 no-STC 完成记录。

正式工作目录和容器临时目录不自动删除，便于诊断与恢复；清理仅限明确完成任务的自有目录。
本地合成验证另使用 `temp/smoke_neuroimaging_*`，测试结束立即清理。
