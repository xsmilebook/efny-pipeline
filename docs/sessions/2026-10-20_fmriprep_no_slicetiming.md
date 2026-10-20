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
