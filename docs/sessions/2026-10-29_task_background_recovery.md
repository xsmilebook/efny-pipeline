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

## 单例恢复结果

12:51 重提 `15463759` 已 COMPLETED、0:0，用时 11:44。容器 workflow 成功并正常生成 HTML（95,212 字节），随后 finish-container 成功完成；未删除任何旧结果或工作缓存。当前 stderr 仅有 uv 只读检查和禁用 scrubbing 时的预期 min-time 提示，没有原来的 IndexError。

完成 marker 记录 XCP-D v26.0.2、代码 `05dfd68`、工作区干净、作业 15463759。期间仅同步恢复说明，分析代码和参数仍与原批一致。该 run 的联合设计为 36P＋3 个 task 项，219 帧，加入截距和线性趋势后的设计秩为 38、名义剩余自由度 181；该数值不代表校正自相关后的有效自由度。task 偏移 0.959 秒通过输入快照检查，残差帧数、TR、三套图谱 ROI／有限值及实际 task 列值检查均通过。运行时 `recovery_20261029.json` 已补充这次正常完成的来源、报告大小与设计审计。

单例故障已经修复，全批审计 15463760 尚待正常结束后才能将 nback 标为全批验收通过。原 15460512 失败和 15460819 取消记录保留，不将历史失败改写为成功。

## 全批审计与最终对账

13:09:24，恢复后的 nback 全批审计 `15463760` 已 COMPLETED、0:0，用时 17:36；stdout 明确记录 `xcpd: 513/513 complete` 和 `nback: all 513 frozen subjects passed the final XCP-D audit`。stderr 仅有 uv 环境只读检查，无异常。该检查按原冻结范围逐 run 复核完整产物、输入快照和上游完成记录、实际联合设计、残差帧数／TR／三套图谱 ROI 与有限性。

随后直接将三个任务的 completion_audit.csv、subjects_success.txt、subjects_failed.txt 和成功 marker 与原 registry 冻结名单对账：

| 任务 | 冻结 run／被试×任务 | 审计通过 | 失败 | 原缺失协变量未提交 |
| --- | ---: | ---: | ---: | ---: |
| sst | 562 | 562 | 0 | 5 |
| nback | 513 | 513 | 0 | 8 |
| switch | 432 | 432 | 0 | 2 |
| 合计 | 1,507 | 1,507 | 0 | 15 |

三个任务的审计名单、成功名单和 marker 均与冻结范围完全一致，失败名单为空，无残留锁。恢复作业及审计已不在队列中。原分析提交到当前 `src/imaging`、`configs` 和 `scripts/neuroimaging` 无差异，工作区干净。本次没有删除旧结果、修改协变量、变更工具或放宽验收条件；单作业复用缓存后成功恢复，符合共享 boilerplate 并发写入冲突的推断，但不能据此确定原冲突写入者。

运行时 `nback/recovery_20261029.json` 已补充审计成功状态、检查时间和三个任务最终计数。XCP-D 残差、三图谱时序和其逐 run Pearson FC 已完成验收；独立 background_fc 的 r／Fisher z 导出及头动描述阶段没有在本次恢复中启动。15 个缺少协变量的 run 仍未提交，不将其计入 1,507 个已完成 run。
