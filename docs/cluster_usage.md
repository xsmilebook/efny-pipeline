# 本地与集群使用说明

## 来源与适用范围

本手册参考同一集群的 `personalized_prediction/docs/cluster_usage.md`（本地参考仓库为
`D:\projects\personalized_prediction`），于 2026-10-06 整理。下列分区、内存和模块信息
来自该项目既有记录，本次未连接集群核验；首次部署时需确认当前站点配置和可用模块。

本项目包含 MATLAB DICOM/BIDS 转换、Python 序列目录清单，以及静息态 fMRIPrep／XCP-D／
头动／FC 的 `efny-imaging` 和四个 sbatch 入口，详见[影像流程](neuroimaging_preprocessing.md)。
尚未完成计算节点验证；现有 Windows MATLAB 转换入口仍需单独调整路径和 worker 数。

## 两端开发与路径

- 代码与文档通过 Git 交换。切换开发端前提交并推送；另一端先运行 `git status` 检查工作区，
  确认分支后使用 `git pull --ff-only` 拉取。有本地修改或分叉时先处理，不自动覆盖。
- Windows 与 Linux 各自维护仓库根目录 `.venv`，不复制虚拟环境。
  已有的 `pyproject.toml`、`uv.lock` 通过 Git 管理。
- 数据和结果各端独立管理，当前不配置镜像、双向同步或自动传输。缺少输入时明确停止相关运行，
  不假设另一端已有数据等于当前端已就绪。
- 本地项目根目录为 `D:\projects\efny-pipeline`。集群项目根目录由用户确定为
  `/ibmgpfs/cuizaixu_lab/xuhaoshu/DATA_C/projects/efny-pipeline`；THU BIDS 输入为
  `/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
  XY 输入暂未确定，不直接套用 THU 或参考项目的路径。MATLAB 转换的原始输入、NIfTI
  和事件替换目录仍需单独确认。
- 沿用已有入口参数或入口顶部的路径设置，明确当前端输入、输出和工具路径。
  数据可以位于仓库外；仓库内输出归属仍遵循 [ARCHITECTURE.md](../ARCHITECTURE.md)。

当前 `run_dicom2bids_checked.m` 使用 Windows 绝对路径、Windows 版 `dcm2niix.exe`
和固定 4 个 worker；`run_psychopy2bids_checked.m` 也使用 Windows 绝对路径。
首次集群运行需显式调整入口路径与 worker 数，并提交这些改动后再记录正式运行版本。
跨平台路径设置应留在入口，不复制不同版本的科学转换逻辑。

## CPU 资源与 Slurm 约定

参考手册记录的 CPU 资源如下；节点数和内存为既有记录，不表示当前空闲资源。

| 分区 | 节点数 | 每节点核心 | 单核对应内存 | 每节点总内存 |
| --- | ---: | ---: | ---: | ---: |
| `q_fat` | 2 | 72 | 40 GB | 3072 GB |
| `q_fat_c` | 8 | 72 | 20 GB | 1536 GB |
| `q_fat_l` | 3 | 72 | 20 GB | 1536 GB |

- 按本项目约定，所有 sbatch 仅使用 `q_fat_c`，写为 `#SBATCH -p q_fat_c`。
  上表其他分区仅为参考手册的历史资源记录，不用于本项目提交。
- 按该站点既有约定，不在 sbatch 中设置 `--time`、`--mem` 或 `--mem-per-cpu`；
  用 `--cpus-per-task` 申请 CPU，内存随申请核数分配；按参考记录，`q_fat_c` 的 6 核约对应 120 GB。
- fMRIPrep 默认每被试申请 6 个 CPU，以控制 FreeSurfer 等步骤的并发内存压力；
  XCP-D、头动和 FC 默认各 1 个 CPU。fMRIPrep／XCP-D 的 `--nprocs` 读取
  `SLURM_CPUS_PER_TASK`，`--omp-nthreads=1`。提交配置与脚本头部的默认资源保持一致。
- 当前 MATLAB 本地进程池任务应使用单节点、`--ntasks=1`，worker 数与
  `SLURM_CPUS_PER_TASK` 对应；不按整节点核数或本地机器设置额外扩展。
- 登录节点仅做短时、低资源检查。批量转换、并行任务和长时间分析通过 Slurm 执行；
  小规模验证使用与正式任务相同的计算环境。
- 从项目根目录提交，作业内使用 `cd "${SLURM_SUBMIT_DIR}"`，并使用 `set -euo pipefail`。
- 作业日志按生产模块放入 `outputs/logs/<module>/`，文件名含 `%j` 作业编号。
  提交前创建 sbatch 实际声明的日志父目录；Slurm 在运行脚本前打开日志文件，不会代为创建目录。
- worker 之间不写同一被试输出目录。转换任务读写大量小文件，应根据少量被试验证评估
  共享文件系统压力后确定核数，不直接照搬参考项目的 24 或 72 核。

## MATLAB 与外部工具

参考手册使用 `module load MATLAB/R2022a`，本项目既有本地静态检查使用 MATLAB R2025a。
集群可用版本及 Parallel Computing Toolbox／worker 许可需在部署时确认；尚未验证 R2022a
对本项目全部脚本的兼容性。集群使用 Linux 版 `dcm2niix`，记录其实际版本和可执行文件路径。

进程并行时将每个 worker 的 OpenMP、OpenBLAS、MKL 和 NumExpr 线程限制为 1，避免嵌套并行：

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
```

MATLAB 批处理使用 `-batch`，进程池任务可使用 `-singleCompThread` 限制数值计算线程；
入口仍需显式将 worker 数设置为作业申请值，这些选项不会自动修改当前入口的固定 4 个 worker。

## Python 环境与离线计算节点

原有 `export_series_folders.py` 仅使用标准库；新影像流程的 Python 依赖由
`pyproject.toml` 和 `uv.lock` 管理，包含 NumPy 和 NiBabel，提供 `efny-imaging` 命令。
Windows 与 Linux 各自运行 `uv sync --frozen` 建立仓库根目录 `.venv`。
默认 Python 版本为 3.11；本地也可显式使用 `uv sync --frozen --python 3.12`。

参考手册记录的计算节点无网络，使用 Python 3.11 和 glibc 2.17。依赖在有网络的登录节点
准备，计算节点只读取项目共享文件系统中已准备的 `.venv`，不得运行在线安装或同步。
若部署时仍使用上述平台，依赖清单或锁文件变化后在登录节点、项目根目录执行：

```bash
uv sync --frozen --python 3.11 --python-platform x86_64-manylinux_2_17 --link-mode copy
```

提交前和作业启动时使用只读离线检查，实际运行禁止隐式修改环境：

```bash
uv sync --check --offline --frozen --python 3.11 --python-platform x86_64-manylinux_2_17
uv pip check --python .venv/bin/python
uv run --offline --no-sync python scripts/neuroimaging/export_series_folders.py --help
```

若检查要求变更环境，返回登录节点准备，不让并行作业同时修改 `.venv`。
Python 包使用 `uv` 管理，不混用站点 NumPy、pandas 等模块；只有必要的基础运行时使用 module。
参考手册用 `module load gcc/11.3.0` 解决 `CXXABI_*`／`GLIBCXX_*` 问题，是否加载取决于
实际依赖。遇到 `GLIBC_*` 不兼容应选择兼容的 wheel，不在作业中替换系统 glibc。
本项目不继承参考项目的 SciPy、Pillow 或 scikit-learn 固定版本。影像作业启动时执行上述
只读环境检查和 `uv run --offline --no-sync`，不在 Slurm 作业内安装依赖。

## 验证和正式运行记录

首次部署先在计算节点以少量被试验证工具调用、被试命名、序列选择、BOLD 与事件时间轴、
场图关联及输出位置，再提交完整任务。验证使用 `temp/smoke_<module>/` 或明确指定的独立
临时输出，不覆盖正式结果；完成后仅清理本次测试拥有的产物。

正式运行在当天 `docs/sessions/` 日志或模块运行记录中保留：

- 代码 commit 与工作区是否有未提交修改；
- 环境、完整命令、入口路径设置、CPU／worker 数和 Slurm 作业编号；
- 输入位置、被试范围、输出位置，以及 Python、MATLAB、`dcm2niix` 等实际使用的软件版本；
- 完成状态、转换警告、失败被试和必要的科学 QC。

不计算、保存或比较文件内容 SHA-256，不将内容哈希作为就绪条件。
正式数据和结果仍留在各自环境；README 中的事件替换传输说明只在明确要求单次替换时使用。
