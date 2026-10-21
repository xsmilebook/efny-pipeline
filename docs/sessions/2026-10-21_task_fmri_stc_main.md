# 2026-10-21：主分析统一 STC，准备任务态 fMRIPrep

## 用户要求与范围

用户计划提交任务态 fMRIPrep，要求启用 STC，其他分析参数保持一致，
允许新增任务态专属脚本；后续静息态与任务态主分析均使用 STC。
用户明确允许取消 no-STC 的等待任务，要求保留正在运行的作业及已运行／已完成的数据。

修改前本地与集群均为 `main`，工作区干净，基线为
`4e63c8479c0c7518df69eb5a5dfd9a0b9eb74243`。
本地根目录为 `D:\projects\efny-pipeline`，已阅读 `ARCHITECTURE.md` 和集群执行约定。
集群通过 `CIBR-login` 连接 `login01`，项目根目录和 THU BIDS 输入保持原配置。

## 已执行的调度操作

限定范围为原 no-STC 数组 `15427951` 及其补交／恢复任务 `15428233`、`15428234`、
`15428235`。先逐任务读取状态，再对明确处于 PENDING 的任务执行：

```bash
scancel --state=PENDING <explicit_pending_task_ids>
```

共选择取消 **658 个等待任务**；使用状态过滤防止检查后刚转为 RUNNING 的任务被取消。
操作后范围内只剩 **42 个 RUNNING**，无 PENDING；其中正在运行的补交任务 `15428233`
保留，等待中的补交 `15428234` 与恢复调度任务 `15428235` 取消。
未删除任何衍生数据、工作缓存、FreeSurfer 结果或运行锁。
完整取消命令、操作前后状态与保留的运行任务列表位于集群
`outputs/logs/neuroimaging/fmriprep/THU/no_slicetiming/rest/cancel_pending_no_stc_20261021.json`。

## 配置与代码

- 新主配置 `configs/neuroimaging_stc.json` 使用 `fmriprep.ignore=[]`；
  除 STC 选择及新增任务标签清单外，与原配置的镜像、路径、资源和其他参数保持一致。
- `configs/neuroimaging.json` 原样保留为历史 no-STC 配置。
  仍运行的作业明确传入该文件，并在结束时再次读取它；直接修改此文件会导致
  完成记录写错分析目录，因此新主配置使用独立文件。
- 新任务态完整命令保存在 `scripts/neuroimaging/run_fmriprep_task.sbatch`，
  通过 `--bids-filter-file` 明确选择 sst、nback、switch。
  镜像 25.2.5、5 个输出空间、91k CIFTI、6／6 线程、随机种子、代理、跳过 BIDS 验证等均保持原值。
- CLI 新增 `--scope task`；现有静息态默认为 `--scope rest`。
  任务态允许单 run 缺省 run 实体，保留 task／run 身份；不套用静息态 QC 或 FC。
- 任务态结果、清单、日志和临时目录使用 `<dataset>/task/`，工作目录使用
  `<dataset>/work_task/<subject>/`，与静息态结果和缓存隔离；FreeSurfer 沿用现有 STC 解剖重建。
- 新主入口及相关下游入口默认读取 STC 主配置。
  审计将空 ignore 列表与旧 STC 默认设置等同，不强制重跑历史 STC 静息态产物。
- STC 输入缺少 SliceTiming 或时间超出 `[0, TR)` 时直接报错。
  完成审计要求逐 run 的 MNI BOLD JSON 标记 `SliceTimingCorrected=true`，并继续检查时间轴。
- 未添加模板预初始化、初始化锁、额外切片时间参考或其他分析方法变更。

README、ARCHITECTURE、原预处理方法、参考参数对照及新任务态专用说明同步更新。
集群旧 STC 静息态输出抽查的 BOLD JSON 已有 `SliceTimingCorrected=true`。

## 任务态输入核对与待确定范围

只读核对原 731 人：563 人有目标任务 BOLD，共 1514 个 run（sst 561、nback 520、switch 433），
对应 JSON 均有 SliceTiming；其余 168 人没有这三类任务影像。
原清单外另有 8 人有任务 BOLD，其中 2 人缺少 T1w、6 人具有 T1w。
未自动扩展或缩减正式样本。已向用户询问任务态样本范围及本轮是否直接提交，
在范围与提交意图未明确前，本次完成脚本与命令准备，不提交新任务态或重提 STC 静息态作业。

## 验证

既有 `.venv` 使用 Python 3.12.9，配合 Git Bash 执行：

```powershell
$env:EFNY_TEST_BASH = 'C:\Program Files\Git\bin\bash.exe'
uv run --python 3.12 --offline --no-sync python -m unittest discover -s tests -p test_neuroimaging.py -v
```

19 项验证通过，覆盖旧 no-STC 流程兼容、STC 参数一致、任务清单与过滤、缺失 run 实体、
缺少 STC 元数据时报错、专属 worker 实际命令、完成记录以及实际 STC 标记为 false 时拒绝通过。
两个 fMRIPrep sbatch 的 Bash 语法检查通过。合成验证不代表真实任务态容器分析完成。
临时合成测试产物由测试自动清理；正式数据和结果无删除操作。

## 集群同步后的核对

实现提交为 `9d2c4af`，已推送；集群检查工作区干净后使用 `git pull --ff-only` 同步。
逐项读取已保存的完成记录，34 份历史 no-STC 记录和原 STC 的 731 份记录均与
各自配置、输入清单兼容，未改写任何完成记录。
进一步逐 run 读取原 STC 静息态 MNI BOLD JSON，2459 个 run 全部
`SliceTimingCorrected=true`，无缺失文件。本次为 STC 标记核对，不等于重新执行完整影像 QC。
集群原生 Bash 下的任务态命令预览通过，确认选择任务过滤文件、不传 ignore slicetiming，
输出与工作目录正确，其他容器参数保持原值。
2026-10-21 17:47（北京时间）复查 no-STC 范围只剩 39 个 RUNNING、无 PENDING；
此前保留的任务按原设置自然完成，未执行取消 RUNNING 或删除数据的操作。
没有提交新的 STC task／rest 作业。

## 用户确认：全部 THU 任务影像，准备后直接提交

用户随后回复：检查全部 THU 被试的任务影像，准备后直接提交到集群。
本节为此前待确定范围的最终执行记录，不再限制为原 731 人。

### 完整输入核对

重新检查全部 765 个 `sub-THU*` 被试目录：

| 输入状态 | 被试数 | 执行决定 |
| --- | ---: | --- |
| 至少有一种目标任务 BOLD 且有 T1w | 569 | 提交任务态 fMRIPrep |
| 有任务 BOLD，但缺少 T1w | 2 | 记录为待补输入，未提交 |
| 没有 sst／nback／switch BOLD | 194 | 记录为无目标任务影像 |

缺 T1w 者为 `sub-THU202501210530`、`sub-THU202602240899`。
没有删除任何被试、源数据或历史结果，也没有把缺输入者标记为预处理成功。
569 人的正式输入共 **1522 个 run**：sst 567、nback 521、switch 434。
每个已选中 BOLD 的 SliceTiming 数目与 NIfTI 切片数一致，NIfTI／JSON TR 一致，
切片时间均在 `[0, TR)` 内，BOLD 帧数不少于 5。
帧数范围为 sst 149–335、nback 20–273、switch 141–209；保留已有短 run，
不自行删除部分采集数据。此处为输入与 STC 就绪核对，不代表任务行为或最终影像 QC 合格。

### 正式提交与并发限制

2026-10-21 18:08（北京时间）提交数组 **15428647**，索引 `0-568`。
代码为 `2f2d19a7c75c60ae4eb9a1126967241f5f391c9e`，集群工作区干净，
离线环境检查通过。依然使用 Python 3.11.15、配置的 fMRIPrep 25.2.5 镜像、
`q_fat_c`、`high_c` 和每任务 6 核／6／6 线程，其他方法参数与已确认脚本一致。

通过 `prepare(config, subjects_ready_20261021.txt)` 生成正式清单与任务过滤文件，
实际命令预览通过。提交仍使用 `imaging.pipeline.submit`，scope 为 `task`，
只在提交时将数组并发值设为当时剩余名额 **15**，不改写共享主配置或分析参数。
当时保留的 no-STC 任务有 33 个 RUNNING，新数组与它们合计最多 48 个。

调度扩容作业 **15428648** 依赖 `afterany:15427951:15428233`，
在所有残余 no-STC 任务结束后执行：

```bash
scontrol update JobId=15428647 ArrayTaskThrottle=48
```

扩容作业使用 `q_fat_c`、`high_c`、1 核，仅调整新数组的调度并发。
旧运行任务均未取消；原 no-STC 数据和缓存继续保留。
提交后新数组先为 PENDING，扩容作业为 PENDING／Dependency；不将排队解释为分析完成。

### 正式来源记录

集群任务态模块日志根目录为
`outputs/logs/neuroimaging/fmriprep/THU/task/`，包含：

- `all_thu_task_input_audit.csv`：765 人的任务 run 数、T1w 状态和提交状态宽表；
- `subjects_ready_20261021.txt`：569 人审核后的输入清单；
- `subjects_blocked_missing_t1_20261021.txt`：两名待补 T1w 者；
- `input_audit_20261021.json`：代码、时间、输入范围、帧数范围及 STC 元数据核查；
- `input_scans.csv`、`bids_filter.json`、`resolved_config.json`：正式输入身份、过滤条件和配置；
- `array_subjects_20261021T100848184824.txt`：数组编号到被试的固定映射；
- `submitted_20261021T100848184824.csv`：569 人任务编号与完整 sbatch 命令；
- `submission_task_stc_20261021.json`：提交时间、代码、工作区、并发预算、旧任务与扩容作业。

新任务输出仍为 `data/interim/neuroimaging/fmriprep/THU/task/`，不覆盖 rest 或 no-STC 结果。

### 启动核对

18:10（北京时间）复查，新数组 1 个 RUNNING、568 个 PENDING；旧 no-STC 33 个 RUNNING，
合计 34 个 fMRIPrep 任务运行，未超过 48。首个任务为 `15428647_0`，
被试 `sub-THU202311180133`，Slurm 单任务编号 `15428649`，节点 `fat14`。
实际启动版本为 fMRIPrep 25.2.5，环境只读检查通过，数组启动 stderr 无错误。
workflow 日志分别为 nback、sst、switch 建立处理分支，均明确写出
`BOLD series will be slice-timing corrected`，参考偏移为约 0.959–0.96 秒。
这是工作流构建／启动核对；真实逐 run STC 执行、必需输出和成功完成仍以后续审计为准。
