# THU n-back 单例报告失败恢复

## 授权、范围与诊断

用户要求修复上一轮唯一失败例，并允许考虑删除旧结果重提。恢复仅针对 `sub-THU202411100424` 的 nback，完成后补跑原冻结 513 个 nback 被试的完整审计。沿用 XCP-D 26.0.2、36P＋已有 HRF task nuisance、STC 时间参考、dummy 0、0.01–0.1 Hz、三套 4S 图谱、q_fat_c 1 CPU 和 1/1 线程，不更改分析设置。

2026-10-29 实时检查：原作业 `15460512` 已 FAILED、1:0；依赖审计 `15460819` 已 CANCELLED，无该被试活动作业或锁。集群 Git HEAD 为 `ead8cd3`，工作区干净。上一轮其余 1,506 个 XCP-D 作业均 COMPLETED、0:0；SST 562/562 和 switch 432/432 已通过全批审计。nback 有 512 个成功记录，原汇总仍仅含两个试跑，不能据此声称全批通过。15 个原缺失 custom confounds 的 run 不在恢复范围。

原日志先出现 `XCP-D finished successfully!`，随后在 `nireports/assembler/reportlet.py` 402–406 行读取 `logs/CITATION.tex` 的 `\\begin{document}...\\end{document}` 正则结果时抛出 IndexError。镜像内源码确认此处属于报告 boilerplate，而非 BOLD 回归。该 run 的 denoised CIFTI、三套 ptseries、三套 FC 和 design.tsv 已存在，但 HTML、成功 marker 和设计审计缺失。共享 CITATION.tex 当前有完整文档标记；结合原并发作业共用 task 输出目录，推断可能读取到并发写入中的文件，无法从事后完整文件证明当时具体写入者。

先采用原入口、原缓存、单作业重提，保留原日志与产物，不预先删除有效计算结果或修改容器。重新执行仍须正常退出并通过 finish-container 的原输入快照、联合设计、帧数、TR、ROI 和完整产物检查。成功后以 afterok 补跑原冻结 nback 范围的最终审计，不直接补写成功记录。

## 路径、环境和运行记录

- 项目根目录：`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
- BIDS：`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
- fMRIPrep：项目下 `data/interim/neuroimaging/fmriprep/THU/task/`。
- custom：`/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK`。
- 输出：`data/interim/neuroimaging/xcpd/THU/task_background/nback/`。
- 该被试缓存：`data/interim/neuroimaging/xcpd/THU/work_task_background/nback/sub-THU202411100424/`。
- 日志：`outputs/logs/neuroimaging/xcpd/THU/task_background/nback/`，原 registry 为上一层 `run_20261028T1650.json`，保持原始批次回执不变。
- uv 环境沿用项目 `.venv`；不安装依赖、不升级镜像。实际版本和完整容器命令由原 sbatch 与完成记录保存。

本次仅增加恢复说明，分析代码保持不变。提交前记录代码 commit、干净工作区、单例冻结名单和新作业回执；随后记录重提和审计作业号及实际状态。此时修复尚未完成。

12:39 已提交恢复作业 `15463759`，q_fat_c、1 CPU；代码 `9842ef1`、工作区干净，已推送并在集群快进同步。uv 离线只读环境检查通过。输入冻结名单为 nback 日志下 `retry_20261029_subjects.txt`，只有 `sub-THU202411100424`。使用现有 `efny-imaging submit --stage xcpd --scope task --task nback` 的同一提交函数，完整 sbatch 命令与回执在 `recovery_20261029.json` 和新增 `submitted_*.csv`。

原入口完整命令为 `scripts/neuroimaging/run_xcpd_task_background.sbatch THU sub-THU202411100424 configs/neuroimaging_stc.json /ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline nback`（提交时配置使用完整绝对路径）。原失败日志、数据及缓存均保留，无删除操作。复核 `ead8cd3` 到本次运行提交的 `src/imaging`、`configs` 和 `scripts/neuroimaging` 无差异。

已同时提交 nback 全批审计 `15463760`，依赖 `afterok:15463759` 且 `--kill-on-invalid-dep=yes`。使用原 `submit_task_background.sbatch audit <run_20261028T1650.json> nback`，范围为原冻结 513 人，排除原 8 个缺失 confounds 的 nback run；不重新拟定范围。审计日志位于 task_background 根目录的 `recovery_audit_nback_15463760.{out,err}`。
