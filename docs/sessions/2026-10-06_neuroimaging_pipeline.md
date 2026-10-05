# 静息态 fMRIPrep、XCP-D、头动和 FC 入口

## 用户要求与确认

参考 `D:\projects\data_driven_EF\scripts\neuroimaging` 整理本项目影像流程。
用户指定 THU BIDS 输入为
`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`，集群项目根目录为
`/ibmgpfs/cuizaixu_lab/xuhaoshu/DATA_C/projects/efny-pipeline`。
保留 THU／XY 两个数据集，XY 输入暂未确定，不借用 THU 路径。

用户进一步确认仅静息态、最少 2 个合格 run，且所有 `ses-*` 已删除，只需支持
无 session、带 `run-*` 的输入。本次不迁移数据、不连接集群或提交正式计算。

## 实现和方法

- `configs/neuroimaging.json` 统一管理集群根目录、两队列输入、容器资源、核数、头动和图谱参数。
- `src/imaging/config.py` 管理模块／数据集／rest 路径；`pipeline.py` 管理输入清单、容器命令、
  Slurm 提交与完成审计；`rest.py` 执行原始 FD、数据集内 IQR QC、被试级 Pearson r 与 Fisher z。
- 提供 `efny-imaging` 命令和 fmriprep、xcpd、head_motion、rest_fc 四个 sbatch 入口。
  BIDS 只读挂载，默认分区 `q_fat_c,q_fat`，不设置 Slurm time／mem。
- fMRIPrep 25.2.5：rest、91k CIFTI、参考输出空间、启用 BIDS 验证；默认 6 核。
  XCP-D 26.0.2：36P、无平滑／despike、0.01–0.1 Hz 带通、6 BPM 运动低通、无逐帧 censoring；
  默认 1 核。各进程数值库线程限制为 1；不沿用参考脚本的计算节点代理。
- FD > 0.3 mm 帧比例 ≤ 25%，run mean FD ≤ 数据集内 Q3 + 1.5 IQR，被试至少 2 个合格 run。
  首帧未定义 FD 从均值分母排除，但沿用参考规则计入帧比例分母，明确记录有效 FD 数。
- 采用真实图谱名 4S156Parcels／4S256Parcels／4S456Parcels，不把含非皮层节点的矩阵命名
  为纯 Schaefer100／200／400。合格 run 按整数编号拼接，保留各 run 均值和振幅。
- 对时间轴、重复 run、图谱标签顺序、ROI 数、非有限信号和零方差 ROI 做科学检查，
  不自动填补 NaN 或无效相关。上游重跑／配置变化使下游完成记录失效，头动重跑后必须重拟合 QC。
- 衍生数据写入 `data/interim/neuroimaging/<module>/<dataset>/rest/`；最终 FC 写入
  `data/processed/neuroimaging/rest_fc/<dataset>/rest/`；表格和日志分别进入
  `outputs/tables/neuroimaging/`、`outputs/logs/neuroimaging/` 的模块子目录。

## 环境与文档

通过 `uv add` 新增 NumPy 2.2.6 与 NiBabel，创建 `pyproject.toml`／`uv.lock` 及默认 Python 3.11
版本约定。项目支持 Python 3.11／3.12；本次本地验证使用 Python 3.12.9、NumPy 2.2.6、
NiBabel 5.4.2，集群计划使用 Python 3.11 与 manylinux_2_17 wheel。
新增 `.gitattributes` 固定 shell／sbatch 为 LF。

同步更新 README、ARCHITECTURE 和集群手册，新增 `docs/neuroimaging_preprocessing.md`
提供方法、输入输出、逐阶段提交、失败审计与首次验证说明。容器参数已对照官方固定版本
使用文档与 XCP-D 参数源码；未复制参考项目的分析数据、结果或无关依赖。

## 验证

- 13 项合成 NIfTI／confounds／CIFTI 定向验证通过，覆盖配置隔离、run 顺序、session 拒绝、
  FD 计分、帧数错位、QC 纳入、各数据集独立阈值、原始幅度拼接 FC、Fisher z、CIFTI 方向、
  NaN／常数 ROI 报错、标签／时间窗错位、命令预览、完成记录和 QC 过期检测。
- 四个 sbatch 入口通过 `bash -n`，Python 通过编译检查，本地离线环境检查和 `uv pip check` 通过。
- 检查配置语法、文档相对链接与 Git 差异；所有 `temp/smoke_neuroimaging_*` 已清理。

容器执行在测试中模拟，未执行真实 fMRIPrep／XCP-D，也未产生正式数据或结果。
首次集群运行仍需确认配置中的镜像、FreeSurfer license、TemplateFlow／4S 图谱资源，
在相同计算环境提交少量真实被试并检查 HTML、日志和产物，然后再批量运行。
