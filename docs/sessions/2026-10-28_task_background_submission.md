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

控制入口第一版 `40f9ebc` 已推送并在集群干净工作区快进同步。依赖 prepare 的试跑控制作业为 `15459638`，registry 为 `outputs/logs/neuroimaging/xcpd/THU/task_background/run_20261028T1650.json`，初始化时记录实际运行代码 commit。完整提交参数为 `sbatch --parsable --dependency=afterok:15459635 --kill-on-invalid-dep=yes --job-name=thu_background_pilot --output=outputs/logs/neuroimaging/xcpd/THU/task_background/pilot_all_%j.out --error=outputs/logs/neuroimaging/xcpd/THU/task_background/pilot_all_%j.err scripts/neuroimaging/submit_task_background.sbatch pilot outputs/logs/neuroimaging/xcpd/THU/task_background/run_20261028T1650.json`。

额外补充真实残差投影门槛：通过读取已配置 26.0.2 镜像内 `xcp_d/utils/utils.py` 核实 detrend→同带通→回归的实际顺序及 padding。批量控制阶段在同镜像中调用 `audit_task_pilot_residuals.py`，要求三套图谱残差与滤波后联合设计的最大归一化内积 <1e-5，记录滤波后设计秩。保留 task 信号的合成反例必须被拒绝；不改变正式回归参数，不向项目 uv 环境新增 Nilearn／SciPy。

该检查的代码为 `81113d5`，已推送并同步。计算节点同镜像的两个合成检验在作业 `15459646` 中通过：去除信号的 float32 残差通过，特意保留 task 信号的反例被拒绝，测试运行 5.417 秒，Slurm COMPLETED、0:0、总耗时 10 秒。试跑控制依赖更新为 `afterok:15459635:15459646`，使用 `q_fat_c`、1 CPU；测试目录由 TemporaryDirectory 自动清理。容器内命令为 `python -m unittest discover -s tests -p test_task_pilot_residuals.py -q`，宿主 OMP／OpenBLAS／MKL／NumExpr 均限制 1 线程。

完整准备的 SST 部分已通过：562/567 run 就绪，111 个偏移 0.96、451 个偏移 0.959；5 个阻塞项均缺少 TSV 和 JSON，没有时间错位或非有限设计。实际 SST 代表样本覆盖两种偏移 × 有／无 cue 四个组合，其余两个任务仍在同一准备作业顺序审计中。

补充 task 残差 TR 与原始 BOLD 的直接对照，防止 denoised CIFTI 和三个 ptseries 彼此一致、却共同带有错误 TR 的静默问题；rest 规则不变。新增反例测试将残差与 ptseries 同时从 2 秒改为 3 秒，必须拒绝。集群 uv 环境实测 Python 3.11.15、NumPy 2.2.6、NiBabel 5.4.2；镜像实测 XCP-D 26.0.2、Python 3.12.12、Nilearn 0.12.1、NumPy 2.2.6、SciPy 1.15.2。

## 实际试跑与当前状态

完整 prepare `15459635` 已 COMPLETED、0:0，用时 14:54：sst 562/567、nback 513/521、switch 432/434；合计 1,507/1,522 个 run 就绪。所有现有文件均通过，15 个阻塞项均为缺少 custom TSV／JSON，没有额外科学不一致。1,507 个 run 逐 task 冻结，8 个试跑包括 SST 的 0.96／0.959 × 有／无 cue 四种组合，nback 和 switch 各覆盖两种偏移。

试跑控制 `15459638` 已 COMPLETED、0:0，用时 8 秒，记录分析代码 `f406745`、干净工作区，registry 为 `run_20261028T1650.json`。

| 任务 | 被试 | 实际 XCP-D 作业 |
| --- | --- | --- |
| sst | sub-THU202311180133 | 15459667 |
| sst | sub-THU202311180134 | 15459668 |
| sst | sub-THU202507100634 | 15459669 |
| sst | sub-THU202507110640 | 15459670 |
| nback | sub-THU202311180133 | 15459671 |
| nback | sub-THU202311180134 | 15459672 |
| switch | sub-THU202311180133 | 15459673 |
| switch | sub-THU202312170155 | 15459674 |

已确认八个作业均在 fat14 RUNNING，stdout 显示实际 XCP-D 26.0.2 正在构建工作流，参数为 36P＋task、1/1 线程、三套图谱。stderr 当前仅环境只读检查及预期的“FD scrubbing disabled，min-time 无效”提示，无已见异常堆栈。实际去噪、联合设计验收和残差投影尚未完成。

批量控制 `15459675` 已提交，依赖 `afterok:15459667:15459668:15459669:15459670:15459671:15459672:15459673:15459674`，`--kill-on-invalid-dep=yes`；先再次审计全部八个试跑及其真实残差投影，再提交 SST 558、nback 511、switch 430，合计 1,499 个剩余被试×任务作业，并分别安排全批完成审计。当前为依赖等待状态，不能将这 1,499 项写为已提交或已完成。

本地最终测试共发现 39 项：37 项通过、2 项因本地无 Nilearn 跳过；这两项已在上述 XCP-D 镜像的作业 `15459646` 通过。新增 TR 反例最初因 Windows 内存映射文件覆盖失败，修为测试读取 `mmap=False` 后完整复跑通过（12.974 秒），分析逻辑无变更。该失败遗留 `D:\projects\efny-pipeline\temp\smoke_task_background_5e81whes`；对这一明确自有测试目录的路径边界验证与 `Remove-Item -LiteralPath ... -Recurse -Force` 被自动审批策略拒绝，未使用其他手段绕过，目录暂留。后续正常测试目录自动清理。
