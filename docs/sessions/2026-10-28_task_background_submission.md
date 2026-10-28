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
