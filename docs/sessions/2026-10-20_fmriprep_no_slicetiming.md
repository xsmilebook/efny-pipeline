# 2026-10-20：独立生成不做切片时间校正的 fMRIPrep

## 请求与决策

用户要求直接修改主脚本，添加 `--ignore slicetiming`，同时保留现有结果；
后续拟将不做切片时间校正的版本作为主分析。

当前工作端为 Windows，项目根目录 `D:\projects\efny-pipeline`。
已阅读 `ARCHITECTURE.md` 和 `docs/cluster_usage.md`；修改前 `main` 工作区干净。
未连接集群、提交作业或改动 `data/`、`outputs/` 中的运行产物。

## 实现与科学影响

- 主入口仍为 `scripts/neuroimaging/run_fmriprep.sbatch`，根据配置的
  `fmriprep.ignore=["slicetiming"]` 传入 `--ignore slicetiming`。
- 新版本的全部影像模块路径在数据集目录后加入 `no_slicetiming/`。
  fMRIPrep 输出为 `data/interim/neuroimaging/fmriprep/THU/no_slicetiming/rest/`；
  工作目录、容器临时目录、FreeSurfer、输入清单、完成记录、Slurm 日志和下游路径均隔离。
- FreeSurfer 使用新目录，会重新生成解剖重建；不自动复制或改写旧结果。
- 关闭切片时间校正是用户明确指定的方法变更，可能影响 BOLD 与后续 FC；
  其余参数、镜像、6／6 线程、分区、代理和跳过 BIDS 验证行为保持原值。
- 后续可直接把 `no_slicetiming/` 指定为主分析，无需覆盖旧目录。
- README、结构说明、方法文档及参考参数对照已同步；方法文档提供沿用原被试清单的命令。

## 正式运行边界

集群根目录仍为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，
THU 输入仍为 `/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`，
镜像仍为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/packages/singularity/fmriprep_25.2.5.sif`。
XY 输入继续留空。本次没有新作业编号或实际容器版本验证。
集群正式运行前先检查工作区和分支，再拉取提交；使用独立的新输入清单和小规模计算节点验证。
正式运行记录代码提交、工作区状态、命令、输入范围、输出位置、软件版本及作业编号。

## 验证

本地使用既有 `.venv` 的 Python 3.12.9 和 Git Bash，运行：

```powershell
$env:EFNY_TEST_BASH = 'C:\Program Files\Git\bin\bash.exe'
uv run --python 3.12 --offline --no-sync python -m unittest discover -s tests -p test_neuroimaging.py -v
```

16 项检查全部通过，包括新旧版本路径／完成记录隔离、下游 fMRIPrep 读取路径、
FreeSurfer／缓存隔离和模拟容器命令中的 `--ignore slicetiming`。
既有时间轴、头动、QC、ROI 顺序及 FC 计算验证也全部通过。
模拟验证使用临时合成数据，不代表真实容器或集群验证。
已确认 `temp/smoke_neuroimaging_*` 无残留，`git diff --check` 通过。
修改前基线提交为 `c36403e`；本次修改另行提交，未推送或切换到集群。

## 后续请求：最多同时运行 48 个 fMRIPrep 任务

用户进一步要求并发上限为 48。以 `8c8cf1f` 为本次修改基线，工作区干净。
`slurm.fmriprep_max_concurrent` 设为 48，现有 fMRIPrep 提交入口改为一次提交
`--array=0-N%48` 的 Slurm 被试数组；每个任务仍申请 6 核，使用原来的主脚本与分析参数。
限流作用于单个新提交数组，不修改已提交任务或账号全局限额；其他阶段仍逐被试提交。

每次提交独立保存 `array_subjects_<timestamp>.txt`，数组索引从 0 开始，
不读取后续可能改变的输入清单进行重新映射。提交回执逐被试保存数组任务编号。
解析被试和路径前的启动错误留在 `array_%A_%a.out/.err`，之后处理日志继续按被试命名，
以兼容原有完成检查。dry-run 不写文件、不提交作业。
README、集群说明和方法文档已同步；本次未连接集群或提交正式任务。

使用上述 Python 3.12.9／Git Bash 命令复查，17 项检查全部通过。
新增 49 人提交模拟核对 `--array 0-48%48`、一次 sbatch 调用、逐被试回执及固定清单，
并验证修改原始子集文件不会改变已提交的数组映射。
模拟数组任务 0 使用倒序清单选中正确被试，命令、完成记录和按被试命名的日志均正确。
首次本地模拟发现 Windows 默认 CRLF 与 Bash `mapfile` 的差异；
固定数组清单已显式使用 LF 写入，随后完整检查通过。
临时合成数据已清理；未验证真实调度器的并发行为或当前 `MaxArraySize`，
未提交集群作业、修改已有任务或推送代码。

## 后续请求：使用 high_c 调度服务等级

用户要求增加 `high_c` 作为优先级规则。修改前基线为 `b61c17b`，工作区干净。
已读取 `D:\projects\personalized_prediction\docs\cluster_usage.md`，其中 QoS 列将
`high_c` 列为 `q_fat_c` 的服务等级；已核对 Slurm 官方 `sbatch` 文档，命名 QoS
通过 `--qos` 请求，而 `--priority` 接受数值或 `TOP`，不接受 QoS 名称。

统一配置新增 `slurm.fmriprep_qos="high_c"`，fMRIPrep 数组提交命令显式传入
`--qos high_c`，主脚本设置 `#SBATCH --qos=high_c`，使直接 sbatch 也采用该默认值。
保留分区 `q_fat_c`、48 个并发任务上限、每被试 6 核及所有分析参数和结果路径。
README 和集群说明同步更新。未连接集群、核验当前账号 QoS 权限或修改已有作业。

本地运行既有提交检查：

```powershell
uv run --python 3.12 --offline --no-sync python -m unittest discover -s tests -p test_neuroimaging.py -k submission -v
& 'C:\Program Files\Git\bin\bash.exe' -n scripts/neuroimaging/run_fmriprep.sbatch
```

2 项提交检查、Bash 语法检查和 `git diff --check` 全部通过；临时验证目录无残留。
本次未提交集群任务或推送代码。

## 正式提交：731 人不做切片时间校正的 fMRIPrep

用户随后明确要求代为提交。2026-10-20 20:52（北京时间）已完成以下操作：

- 本地 `main` 工作区干净，将前述 3 个提交推送到 `origin/main`。
  通过 `CIBR-login` 连接 `login01`，检查集群工作区干净且分支为 `main` 后，
  使用 `git pull --ff-only origin main` 更新至 `3b8bf3699b9c013b4f06dbe6faae9486491ac759`。
- 确认当前账号允许 `high_c`；Slurm `MaxArraySize=18000`，足够容纳本批。
  原始 731 人清单、fMRIPrep 成功名单和参考成功名单人数一致；新版本尚无结果或提交记录。
  本批沿用原清单，重新发现 731 人、2459 个静息态 run，均有 T1w 输入。
- 集群根目录为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`；输入为
  `/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
  确认配置中的 fMRIPrep 镜像、FreeSurfer license 和 TemplateFlow 路径可访问。
- 集群 Python 为 3.11.15；`uv sync --check --offline --frozen --python 3.11
  --python-platform x86_64-manylinux_2_17` 和 `uv pip check --python .venv/bin/python`
  均通过，环境无须更新。镜像配置版本为 fMRIPrep 25.2.5，提交时尚未进行实际容器启动验证。

从集群项目根目录执行的命令为：

```bash
uv run --offline --no-sync efny-imaging prepare --dataset THU \
  --subjects outputs/logs/neuroimaging/fmriprep/THU/rest/subjects.txt
uv run --offline --no-sync efny-imaging run --stage fmriprep --dataset THU \
  --subject sub-THU202311180133 --dry-run
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU --dry-run
uv run --offline --no-sync efny-imaging submit --stage fmriprep --dataset THU
```

容器命令预览确认 `--ignore slicetiming`、独立输出／工作／临时／FreeSurfer 目录和
6／6 线程。正式提交代码为上述 `3b8bf36`，提交时工作区干净。
Slurm 数组作业 **15427951**，索引 `0-730%48`，`ArrayTaskThrottle=48`，
分区 `q_fat_c`、QoS `high_c`、每任务 6 核；调度器分配内存规则为每核 20 GB，
未额外设置内存或运行时限。首次状态为 `PENDING / Resources`，不代表分析完成。

新 fMRIPrep 输出为
`data/interim/neuroimaging/fmriprep/THU/no_slicetiming/rest/`；
清单及日志位于 `outputs/logs/neuroimaging/fmriprep/THU/no_slicetiming/rest/`：

- `array_subjects_20261020T125230908442.txt`：固定的数组索引到被试对应关系；
- `submitted_20261020T125230908442.csv`：731 名被试的数组任务编号与完整 sbatch 命令；
- `submission_20261020.json`：提交时间、代码、工作区、输入范围及输出位置。

本次只提交 fMRIPrep，未提交下游阶段，旧结果保持原位。
真实容器版本、完成产物和科学 QC 需在运行后检查；未把已提交或排队解释为已完成。
