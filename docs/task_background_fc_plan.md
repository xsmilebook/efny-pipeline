# THU 任务态 background FC 修改方案

## 目标与本轮边界

目标是在现有 STC task fMRIPrep 结果上，沿用 rest 的 XCP-D 设置，增加任务效应回归，获得去除模型化任务诱发效应后的残差时序和 background FC。任务标签为 `sst`、`nback`、`switch`，分别处理和保存。

本轮仅核查和规划，没有修改代码、统一配置、上游协变量或数据结果，没有提交集群作业。根目录 [PLAN.md](../PLAN.md) 为实施清单。下列新路径及新入口均为拟议方案，当前尚不存在相应处理能力。

## 当前证据

2026-10-27 15:46（北京时间）通过 CIBR-login 只读检查；项目根目录为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，使用该仓库 `.venv/bin/python`。未在登录节点运行影像处理、矩阵计算或并行分析。

上游读取 `outputs/logs/neuroimaging/fmriprep/THU/task/input_scans.csv`，包含 569 人、1,522 个 run。当前有 569 份完成记录；已有 `retry_audit_15438020.out` 报告 569/569 通过，配套 stderr 为空。这是已有审计证据和本次完成记录计数，本轮未重新执行全量产品、时间轴与 Slurm accounting 审计。

外部协变量根目录为：

```text
/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK
```

根目录含 `dataset_description.json`、`processing_summary.tsv`、`candidate_files.tsv`；各被试 `func/` 同时含 events 与 confounds，必须只选 `*_desc-confounds_timeseries.tsv`。不能将所有 TSV 数量当作协变量文件数。

| 任务 | fMRIPrep 清单 run 数 | 按完整 scan 身份匹配的协变量 | 缺失协变量 |
| --- | ---: | ---: | ---: |
| nback | 521 | 500 | 21 |
| sst | 567 | 316 | 251 |
| switch | 434 | 418 | 16 |
| 合计 | 1,522 | 1,234 | 288 |

外部共有 530 人、1,239 份 confounds，其中 5 份不在现有 fMRIPrep 清单。现有 569 人中，528 人至少匹配一个任务，41 人完全未匹配。这些是文件身份交集，不代表 1,234 个 run 已通过时间轴、来源和设计矩阵检查。

外部 summary 自身报告 1,239 个 `ok` 和 289 个 `error`，错误原因为：243 个没有完整 CSV、45 个没有匹配的 PsychoPy CSV、1 个模型化事件超出 BOLD 时长。该 summary 的范围与项目清单不同，其 289 个 error 不应直接等同于项目缺失的 288 个 run。实施时需逐项关联，不推断一一对应，也不自动补齐、重新配对或扩展样本。

三个任务各抽查一份 confounds 与 JSON，结果如下。列名来自实际 TSV，未将 task 简化成单一二元 block。

| 任务 | 抽查列名 | 抽查行数 |
| --- | --- | ---: |
| nback | `task_0back`, `task_2back`, `task_cue` | 219 |
| sst | `task_go_correct`, `task_go_error`, `task_stop_fail`, `task_stop_success` | 161 |
| switch | `task_cue`, `task_nonswitch1`, `task_nonswitch2`, `task_switch` | 209 |

抽查 sidecar 说明这些列用于移除任务效应，已使用 SPM canonical HRF，无 HRF 导数或 drift；生成器为 `build_task_confounds.py` 1.2.0，Nilearn 0.12.1；`DummyVolumesRemovedHere=0`。直接使用前仍需核查全部实际文件，不能重复做 HRF 卷积。

## 时间参考是实施前的关键条件

抽查被试 `sub-THU202311180133` 的三个任务：协变量 JSON 均为 `FrameTimeOffsetSeconds=0`；对应 fMRIPrep MNI BOLD JSON 为 `SliceTimingCorrected=true`，`StartTime` 分别为 nback 0.96、sst 0.96、switch 0.959 秒，TR 均为 2 秒。

这是潜在的任务设计采样时间差异。实施前必须结合生成器的 frame times 定义、scanner trigger、BOLD `StartTime`、CIFTI 时间轴和实际 STC 设置确认。行数相同不能解决亚 TR 的错位；不能根据 CIFTI 序列起点为零就忽略 STC 的物理时间参考，也不能将所有 run 强制写成相同偏移。

若核查确认设计应采样于 `StartTime + arange(N) * TR`，应从已确认的原始任务时序重新计算一份独立、可追溯的 STC 对齐设计，保留外部原件。不能只改 JSON 的偏移标签，也不能简单平移／插值已有离散 HRF 列冒充重新生成。新增衍生设计应登记在本项目对应的 `data/interim/neuroimaging/task_confounds/THU/task_background/<task>/` 模块路径，并在配置中明确实际挂载根目录；只有确有需要时创建。

来源核对还需保留 sidecar 的原 CSV、trigger 与日志选择依据；抽查可见 scanner acquisition 与 PsychoPy 时钟存在分钟差，不能仅因协变量文件已生成就把 CSV／BOLD 配对视为已独立验证，也不应擅自平移时钟。

## 回归模型与保留参数

使用同一个联合设计矩阵回归 36P 与任务效应。XCP-D 26.0.2 的入口应为：

```bash
--datasets custom=/custom_confounds
--nuisance-regressors /configs/xcpd_36p_task_background.yml
--task-id <sst|nback|switch>
```

容器须只读挂载实际使用的 custom derivative dataset 和 YAML。`--datasets` 与已有 atlas datasets 参数合并为同一个参数列表。保持显式 `--output-layout bids`。

新增 YAML 以该版本内置 `36P.yml` 的 36 列为基线，保留其 `preprocessed` 查询，另增 `dataset: custom`、`desc: confounds`、`suffix: timeseries`、`.tsv` 查询，通过 `^task_.*$` 选择任务列。运行前按任务核对实际选中列集合及其生成含义，不能让正则匹配为空而退化为只有 36P。不能用一份所有任务列名的硬编码并集要求每个 run 都具备全部列。

任务项是要去除的 nuisance，不添加 `signal__` 前缀；该前缀会使 XCP-D 将相关列视为需要保护的信号。带通、去趋势及回归交由同一 XCP-D 流程完成，不先单独残差化再运行 rest 流程。

| 设置 | 拟议值与依据 |
| --- | --- |
| 上游 | 现有 THU STC task fMRIPrep 25.2.5，读取 `task/` |
| XCP-D | 26.0.2，`--mode none`，CIFTI |
| 回归 | 原 36P，加现有任务条件／cue 的 HRF 回归项 |
| 时间处理 | dummy 0；带通 0.01–0.1 Hz，阶数 2 |
| 头动参数滤波 | 沿用 low-pass、6 BPM，不据此改变 QC 用原始 FD 的定义 |
| censoring | `--fd-thresh 0`，不逐帧删除 |
| 其他 | smoothing 0、despike n、combine-runs n、min-coverage 0、seed 42 |
| 图谱 | 4S156Parcels、4S256Parcels、4S456Parcels，保留非皮层节点 |
| 资源 | q_fat_c，1 CPU，`--nprocs 1 --omp-nthreads 1`，沿用参考代理及容器环境传递 |

background FC 在这里指去除已建模任务效应后的残差相关；不能据此保证所有任务诱发变化都已消除。当前提供的条件设计不新增 FIR、HRF 导数、替代带通或其他未经明确要求的方法分支。

## 路径与最小代码改动

保持上游 `fmriprep/THU/task/` 和现有 rest 路径。下游以 `task_background` 显式表明分析含义，再按 task 隔离；这样可独立处理部分任务可用的被试，同时避免同一被试的多个任务并发写同一报告或缓存。

| 用途 | 拟议路径，相对项目根目录 |
| --- | --- |
| XCP-D derivatives、逐 run FC、报告 | `data/interim/neuroimaging/xcpd/THU/task_background/<task>/` |
| XCP-D 缓存 | `data/interim/neuroimaging/xcpd/THU/work_task_background/<task>/<subject>/` |
| XCP-D 输入清单、选列记录、作业／完成审计 | `outputs/logs/neuroimaging/xcpd/THU/task_background/<task>/` |
| XCP-D 容器临时目录 | `temp/neuroimaging/xcpd/THU/task_background/<task>/<subject>/<job_id>/` |
| 标准化导出的 r／z 矩阵 | `data/processed/neuroimaging/background_fc/THU/task_background/<task>/<subject>/<scan_id>/<atlas>/{raw,fisher_z}/` |
| FC 指标与来源表 | `outputs/tables/neuroimaging/background_fc/THU/task_background/<task>/` |
| FC 来源日志 | `outputs/logs/neuroimaging/background_fc/THU/task_background/<task>/` |
| task 头动描述表／来源日志 | `outputs/{tables,logs}/neuroimaging/head_motion/THU/task_background/<task>/` |

具体改动落点：

1. `configs/neuroimaging_stc.json` 新增独立 `task_xcpd` 设置；不把 XCP-D 字段加进现有 `task_fmri`，避免已有 `processing_settings(fmriprep)` 因下游配置变化而错误失效。
2. `src/imaging/config.py` 统一解析上表路径；task fMRIPrep 与 task background 下游分别解析。`task_background` 是下游分析变体，不能把上游输入路径也改成该目录。
3. 新增 `configs/xcpd_36p_task_background.yml` 和 `scripts/neuroimaging/run_xcpd_task_background.sbatch`。完整容器命令及科学参数留在 sbatch，不放进 `src/`。保留原 rest 入口。
4. `src/imaging/pipeline.py` 放开 THU task 的 XCP-D 子集，修正 `run_stage` 当前 task 一律指向 fMRIPrep 脚本的路由；联动 shell-config、start/finish-container、submit、check。拟以 `--scope task --stage xcpd --task <task>` 选择背景处理，新增 task 参数的具体实现与校验应保持局部、明确。
5. 对每个 subject×task 按审核的 run 清单提交并锁定，使用 `--task-id` 和所需精确 run 过滤。缺协变量的 run 在审计中明确为未就绪；不能自动跳过后仍登记整个任务成功。多 run 只处理明确选择的 run，未选中的 run 不能被容器默认纳入。
6. 复用现有上游 fMRIPrep 完成记录时，仍以完整原上游清单验证；背景分支另存选中的 scan 子集。不能拿下游子集去比较现有整被试 fMRIPrep 的 `record['scans']`，也不能为做子集而覆盖上游 `input_scans.csv`。
7. 完成记录应包含 background 方法名、task/run、36P 与任务实际列、协变量路径及必要来源、采样时间约定、上游完成时间、代码／工具版本、命令及作业号；配置或设计来源变化后不得复用旧标记，不引入文件内容哈希。
8. XCP-D 已提供逐 run 相关矩阵；若需与项目 rest 的标准化 r／Fisher z 输出一致，在最小独立 `background_fc` 模块中读取残差 ptseries 计算并交叉核对，不将 task 数据送入 `rest.compute_fc` 的 rest 拼接规则。

## 验证、QC 与执行顺序

先完成匹配、来源和时间核对，再提交少量计算节点试跑。三个任务均应覆盖；另用合成验证覆盖缺协变量、无 run 实体、多 run 子集、时间／身份不符和设计退化等情况。

科学检查包括：BOLD／36P／task TSV 行数及 TR 一致；相同 dummy 时间窗；task 列存在且有限；常量、零列和共线项及滤波后的设计秩／剩余自由度可解释；XCP-D 实际设计确实纳入 36P 与 task 项。退化设计须明确暴露，不静默删除条件或添加填充值。试跑时检查联合回归后的残差与同样去趋势／滤波的设计近似正交，而不是仅检验与未经滤波的原始 task TSV 的相关。

随后核对 denoised CIFTI 与 ptseries 的帧数、TR、ROI 数和标签顺序，验证 r 矩阵对称性、对角线及 Fisher z 约定，结合 stderr、HTML、完成记录和 Slurm accounting 确认成功。保存试跑耗时和资源记录，再确定批量提交范围；本轮不写未经实现的正式提交命令供直接运行。

头动先按 subject×task/run 汇总原始 fMRIPrep FD、帧数和有效时长。rest 的“至少两个合格 run”不适用于普遍单 run 的 task，rest 已估计的总体 FD 阈值也不自动迁移。若后续要产生筛选后／汇总后的被试×任务 FC，另行明确任务的阈值、有效时长、最低 run 数和汇总方法。默认分别保留各任务、各 run，不合并 SST、n-back 与 switch，不跨 run 边界直接拼接后套用 rest 汇总。

实现时同步更新 `ARCHITECTURE.md`、README 和方法补充，记录当天 session，按仓库要求 commit；切换集群开发端前提交并推送，集群确认工作区和分支后快进同步。不得将提交／RUNNING 或单个完成标记当作整批分析完成。

## 官方依据

- [XCP-D 26.0.2 自定义协变量与任务回归](https://xcp-d.readthedocs.io/en/26.0.2/usage.html#task-regression)：YAML 配合额外 derivative dataset；任务效应先与 HRF 卷积。
- [XCP-D 26.0.2 内置 36P 配置](https://github.com/PennLINC/xcp_d/blob/26.0.2/xcp_d/data/nuisance/36P.yml)：明确 36 列及查询。
- [XCP-D 26.0.2 回归配置和去噪流程](https://xcp-d.readthedocs.io/en/26.0.2/workflows.html#the-confound-configuration-file-format)：正则选列、联合去噪、滤波和 signal regressors 语义。
- [fMRIPrep 变更记录中的 STC 时间元数据说明](https://fmriprep.org/en/latest/changes.html)：`StartTime` 表示校正后序列的时间起点；实施时仍须以所用版本与实际文件为准。
