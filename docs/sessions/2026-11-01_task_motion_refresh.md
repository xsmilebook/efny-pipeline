# THU task 头动 confounds 重算与 XCP-D 重跑

用户明确授权使用 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/ADHDnetwork/batchcode/brainproject` 的 `batch_run_recomputemotion.sh` 和 `recompute_motion_25_2_7.sh` 重算 task 头动、覆盖旧 confounds，删除旧 task XCP-D 并重新生成结果。范围仅为 STC THU task，rest、no-STC、BIDS、FreeSurfer 和 fMRIPrep 影像不变；已有 task 效应 regressors 不重建。

检查发现外部脚本输入与选择器均写死 rest，计算脚本指定 q_cn。仓库保存同名 task 适配版，外部原文件只读保留。算法沿用指定脚本：25.2.7 FSLMotionParams 从 HMC 变换及 boldref 重建六参数，ExpandModel 生成 24 项，半径 50 mm 的 Power FD，按 FD>0.5 mm 或标准化 DVARS>1.5 重建 motion_outlier，保留其他 confounds 和 JSON 元数据。适配仅改变显式 task 输入路径、任务选择与项目要求的 singularity/3.7.0、q_fat_c；每个重算作业保留原脚本 3 CPU，数值线程 1，不重新启动完整 fMRIPrep。

当前集群项目根目录 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，输入为 `data/interim/neuroimaging/fmriprep/THU/task/`，清单 569 人／1,522 run。已抽查 HMC boldref 和 orig→boldref xfm 存在。起始 Git 5bbccd7，两端工作区干净；账号队列仅有无关交互 bash，没有活动影像作业。旧结果在 2026-10-29 曾通过原检查，但未包含上游 25.2.5 头动参数修复，不能作为本次校正后的最终结果。

先在独立 staging 路径重算一人的三个任务，确认数值和非头动项后提交全量。完整新文件必须全部通过时间轴、非头动列、24 项和 FD 一致性检查，才备份并原子替换 task fMRIPrep confounds。之后归档旧日志、检查终态／锁／路径和符号链接，清理仅属 task_background 的旧 XCP-D 结果、work/temp 及受其影响的下游产物，重新 prepare。沿用三个 task 的真实试跑→残差门槛→全批→审计链，不改变回归、滤波、censoring、atlas 或任务采样偏移。

代码和实际运行作业号、范围、版本及成功／失败状态继续补充；本轮尚未重算或清理正式产物。
