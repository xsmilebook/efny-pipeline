# 任务态 fMRIPrep：统一启用切片时间校正

## 方法与输入范围

2026-10-21 用户决定静息态和任务态主分析均使用 STC。
主配置为 `configs/neuroimaging_stc.json`，任务态入口为
`scripts/neuroimaging/run_fmriprep_task.sbatch`。
任务标签固定为 `sst`、`nback`、`switch`，通过准备阶段生成的
`bids_filter.json` 传入 `--bids-filter-file`，不把静息态 BOLD 混入任务态输出。

相对已有静息态脚本，任务态只改变输入选择及独立路径；启用 STC 的主配置使用
`fmriprep.ignore=[]`。镜像 25.2.5、5 个输出空间、91k CIFTI、全部 CompCor components、
随机种子 42、6／6 线程、`--skip-bids-validation`、原代理和其他容器参数保持一致。
不新增 `--slice-time-ref`，继续使用该版本默认的切片时间参考设置。
任务态脚本要求 ignore 列表为空。

fMRIPrep 根据 `SliceTiming` 元数据启用 STC，定义见
[25.2.5 官方流程说明](https://fmriprep.org/en/25.2.5/workflows.html#slice-time-correction)。
准备阶段要求每个选中 BOLD 的同名 JSON 含 `SliceTiming` 和有效 TR，
切片时间必须位于 `[0, TR)`；缺失或错误时停止，不通过忽略 STC 继续运行。
完成审计逐 run 要求 MNI152NLin2009cAsym BOLD JSON 的 `SliceTimingCorrected=true`，
不把仅有输入元数据或提交参数视为 STC 已执行；同时保留帧数与 CIFTI 时间轴检查。

支持 `sub-*/func/*_task-<task>[_run-*]_bold.nii[.gz]`，允许任务态单 run 省略 run 实体。
同一任务与 run 身份不得重复；继续不支持 session 和多回波。
静息态原有的正整数 run 编号约定不变。
当前任务态只支持 fMRIPrep，不自动运行静息态 XCP-D、头动筛选或 FC。

本次只读核对显示：原 731 人中 563 人有任务影像，共 1514 个 run
（sst 561、nback 520、switch 433）；对应 JSON 均有 `SliceTiming`。
其余 168 人在当前 BIDS 中无上述任务 BOLD，不应被当作任务处理失败。
原范围外另有 8 人有任务影像，其中 2 人缺少 T1w，6 人具有 T1w。
这属于样本范围差异，不自动纳入、排除或扩展分析；提交前审核明确的任务态被试清单。

## 路径与提交

项目根目录和 BIDS 输入保持原值。路径相对项目根目录如下：

| 内容 | 路径 |
| --- | --- |
| 任务态 fMRIPrep | `data/interim/neuroimaging/fmriprep/THU/task/` |
| 工作缓存 | `data/interim/neuroimaging/fmriprep/THU/work_task/<subject>/` |
| 清单、过滤文件、日志、完成记录 | `outputs/logs/neuroimaging/fmriprep/THU/task/` |
| 临时目录 | `temp/neuroimaging/fmriprep/THU/task/<subject>/<job_id>/` |
| FreeSurfer | `data/interim/neuroimaging/freesurfer/THU/` |

任务态沿用已有 STC FreeSurfer 解剖重建，不写入 `no_slicetiming/`，
不与同被试的静息态工作缓存混用。本次不增加模板初始化或初始化锁机制。
不要同时启动同一被试的另一套 STC FreeSurfer 解剖重建。

从集群项目根目录执行，`<reviewed_task_subjects.txt>` 为审核后的明确被试清单：

```bash
uv run --offline --no-sync efny-imaging prepare --dataset THU --scope task \
  --subjects <reviewed_task_subjects.txt>
uv run --offline --no-sync efny-imaging run --stage fmriprep --dataset THU --scope task \
  --subject <subject> --dry-run
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU --scope task --dry-run
# Submit after reviewing the manifest and command; use --subjects for a small first batch.
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU --scope task
```

主配置默认使用 STC，不必额外传 `--config`。仍通过作业数组按被试提交、每任务 6 核，
分区 `q_fat_c`、QoS `high_c`、单数组上限 48。并行上限不跨数组共享，
如与仍在运行的 no-STC 作业同时提交，应单独控制合计并发。
任务态缺少部分任务可以保留其现有任务，显式清单中的被试完全没有目标任务则报错；
不会静默跳过被试。

任务态作业结束后执行：

```bash
uv run --offline --no-sync efny-imaging check --stage fmriprep --dataset THU --scope task
```

## 保留历史作业

`configs/neuroimaging.json` 保持原样，因为运行中的 no-STC 作业在结束时仍显式读取它。
主入口和下游默认改用 `configs/neuroimaging_stc.json`。
历史 STC 静息态完成记录未保存空 ignore 列表，审计将空列表与原默认 STC 行为等同，
不因此要求重跑既有 STC 结果。
取消 no-STC 等待任务的记录见当日会话；正在运行的任务和已有数据均不删除。
