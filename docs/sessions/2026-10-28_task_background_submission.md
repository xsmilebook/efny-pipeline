# THU task background XCP-D 实际提交

## 授权与来源

用户确认现有路径下文件已修正，授权实现并实际提交 XCP-D。沿用已有 36P＋HRF task nuisance、XCP-D 26.0.2、0.01–0.1 Hz、dummy 0、无 censoring、三套 4S 图谱及 1 CPU／1/1 线程，不重新生成外部协变量或重跑 fMRIPrep。

- 集群根目录：`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
- 输入 BIDS：`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
- task fMRIPrep：`data/interim/neuroimaging/fmriprep/THU/task/`。
- custom：`/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK`，生成器 `build_task_confounds.py` 1.4.0。
- 输出：`data/interim/neuroimaging/xcpd/THU/task_background/<task>/`；缓存、日志同名隔离，具体见 ARCHITECTURE。

16:37–16:39 的 live 检查：上游仍为 1,522 run／569 人；现有 1,507 份 confounds 均匹配上游，无多余项。nback 513/521、sst 562/567、switch 432/434，15 个缺失 run 不补齐。抽查 `FrameTimeOffsetSeconds` 已为对应 StartTime，并以 `FrameTimeOffsetSource` 和参考 JSON 明确记录来源。完整 CIFTI 与 TSV 审计通过计算节点运行，避免登录节点批量解析。

集群 Git 工作区干净，由 `20b1249` 快进至 `ba7a13c`。登录节点只读离线 uv 环境检查通过，Python 环境在仓库 `.venv`，未新增依赖。上游 retry 数组 `15438019` 六个元素及审计 `15438020` 均为 COMPLETED、0:0；未操作其他正在运行的作业。

## 作业与推进规则

完整 prepare 作业 `15459635` 已提交 `q_fat_c`、1 CPU，代码 `ba7a13c`、工作区干净，运行三个 task 的 `efny-imaging prepare --stage xcpd --scope task`。完整命令：

```bash
sbatch --parsable --job-name=thu_task_background_prepare \
  --output=outputs/logs/neuroimaging/xcpd/THU/task_background/prepare_%j.out \
  --error=outputs/logs/neuroimaging/xcpd/THU/task_background/prepare_%j.err \
  scripts/neuroimaging/prepare_task_background.sbatch THU configs/neuroimaging_stc.json
```

新增 `submit_task_background.sbatch`：先冻结就绪范围并选取覆盖采样偏移／SST cue 协议的试跑；afterok 控制作业检查所有任务试跑的实际产物、联合设计、帧数、TR、ROI 与完成记录，全部通过才提交剩余批次，最后分别安排三个任务完成审计。缺失 run 有明细，其他科学问题一律阻塞，不自动排除或修正。部分提交失败时保留每个成功回执，禁止重复初始化。代码或配置在试跑后改变时停止推进；仅文档提交不改变分析设置。

本地 36 项 unittest 全部通过（12.185 秒），包含原 34 项科学与命令验证，以及“现有但不合格的设计阻止全部任务提交”“任一任务试跑完成审计失败阻止全部正式批次”两项新增验证。新 sbatch 通过 `bash -n`，`git diff --check` 通过；合成测试临时目录自动清理。验证代码为 `ba7a13c` 加本轮提交内容，Git Bash 入口与前次一致。

试跑与批量运行尚未完成。后续作业号和验证结果继续补充于此；不以提交状态声明全批分析成功。
