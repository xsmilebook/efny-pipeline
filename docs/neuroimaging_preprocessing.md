# 静息态 BIDS 预处理、头动与功能连接

## 范围与配置

本流程参考 `D:\projects\data_driven_EF\scripts\neuroimaging` 中的 fMRIPrep、XCP-D、
头动及 FC 脚本。按用户确认，仅处理静息态 `task-rest`，要求每名被试至少 2 个合格 run。
所有输入必须无 `ses-*` 目录，并采用 `sub-*/func/*_task-rest_run-*_bold.nii[.gz]`。
run 编号可以不连续，按整数排序，不限制为参考项目的 run 1–4；重复 run 编号、session
或多回波输入明确报错，不猜测如何合并。

统一配置为 `configs/neuroimaging.json`，模块路径定义见 [ARCHITECTURE.md](../ARCHITECTURE.md)。

fMRIPrep 和 XCP-D 的完整分析命令分别写在
[`run_fmriprep.sbatch`](../scripts/neuroimaging/run_fmriprep.sbatch) 和
[`run_xcpd.sbatch`](../scripts/neuroimaging/run_xcpd.sbatch)。输出空间、回归、滤波、平滑、
censoring 和 run 合并等参数在对应命令中逐项列出，便于科研人员查看分析逻辑。
配置文件保留共享路径和可调参数值，`src/imaging/` 负责路径解析、输入清单、Slurm 提交、
时间轴／产物审计和头动／FC 计算，不再组装 fMRIPrep／XCP-D 容器命令。
修改命令中的固定科学选项后，应同步方法说明及相关审计假设，并重跑该阶段与下游。

| 配置项 | 当前值 |
| --- | --- |
| 集群项目根目录 | `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline` |
| THU BIDS 输入 | `/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new` |
| THU 被试前缀 | `sub-THU` |
| XY BIDS 输入 | 暂未确定，配置值为 `null`，填写前禁止运行 |
| XY 被试前缀 | `sub-XY` |

输入在容器中只读挂载，全部衍生数据、FC、QC 和日志写入项目根目录下的生产模块。
THU 与 XY 分别建立输入清单、QC 分布和结果，不跨数据集混合。当前不配置数据同步。

2026-10-06 按用户要求，将集群开发目录与结果根目录统一到上述路径。
此前 `DATA_C/projects/efny-pipeline` 下的 THU fMRIPrep／FreeSurfer 衍生结果、工作缓存和
容器临时目录在作业停止后删除；历史提交清单及失败日志保留用于追溯。新批次重新生成
输入清单，fMRIPrep、XCP-D、头动和 FC 的生产端与读取端均使用同一新根目录，
不读取旧路径作为回退。清理及重新提交的记录见
[当日会话记录](sessions/2026-10-06_thu_fmriprep_submission.md)。

## 环境与外部资源

登录节点在项目根目录准备 Python 3.11 环境，计算节点只读使用：

```bash
uv sync --frozen --python 3.11 --python-platform x86_64-manylinux_2_17 --link-mode copy
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17
uv run --offline --no-sync python -c "import numpy,nibabel; print(numpy.__version__,nibabel.__version__)"
```

Python 依赖仅新增 NumPy 与 NiBabel。NumPy 固定为 2.2.6，锁文件包含 Linux／Windows wheel；
实际集群导入验证仍需执行上述命令。本地可用 Python 3.11 或 3.12，分别建立 `.venv`。

参考项目的容器与共享资源路径写入配置的 `tools`：

- `singularity/3.7.0` 模块；
- `fmriprep_25.2.5.sif`、`xcp_d-26.0.2.sif`；
- FreeSurfer `license.txt` 与 TemplateFlow 缓存。

这些路径来自参考项目。2026-10-06 已确认 fMRIPrep 镜像、license 和 TemplateFlow 路径可访问，
并通过计算节点挂载与版本启动检查；XCP-D 镜像及完整模板／图谱覆盖仍需在该阶段运行时核验。
fMRIPrep／XCP-D 沿用参考代理 `http://10.11.100.5:3128`，设置宿主 HTTP／HTTPS／FTP／ALL
大小写代理变量，并通过对应 `SINGULARITYENV_*` 传入 `--cleanenv` 容器，以保留需要时的网络访问。
本次未核验代理连通性。镜像、Python 依赖及所需模板仍优先在登录节点准备。
TemplateFlow 在容器内只读挂载为 `/templateflow`。

XCP-D 26.0.2 默认从镜像中的 `/home/xcp_d/.cache/xcp_d/XCPDAtlases` 与
`/home/xcp_d/.cache/xcp_d/AtlasPack` 读取图谱。如果站点镜像未包含所需资源，应先准备
独立的 BIDS-Atlas 数据集，在 `tools.atlas_datasets` 中填写 `xcpdatlases` 和 `xcpd4s`
对应的宿主路径；程序以只读挂载和 `--datasets` 显式传入。
该行为依据 [XCP-D 26.0.2 参数解析源码](https://github.com/PennLINC/xcp_d/blob/26.0.2/xcp_d/cli/parser.py)，
不会自动寻找其他图谱缓存，图谱数据集需提前准备。

## 科学方法

### fMRIPrep

沿用参考版本 25.2.5 和输出空间 T1w、MNI152NLin2009cAsym、MNI152NLin6Asym、fsLR、
fsaverage，生成 91k CIFTI，并保留全部 CompCor components。仅选择 `task-rest`，
不设置忽略 slice timing 或 fieldmap 的参数。沿用 `--skip-bids-validation` 跳过 BIDS 验证；
不另加预验证步骤，运行失败后再根据日志检查输入格式与元数据。
FreeSurfer 按数据集独立保存。随机种子固定为 42，默认每个被试申请 6 核。
容器明确使用 `--nprocs 6 --omp-nthreads 6`，与参考脚本一致；不额外注入单线程环境变量。
参数已对照 [fMRIPrep 25.2.5 使用说明](https://fmriprep.org/en/25.2.5/usage.html)。
与参考脚本存在的其他参数差异及原因见[逐项对照](neuroimaging_reference_audit.md)。

### XCP-D

沿用参考版本 26.0.2：36P、无空间平滑、无 despike、二阶 0.01–0.1 Hz 带通，
运动参数采用 6 BPM 低通，head radius 为 auto；不合并 run。
36P 包含全局信号项。默认 `dummy_scans=0`，不额外删除开头帧；
`--fd-thresh=0` 禁用逐帧 censoring，虽指定输出类型 censored，默认仍保留全部帧。
头动 QC 后纳入整个 run，而非删除该 run 内高头动帧。
参数含义见 [XCP-D 26.0.2 使用说明](https://xcp-d.readthedocs.io/en/26.0.2/usage.html)。

仅生成后续使用的 4S156Parcels、4S256Parcels、4S456Parcels 图谱输出，默认每被试 1 核。
这三套图谱分别含 100／200／400 个 Schaefer 皮层节点及 56 个非皮层节点，因此最终矩阵
为 156×156、256×256、456×456，不命名为纯 Schaefer100／200／400。

### 头动 QC

读取 fMRIPrep confounds 的原始 `framewise_displacement`，单位为 mm，
不使用 XCP-D 运动滤波后的 FD。先验证原始 BOLD 与 confounds 总帧数一致，再按
`dummy_scans` 切取与 XCP-D 相同的窗口。仅允许第 1 帧 FD 因差分未定义而为 `n/a`／NaN／空值；
其他帧的缺失、非有限值或负值立即报错。

沿用参考计分口径：mean FD 的分母为有效 FD 数；高头动比例为 FD > 0.3 mm 的帧数
除以分析窗口总帧数，第 1 帧若 FD 未定义仍计入总帧数。表中明确保存总帧数、有效 FD 数
与首帧缺失标记。默认不删首帧时，有效 FD 数通常比总帧数少 1。

在每个数据集的全部纳入 run 内，使用 inclusive quartile 计算 Q1、Q3：

- run mean FD ≤ Q3 + 1.5 × IQR；
- FD > 0.3 mm 的帧比例 ≤ 0.25；
- 被试至少 2 个合格 run。

拟合 IQR 阈值至少需要 4 个 run。小样本容器验证不改变正式 QC 规则；只有一个合格 run
的被试明确标记为不合格，保留 QC 表，不自动删除原始或衍生数据。
重跑任何头动输入后需重新计算该数据集完整 QC，再提交 FC，避免沿用旧群体阈值。

### 功能连接

读取 XCP-D 的 `*_atlas-4S*Parcels_den-91k_stat-mean_timeseries.ptseries.nii`。
通过 CIFTI SeriesAxis／ParcelsAxis 确定时间和 ROI 方向，核验节点数、标签唯一性、
run 间标签顺序、TR 及与头动窗口一致的帧数。
非有限信号或零方差 ROI 会报错，不将缺失或无效相关填成零。

按整数 run 编号拼接合格 run，保留每个 run 原有均值和振幅，不额外做 run 内标准化。
以拼接后的帧为观测计算 Pearson r。Fisher z 使用 `atanh(clip(r,-0.999999,0.999999))`；
r 对角线为 1，z 对角线为 0，均保存有明确 ROI 行列标签的 CSV。
该拼接口径用于延续参考分析，跨 run 的均值／振幅差异会影响合并相关。

## 分阶段提交

以下命令从集群项目根目录执行。不要在上游作业仍运行时执行完成检查或提交下游；
本入口不自动等待作业，也不自动提交整条长流水线。

```bash
cd /ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline

# Build the THU source inventory, without modifying BIDS.
uv run --offline --no-sync efny-imaging prepare --dataset THU

# Review commands, then submit one job per subject.
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU --dry-run
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU

# After fMRIPrep jobs finish, audit each expected run before XCP-D submission.
sbatch --output=outputs/logs/neuroimaging/fmriprep/THU/rest/reference_check_%j.out \
  --error=outputs/logs/neuroimaging/fmriprep/THU/rest/reference_check_%j.err \
  scripts/neuroimaging/check_fmriprep_success.sbatch THU \
  /ibmgpfs/cuizaixu_lab/xuhaoshu/projects/data_driven_EF/scripts/neuroimaging/check_fmriprep_success.sh
# Wait for the audit job to succeed before submitting XCP-D.
uv run --offline --no-sync efny-imaging submit --stage xcpd --dataset THU --dry-run
uv run --offline --no-sync efny-imaging submit --stage xcpd --dataset THU

# After XCP-D jobs finish, audit outputs and submit original-FD summaries.
uv run --offline --no-sync efny-imaging check --stage xcpd --dataset THU
uv run --offline --no-sync efny-imaging submit --stage head_motion --dataset THU

# After head-motion jobs finish, fit dataset-wide QC and submit eligible subjects.
uv run --offline --no-sync efny-imaging qc --dataset THU
uv run --offline --no-sync efny-imaging submit --stage rest_fc --dataset THU --dry-run
uv run --offline --no-sync efny-imaging submit --stage rest_fc --dataset THU
```

默认 XCP-D 仅提交完成 fMRIPrep 审计的被试，头动仅提交完成 XCP-D 审计的被试，
FC 仅提交 QC 合格被试。完成审计为每个缺失或未完成被试保存原因及失败名单，需阅读
`completion_audit.csv` 处理失败项；不会把存在旧 HTML 或旧日志成功字样等同于本次完成。
如果准备的输入清单包含上游失败被试，QC 会因缺少其已完成头动结果而停止。
应先补齐失败任务；若研究者明确决定缩小分析样本，应使用审核后的完整被试名单重新
`prepare --subjects <path>`，并记录排除理由后重新审计，不自动排除。

`--subjects <path>` 可用于首次少量被试提交或重跑失败名单，每行一个 `sub-*`，
文件可使用 Windows CRLF。`prepare --subjects` 定义分析清单，`submit --subjects`
仅缩小本次提交范围，不改变分析清单；不要用小规模测试的清单拟合正式群体阈值。
核数和队列由配置统一决定，不设置 Slurm time／mem。
四个阶段仅使用 `q_fat_c`；fMRIPrep 默认 6 个 CPU，其他阶段各 1 个 CPU。
直接使用 sbatch 入口时，脚本头部也采用上述默认值；fMRIPrep 固定使用 6／6，
XCP-D 的 `--nprocs` 读取实际 Slurm CPU 配额，默认 1，`--omp-nthreads` 为 1。
不自行提高 fMRIPrep 默认并行数，以控制 FreeSurfer 等步骤的内存压力。

需要预览单被试容器命令时：

```bash
uv run --offline --no-sync efny-imaging run --stage fmriprep --dataset THU --subject sub-THUXXXX --dry-run
uv run --offline --no-sync efny-imaging run --stage xcpd --dataset THU --subject sub-THUXXXX --dry-run
```

以上预览会调用对应 sbatch 脚本输出完整容器命令；也可直接在 Bash 中预览：

```bash
bash scripts/neuroimaging/run_fmriprep.sbatch THU sub-THUXXXX configs/neuroimaging.json "$PWD" --dry-run
bash scripts/neuroimaging/run_xcpd.sbatch THU sub-THUXXXX configs/neuroimaging.json "$PWD" --dry-run
```

`sub-THUXXXX` 必须替换为准备清单中的真实被试。XY 填写 BIDS 路径后，用相同命令的
`--dataset XY` 执行，结果自动分开。`--project-root` 用于明确指定独立验证根目录；
Slurm 提交时须保证该根目录存在代码与 `.venv`，正式配置仍使用用户给定的集群根目录。

## 完成、恢复与验证

fMRIPrep 全批判定先执行参考项目的 `check_fmriprep_success.sh`：HTML 无错误、日志成功结束，
且每个原始静息态 BOLD 都有对应 fsLR 91k CIFTI、MNI 预处理 BOLD 和 confounds。
`check_fmriprep_success.sbatch` 保留参考判断逻辑，只适配统一配置路径和本项目下划线日志命名；
保存实际执行脚本、参考成功／失败名单，再执行原有 `efny-imaging check` 的来源和时间轴检查。
两套成功／失败名单必须完全一致，否则审计作业失败，不能继续提交下游。
缓存清理和 XCP-D 试跑后批量提交见[专用说明](fmriprep_cleanup_xcpd.md)。

每个容器运行成功后检查所有预期 run、HTML、dataset description、时间轴和图谱产物，
再写入模块日志中的 `completed/<subject>.json`，记录实际命令、版本、代码 commit、
工作区状态、科学配置和上游完成时间。上游重跑后，下游旧完成记录失效。
容器版本检查也使用完整处理命令的挂载及环境，再追加 `--version`；
TemplateFlow 在 CLI 导入阶段就需要访问缓存，不能在设置 `/templateflow` 环境变量后无挂载启动。
不比较或记录文件内容 SHA-256。

同一模块／被试使用独立锁目录，防止同时写出。正常失败会释放锁；强制终止留下锁时，
先检查相应 Slurm 作业和进程确已停止，再清理该被试的锁，不自动删除所有锁。
作业不自动清理正式衍生数据、工作缓存或容器临时目录，清理时只能操作本模块自有路径。

本地定向验证命令：

```bash
uv run --offline --no-sync python -m unittest discover -s tests -p test_neuroimaging.py -v
```

验证使用合成 NIfTI／confounds／CIFTI，覆盖时间轴、首帧 FD、QC、拼接 FC、ROI 顺序、
无效信号报错、路径配置与完成记录。安装 Bash 时还会实际执行两份作业脚本，以模拟容器
验证命令预览、运行后审计、失败状态和锁释放。Windows 下显式设置
`EFNY_TEST_BASH` 为 Git Bash 的 `bash.exe` 路径；未设置时跳过该项 Bash 集成验证。
容器调用在测试中模拟，不能替代集群实测。
测试产物位于 `temp/smoke_neuroimaging_*`，结束立即清理；首次正式批量计算前应在相同
计算环境提交少量真实被试，检查 fMRIPrep 与 XCP-D HTML、日志和科学 QC。
