# THU rest XCP-D 节点故障后的锁清理与补提

## 授权和核验

用户明确要求清除 35 个失败 XCP-D 作业的遗留锁并重新提交。
15:08（北京时间）核对：两端为 `3efa867`，工作区干净；主分析输入仍为 731 人。
当前 XCP-D 有 696 个成功完成记录，35 人缺少完成记录，并各有一个空锁目录；
没有活动 XCP-D 作业。Slurm 最后状态均为 FAILED／1:0。

这些作业此前在 2026-10-22 06:08:33 遭遇 NODE_FAIL：fat18 为 19 个，fat17 为 16 个。
自动重排后因锁已存在而在启动前失败。原全批审计 `15430493` 因无效 afterok 依赖取消，
头动和 FC 尚未启动。这里只补提失败者，不重新提交已经完成的 696 人。

## 实际操作

15:09:49 起，从集群项目根目录通过既有 `imaging.pipeline.submit` 执行：

1. 再次确认旧作业已失败、当前无 XCP-D 活动作业，锁与 35 人名单完全对应。
2. 核对锁为本模块目录中的非符号链接空目录，逐一使用 `Path.rmdir()` 删除。
3. 保存明确被试名单，通过现有 `run_xcpd.sbatch` 提交 35 人，保留其工作缓存以恢复计算。
4. 新提交 `advance_rest_pipeline.sbatch THU xcpd`，afterok 依赖全部 35 个新作业。
   全批 731 人产物审计通过后，继续既有头动、全数据集 QC、FC 和最终矩阵审计。

计算环境为集群仓库根目录 `.venv`／离线 uv，工作根目录为
`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
输入为该根目录下 `data/interim/neuroimaging/fmriprep/THU/rest/` 的 STC 影像及已替换的校正 confounds；
输出仍为 `data/interim/neuroimaging/xcpd/THU/rest/`。
XCP-D 26.0.2、q_fat_c、每任务 1 CPU、1／1 线程、36P、0.01–0.1 Hz 及三个图谱等参数均不变。
`--fd-thresh 0` 保持不按 FD 删除影像帧；未删除科学产物、缓存或原失败日志。

新作业为 `15432344`–`15432368` 和 `15432373`–`15432382`，合计 35 个。
新的全批审计及下游控制作业为 **15432383**。
审计提交命令使用 `--dependency afterok:<全部 35 个新编号>`、`--kill-on-invalid-dep=yes`，
分区 q_fat_c、1 CPU，入口为 `scripts/neuroimaging/advance_rest_pipeline.sbatch THU xcpd`。

模块日志 `outputs/logs/neuroimaging/xcpd/THU/rest/` 保存：

- `retry_nodefail_20261022T070949.json`：旧失败记录、清除的锁、代码及配置、全部新作业命令、审计编号；
- `subjects_retry_nodefail_20261022T070949.txt`：35 人名单；
- `submission_retry_nodefail_20261022T070949.csv`：被试与新作业的映射和完整 sbatch 命令；
- 新的逐作业 `submitted_*.csv`、被试 stdout／stderr，以及 `audit_retry_15432383.out/.err`。

## 提交后验证

15:10:46 核对：13 个 RUNNING、22 个 PENDING，35 个作业均已被 Slurm 接收，没有新增失败状态；
控制作业 `15432383` 为 PENDING／Dependency。抽查前两个新作业已进入实际 XCP-D 容器命令，
没有锁冲突。stderr 的 `Framewise displacement-based scrubbing is disabled` 符合既定设置。
本次没有修改分析代码或容器参数，不新增计算方法测试；仍以全批产物审计确定最终完成。
