# Plan

为 THU 的 STC task fMRI 增加 background FC 分支：沿用 rest 的 XCP-D 设置，将 36P 与任务效应联合回归，按 SST、n-back、switch 分开保存残差时序与 FC。先完成协变量覆盖、来源和采样时间核对，再实施代码、验证及集群试跑。详细依据见 [修改方案](docs/task_background_fc_plan.md)。

## Scope

- In: THU task 的协变量审计、XCP-D 自定义回归、显式 `task_background` 路径、逐 task/run FC、提交与完成审计。
- Out: 本轮仅编写计划；不修改工程代码、外部协变量、现有预处理数据或运行产物，不提交作业；不重跑 fMRIPrep，不改变 rest 分析，不合并不同任务。

## Action items

[ ] 以现有 task fMRIPrep 清单及完成记录为上游，逐 subject/task/run 建立独立 background 输入清单；列出匹配、缺失、额外协变量及来源异常，明确审核后的运行范围，不覆盖 fMRIPrep 清单。

[ ] 核对 custom TSV、JSON、BOLD、原始 fMRIPrep confounds 与 CIFTI 的身份、行数、TR、dummy 和 STC 时间参考；解决抽查所见 `FrameTimeOffsetSeconds=0` 与 BOLD `StartTime≈0.96 s` 的差异后再试跑，保留原协变量。

[ ] 在 `configs/neuroimaging_stc.json` 增加独立 `task_xcpd` 设置，记录只读 custom 根目录与 YAML 路径；新增 `configs/xcpd_36p_task_background.yml`，完整保留 26.0.2 内置 36P，增加匹配 `^task_.*$` 的任务 nuisance 项，不使用 `signal__` 前缀。

[ ] 在 `src/imaging/config.py` 中区分 task fMRIPrep 输入路径与 background 下游路径；按 `task_background/<task>/` 隔离 XCP-D、FC、日志、表格和临时目录，按 `work_task_background/<task>/<subject>/` 隔离缓存；同步登记 `ARCHITECTURE.md`，保持现有 rest/task fMRIPrep 路径及完成记录有效。

[ ] 新增 `scripts/neuroimaging/run_xcpd_task_background.sbatch`；在 sbatch 内显式保留 rest 的完整 XCP-D 命令，并添加只读挂载、`--datasets custom=...`、自定义 YAML、单任务选择及精确 run 过滤；在 `src/imaging/pipeline.py` 中补充 task XCP-D 路由、按 subject×task 提交与审计，避免现有 task 路由误指向 fMRIPrep。

[ ] 按 task/run 保存三套 4S 图谱的残差 ptseries、Pearson r 与 Fisher z；需要标准化矩阵导出时新增最小 `background_fc` 模块／入口，保留 ROI 标签顺序、对角线约定与来源记录；先输出逐 task/run 头动描述，不直接套用 rest 的至少两个合格 run 规则或自动生成跨任务总 FC。

[ ] 扩展有科学意义的合成验证：身份／行数／TR／采样偏移错误、缺失协变量、无 run 实体、任务列错误、非有限值、退化设计、路径及完成记录隔离、残差与 FC 计算；检查 dry-run 命令和实际选列，测试后立即清理 `temp/smoke_*`。

[ ] 更新 README、方法补充和当天 session，提交并推送代码后检查集群工作区并快进同步；在 `q_fat_c` 以 1 CPU 和 1/1 线程试跑少量覆盖三个任务的样本，审计实际联合设计矩阵、残差帧数／TR／ROI、回归效果、FC、stderr 与 Slurm 退出码，再按审核后的冻结清单提交批量并记录运行来源。

## Open questions

- 输入覆盖：2026-10-27 15:46 北京时间按文件身份匹配，现有 1,522 个 task run 中 1,234 个匹配协变量、288 个缺失；528 人至少匹配一个任务、41 人完全未匹配。需审核是先处理明确可用的 task/run，还是先补齐；这些数字不是完成全量科学审计后的可运行数量。
- 时间参考：现有协变量已作 SPM canonical HRF 卷积；需核查生成器与 fMRIPrep/CIFTI 元数据，确定是否需要以 STC 参考重新生成独立衍生协变量。不能仅凭行数一致判为对齐，也不能直接假定固定 1 秒偏移。
- QC／汇总：若后续需要筛选后的被试×任务 FC 或多 run 汇总，应先明确 task 的头动阈值、最低有效时长和汇总口径；本计划先保留逐 run 结果及描述指标。
