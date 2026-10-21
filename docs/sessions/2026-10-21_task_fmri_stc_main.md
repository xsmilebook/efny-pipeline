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
