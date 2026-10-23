# 停止并重提 4 个卡住的 THU rest XCP-D 作业

## 用户授权和复核

用户明确要求检查 4 个卡住的旧任务，停止后重新提交。
2026-10-23 23:07:50（北京时间）核对：

| 原作业 | 被试 | stdout 最后更新 |
| --- | --- | --- |
| 15432344 | sub-THU202503080579 | 10-22 15:48:00 |
| 15432374 | sub-THU202511220798 | 10-22 16:09:46 |
| 15432376 | sub-THU202511290802 | 10-22 16:23:19 |
| 15432378 | sub-THU202511290804 | 10-22 16:24:56 |

4 个任务均 RUNNING 约 31 小时，超过 30 小时未更新日志，停在 Nipype 缓存读取警告。
此前清缓存重提的 `15433623–15433633` 全部 COMPLETED／0:0，现有成功完成记录为 727 人。
原全批审计 `15433634` 仍在等待这 4 个旧任务。
两端起始代码为 `7009057`，工作区干净。

## 本次处理

先记录状态和用户授权，取消等待中的原审计 `15433634`，随后停止上述 4 个作业。
确认 Slurm 已完全结束这些任务后，才清理它们的 XCP-D 衍生结果、HTML、work、temp 和遗留空锁。
保留原 stdout／stderr，归档被试崩溃记录，保留已完成 727 人结果。
fMRIPrep、FreeSurfer、原始 BIDS 和其他活动任务不在取消或清理范围内。

沿用 `retry_xcpd_clean.sbatch`，增加显式第五参数 `CANCELLED`，
以接受此次用户授权停止的旧作业；默认 FAILED／1:0 检查不变，不自动猜测或取消活动任务。
先用真实清单执行 `dry-run CANCELLED`，再通过 Slurm 清理和补提。
新的全批审计改为依赖 4 个新编号，继续既定头动、全数据集 QC、FC 和最终矩阵审计。

XCP-D 科学参数及资源保持原值：26.0.2、q_fat_c、每任务 1 CPU／1／1、36P、0.01–0.1 Hz、
三个既定图谱和 `--fd-thresh 0`。清理控制任务申请 4 CPU，删除 worker 数与申请相同。

## 执行结果与启动验证

2026-10-23 23:09:27，4 个旧任务及旧审计 `15433634` 均已停止；
Slurm accounting 确认为 `CANCELLED by 5315`，4 个旧任务均已退出活动队列。
真实名单的 `dry-run CANCELLED` 通过，仅列出这 4 人的 12 个现存目录（每人 output、work、temp）。

执行代码为 `d0b4c39`，两端工作区干净。清理控制作业 `15435425` 在 fat20 上运行，
使用 q_fat_c／high_c、4 CPU／4 worker，23:10:42 开始、23:11:36 完成，状态 `COMPLETED 0:0`。
12 个目标均删除完成，保留原日志并归档被试崩溃记录，随后仅补提以下 4 人：

| 被试 | 旧作业 | 新作业 | 23:13–23:14 启动复核 |
| --- | --- | --- | --- |
| sub-THU202503080579 | 15432344 | 15435426 | RUNNING，1109 节点工作流建立成功，XCP-D started |
| sub-THU202511220798 | 15432374 | 15435427 | RUNNING，455 节点工作流建立成功，XCP-D started |
| sub-THU202511290802 | 15432376 | 15435428 | RUNNING，455 节点工作流建立成功，XCP-D started |
| sub-THU202511290804 | 15432378 | 15435429 | RUNNING，346 节点工作流建立成功，XCP-D started |

4 个新任务均在 23:11:36 于 fat20 启动。启动日志未发现错误；stderr 中禁用 FD scrubbing
导致 `--min-time` 无效的提示符合既定 `--fd-thresh 0` 参数。当前只是启动成功，不能视为重跑完成。

新审计 `15435430` 为 PENDING／Dependency，已核实仅以 `afterok` 等待上述 4 个新作业；
成功后复核全批 731 人，再接续头动、全数据集 QC、合格被试 FC 和最终矩阵审计。
已有 727 人完成结果保留，科学参数未改变。

集群项目根目录为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
输入为 `configs/neuroimaging_stc.json` 指向的 THU rest STC fMRIPrep 结果及已替换的正确 confounds，
输出仍为 `data/interim/neuroimaging/xcpd/THU/rest/`。
原取消状态、完整命令和冻结清单位于
`outputs/logs/neuroimaging/xcpd/THU/rest/stop_stalled_20261023.json`、
`cancelled_stalled_20261023.csv`；清理和重新提交的完整执行记录位于同日志根目录下
`clean_retry_15435425/retry.json`，包含配置、代码版本、工作区状态、12 个目标、4 个新作业及审计命令。
