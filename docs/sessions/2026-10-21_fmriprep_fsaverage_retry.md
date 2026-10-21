# 2026-10-21：补交共享模板初始化冲突导致失败的两名被试

## 用户决定与范围

用户决定不增加额外的 FreeSurfer 模板初始化代码，要求将因 `fsaverage` 首次复制冲突
失败的任务直接补交，并解释主脚本中的数组编号到被试映射。
本次不修改分析脚本、科学参数、输出目录或原输入清单，也不处理节点故障留下的其他任务。

## 提交前核查

本地项目为 `D:\projects\efny-pipeline`；集群通过 `CIBR-login` 连接 `login01`，
项目根目录为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
已阅读 `ARCHITECTURE.md`；两端 `main` 工作区干净，提交代码为
`b8aa19acb3d3ce9c613facb7e78bdc11752a96e5`。

再次检查两名被试仍无成功记录、无残留运行锁，历史 stdout 均包含
`/freesurfer/fsaverage/` 复制时的 `shutil.Error` 与 `File exists`，符合本次重试范围。
原数组 `15427951` 此时有 48 个运行任务；当前同模块仅有原始提交回执，未发现重复补交。

## 实际补交

2026-10-21 11:34（北京时间）分别提交：

| 被试 | 原数组任务 | 新作业号 | 等待结束的原运行任务 |
| --- | --- | --- | --- |
| sub-THU202311180133 | 15427951_0 | 15428233 | 15427951_9 |
| sub-THU202311180134 | 15427951_1 | 15428234 | 15427951_16 |

每个补交任务使用以下命令结构，完整命令保存在集群回执中：

```bash
sbatch --parsable --chdir <project_root> --partition q_fat_c --qos high_c \
  --cpus-per-task 6 --dependency afterany:<original_running_task> \
  --output <logs>/<subject>_%j.out --error <logs>/<subject>_%j.err \
  scripts/neuroimaging/run_fmriprep.sbatch THU <subject> \
  <project_root>/configs/neuroimaging.json <project_root>
```

主脚本继续使用 fMRIPrep 25.2.5 镜像、`--ignore slicetiming`、6／6 线程，
沿用两名被试各自现有的工作缓存。输入仍为
`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`，
输出仍为 `data/interim/neuroimaging/fmriprep/THU/no_slicetiming/rest/`。
实际容器版本与成功产物应在任务运行后核查，本次不将排队视为完成。

为维持原有最多 48 个 fMRIPrep 并发任务的约束，将原数组临时设为
`ArrayTaskThrottle=46`；两名补交任务分别等待一个原运行任务结束，
因此不会在原 48 个任务尚未释放名额时额外启动。
调度恢复作业 `15428235` 在两名补交任务均结束后执行
`scontrol update JobId=15427951 ArrayTaskThrottle=48`，使用 `q_fat_c`、`high_c`、1 核。
它只恢复调度上限，不运行分析。任何运行中的原任务均未取消或中断。

提交后 3 个新作业均为 `PENDING / Dependency`。
再次通过 `squeue` 核对当前 fMRIPrep 运行数为 48；`scontrol` 确认原数组上限 46、
两名补交任务的各自依赖和恢复作业依赖均与上述设置一致。
本次仅补交上述两人，未重跑整批、未复制或改动现有 `fsaverage`。

## 来源记录与核查

来源记录位于集群
`outputs/logs/neuroimaging/fmriprep/THU/no_slicetiming/rest/`：

- `resubmission_fsaverage_20261021T033444806185.json`：提交代码、工作区状态、
  被试、依赖任务、完整命令、调度上限和恢复作业；
- `submitted_retry_20261021T033444806185.csv`：两名补交被试的作业号和完整 sbatch 命令。

未生成本地数据或测试产物；本次只更新本会话记录，随后通过 Git 同步。
