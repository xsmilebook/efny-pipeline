# THU task fMRIPrep 六名未完成被试补提

## 授权、复核与范围

用户明确授权清除因遗留锁启动失败的 5 人残留锁后重新提交；
对容器日志报告成功、但 Slurm 失败且无完成登记的另一人，可继续执行或重新执行。
本次沿用既有入口重提全部 6 人，保留已有衍生结果和工作缓存，由 fMRIPrep 使用可复用节点，
并重新执行脚本末尾的产物、STC、时间轴检查和正式完成登记。

2026-10-24 15:11–15:14（北京时间）复核：本批无活动作业；
原数组的以下 6 个任务均为 FAILED／1:0，模块已有 563 人完成登记。
5 个锁均为空目录、非符号链接，确认位于 task 模块 locks 目录后使用 `rmdir` 删除；
未递归删除结果、work_task、临时目录或共享 FreeSurfer。

| 被试 | 原数组任务 | 本次任务 | 启动核对 |
| --- | --- | --- | --- |
| sub-THU202401290223 | 15428647_53 | 15438019_0 | RUNNING，fat14 |
| sub-THU202401290224 | 15428647_54 | 15438019_1 | RUNNING，fat14 |
| sub-THU202402240236 | 15428647_66 | 15438019_2 | RUNNING，fat14 |
| sub-THU202402250240 | 15428647_70 | 15438019_3 | RUNNING，fat14 |
| sub-THU202402250242 | 15428647_71 | 15438019_4 | RUNNING，fat14 |
| sub-THU202508200733 | 15428647_349 | 15438019_5 | RUNNING，fat14 |

最后一人的既有结果已在前次检查中通过必需产物、STC 和时间轴检查，未发现崩溃文件；
其原作业非零退出的具体原因仍未确定。本次不根据日志文本直接补成功标记，
由原脚本重新执行和登记，科学参数不变。

## 运行来源与命令

运行代码为 `838ba88`，本地与集群起始工作区均干净。没有修改代码或配置。
集群项目根目录为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
输入为 `/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`，
仅处理既有 task 输入清单中的 SST、n-back、switch；本次 6 人共 17 个任务序列。
输出为 `data/interim/neuroimaging/fmriprep/THU/task/`，
沿用 `data/interim/neuroimaging/fmriprep/THU/work_task/<subject>/` 和共享 STC FreeSurfer。
保留其余 563 人完成结果及全部 rest 结果。

沿用 fMRIPrep 25.2.5、启用 STC、6 CPU、`--nprocs 6 --omp-nthreads 6`、
q_fat_c／high_c，以及既有输出空间、91k CIFTI、随机种子、代理和跳过 BIDS validation 参数。
环境检查 `uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17` 通过。

从集群项目根目录运行：

```bash
uv run --offline --no-sync efny-imaging submit \
  --dataset THU --scope task --stage fmriprep \
  --config configs/neuroimaging_stc.json \
  --subjects outputs/logs/neuroimaging/fmriprep/THU/task/retry_subjects_20261024T071348899111.txt
```

提交入口固定本次 6 人的 LF 清单，生成数组 `15438019`；配置并发上限仍为 72，
实际本批最多 6 人并行。完整 Slurm 命令和逐人编号保存在提交 CSV 和操作记录中。
`15438020` 使用 q_fat_c／1 CPU，以 `afterok:15438019` 等待全部重提任务成功，
随后执行既有 `efny-imaging check --dataset THU --scope task --stage fmriprep`，
并显式断言成功身份集合与原 569 人清单完全一致、失败清单为空。
审计仅使用 task 输入及结果，不调用 rest 下游流程。

## 追溯和当前状态

本次完整操作记录为集群模块日志下的
`outputs/logs/neuroimaging/fmriprep/THU/task/retry_six_20261024T071348899111.json`，
记录授权范围、代码版本、工作区状态、输入输出位置、5 个删除锁路径、冻结清单、提交及审计完整命令。
被试 stdout／stderr 仍保存在该目录，以被试和实际 Slurm 作业号命名；
审计日志为 `retry_audit_15438020.out`／`.err`。

提交后 6 个任务均 RUNNING，日志通过环境检查且未出现锁冲突；
审计为 PENDING／Dependency。当前仅确认补提及启动，尚不能视为全部预处理完成。
