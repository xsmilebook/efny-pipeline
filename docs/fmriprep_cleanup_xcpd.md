# fMRIPrep 缓存清理与 XCP-D 提交

## 成功标准与当前批次

按用户要求，fMRIPrep 成功判断使用集群参考脚本：
`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/data_driven_EF/scripts/neuroimaging/check_fmriprep_success.sh`。
`scripts/neuroimaging/check_fmriprep_success.sbatch` 读取该文件，只替换项目、输入、输出、
名单路径和日志匹配规则，不更改 HTML、日志或逐 run 三类产物的判断逻辑。
参考脚本匹配 `<subject>.*`，本项目实际日志为 `<subject>_<job>.out/.err`，因此需要路径适配。
实际运行的脚本副本、参考成功／失败名单和 `reference_audit.json` 保存在 fMRIPrep 模块日志中。
另执行原有来源、参数和时间轴审计；两套名单不一致时明确失败。

2026-10-09 首次计算节点只读检查覆盖本批全部 745 人：731 人通过，共 2459 个 run，
14 人未通过且原始输入均缺少 T1w；两套完成记录及 Slurm 状态与参考判断一致。
BIDS 中有静息态 BOLD 的被试全部在本批名单中，没有遗漏。
这表示流程完成及必需文件齐备，不表示头动、配准或其他科学 QC 已通过。

## 清理范围

仅在用户明确授权丢弃缓存后运行 `scripts/neuroimaging/cleanup_fmriprep_cache.sbatch`。
本次用户明确要求所有被试均清理，包括缺少 T1w 且不再重跑的 14 人。
使用 q_fat_c、8 CPU，最多同时删除 8 个被试目录；不设置 Slurm 内存或时间参数。

删除范围由统一配置生成，仅为：

- `data/interim/neuroimaging/fmriprep/THU/work/<subject>/`
- `temp/neuroimaging/fmriprep/THU/rest/<subject>/`

运行前确认本批无活动作业、无执行锁，并检查删除目标在解析后的项目目录内，
不允许缓存根目录或被试目录为符号链接。保留空的缓存根目录。
保留正式 fMRIPrep derivatives、FreeSurfer 重建、原始 BIDS、日志、提交清单和完成记录。
计划、实际移除目录及结束信息写入 fMRIPrep 模块的 `cache_cleanup_<job>.json/.jsonl`。

## 顺序与失败条件

1. 清理全部被试的 fMRIPrep work/temp。
2. 清理完成后执行参考成功检查和本项目正式审计，生成成功／失败名单。
3. 选取成功被试执行现有 `run_xcpd.sbatch`，保持 q_fat_c、1 CPU、1／1 线程及原分析参数。
4. 试跑成功后，`submit_xcpd_after_pilot.sbatch` 再检查正式 XCP-D 产物、时间轴、图谱维度和信号，
   然后提交其余成功被试。试跑被试不重复提交，14 名 fMRIPrep 失败被试不提交 XCP-D。

Slurm 作业之间均采用 `afterok:<job_id>`，任何前置作业失败时，不执行后续步骤。
控制提交作业使用 `--kill-on-invalid-dep=yes`，避免上游失败后留下永久等待作业。
试跑是正式被试级处理，产物保存在正式 XCP-D 模块，成功后直接纳入全批结果。
试跑和控制链记录在 `outputs/logs/neuroimaging/xcpd/THU/rest/`；
逐人提交记录及汇总 `submission_batch_after_pilot.csv` 均保留作业编号和实际命令。

2026-10-10 用户授权继续执行头动、QC 和 FC。清理及 fMRIPrep 审计已成功完成。
初次 XCP-D 试跑因 Bash 4.2 的空数组兼容问题在容器启动前失败；
`run_xcpd.sbatch` 的可选数组现使用兼容展开，不改变科学设置。
重试及下游作业状态见[当日记录](sessions/2026-10-10_xcpd_retry_downstream.md)。

## 授权后的下游自动执行

`submit_xcpd_after_pilot.sbatch` 通过试跑审计后，先保存原始提交批次的输入清单、被试名单、
配置、完成审计和参考审计为 `*_original_batch.*`，不覆盖原始审计存档。
按参考成功名单重新准备 731 人、2459 个 run 的当前分析清单；逐项确认保留的 run 身份完全不变。
14 名缺少 T1w 且用户决定不再重跑的被试及理由记录在 `downstream_scope.json`。
单 run 被试仍参与头动汇总和既定数据集 IQR 阈值估计，是否进入 FC 由至少两个合格 run 规则决定。

试跑被试不重复提交；其余 730 人 XCP-D 成功后，`advance_rest_pipeline.sbatch THU xcpd`
重新执行全批产物、来源、时间轴和图谱检查，确认 731 人全部通过后提交头动任务。
头动全部成功后运行 `advance_rest_pipeline.sbatch THU head_motion`：验证完成记录，
执行数据集 QC，仅向符合既定 QC 的被试提交 FC。
FC 全部成功后运行 `advance_rest_pipeline.sbatch THU rest_fc`，检查每个图谱的 Pearson r／
Fisher z 矩阵维度、有限值、对称性、对角线、标签顺序、变换关系和合格 run 来源，保存完成审计。

每批提交持久化逐人记录和汇总，审计控制作业依赖该批所有作业的 `afterok`。
任一步失败则停止推进，不静默排除新失败的 XCP-D 被试，不提前计算 QC 或 FC。
该控制入口现在包括授权的完整下游链；只提交 XCP-D 时仍使用 `efny-imaging submit --stage xcpd`。
