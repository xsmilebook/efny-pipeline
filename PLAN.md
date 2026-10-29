# Plan

为 THU 的 STC task fMRI 增加 background FC 分支：沿用 rest 的 XCP-D 设置，将 36P 与任务效应联合回归，按 SST、n-back、switch 分开保存残差时序与 FC。2026-10-28 用户授权检查更新文件并实现代码；入口和输入限制见 [使用说明](docs/task_background_fc.md)，原规划依据保留在 [修改方案](docs/task_background_fc_plan.md)。

## Scope

- In: THU task 的协变量审计、XCP-D 自定义回归、显式 `task_background` 路径、逐 task/run FC、提交与完成审计。
- Out: 不修改外部协变量或现有预处理产物，不重跑 fMRIPrep，不改变 rest 分析，不合并不同任务。2026-10-28 用户进一步授权对修正后的输入实际提交 XCP-D。

## Action items

[x] 以现有 task fMRIPrep 清单及完成记录为上游，实现独立 background 清单与逐 subject/task/run 审计；就绪／阻塞明确列出，不覆盖 fMRIPrep 清单。更新文件的交集为 1,507/1,522 个 run；实际运行范围仍待审核。

[x] 核对 custom TSV、JSON、BOLD、原始 fMRIPrep confounds 与 CIFTI 的身份、行数、TR、dummy 和 STC 时间参考；1.4.0 文件的 1,507 个现有 run 均通过完整 prepare（作业 15459635 COMPLETED、0:0），15 个缺失项保留。

[x] 在 `configs/neuroimaging_stc.json` 增加独立 `task_xcpd` 设置，记录只读 custom 根目录与 YAML 路径；新增 `configs/xcpd_36p_task_background.yml`，完整保留 26.0.2 内置 36P，增加匹配 `^task_.*$` 的任务 nuisance 项，不使用 `signal__` 前缀。

[x] 在 `src/imaging/config.py` 中区分 task fMRIPrep 输入路径与 background 下游路径；按 `task_background/<task>/` 隔离 XCP-D、FC、日志、表格和临时目录，按 `work_task_background/<task>/<subject>/` 隔离缓存；同步登记 `ARCHITECTURE.md`，保持现有 rest/task fMRIPrep 路径及完成记录有效。

[x] 新增 `scripts/neuroimaging/run_xcpd_task_background.sbatch`；在 sbatch 内显式保留 rest 的完整 XCP-D 命令，并添加只读挂载、`--datasets custom=...`、自定义 YAML、单任务选择及精确 run 过滤；在 `src/imaging/pipeline.py` 中补充 task XCP-D 路由、按 subject×task 提交与审计，避免现有 task 路由误指向 fMRIPrep。

[x] 实现按 task/run 保存三套 4S 图谱的残差 ptseries、Pearson r 与 Fisher z；新增 `background_fc` 入口，保留 ROI 标签顺序、对角线约定与来源记录；提供逐 task/run 头动描述，不直接套用 rest 的至少两个合格 run 规则或自动生成跨任务总 FC。

[x] 扩展科学定向合成验证与模拟容器命令验证；真实试跑的 24 个 run×atlas 组合通过滤波后联合设计投影门槛，最大归一化内积约 1.07e-6，低于 1e-5。滤波后秩已记录；名义自由度不等于自相关校正后的有效自由度。测试临时产物及清理受限项见 session。

[x] 更新 README、方法补充和 session，提交推送并在集群快进同步；在 `q_fat_c` 以 1 CPU 和 1/1 线程完成覆盖三个任务的真实试跑与残差验收后，按冻结清单提交批量。2026-10-29 唯一 nback 报告失败例复用缓存重提 15463759 成功，补充全批审计 15463760 成功；SST 562/562、nback 513/513、switch 432/432 全部通过。原失败记录和 15 个缺失输入保留，详细来源见当天恢复日志。独立 background_fc r／z 导出和头动描述尚未启动，不将 XCP-D 验收等同于这些独立阶段已完成。

## Open questions

- 输入覆盖：2026-10-28 再次更新后匹配 1,507/1,522 个 run、568/569 人，仍缺 15 个 run。已完成完整 prepare 和现有 1,507 个 run 的 XCP-D 验收；缺失 15 个 run 未提交。
- 时间参考：生成器已更新为 1.4.0，1,507 个 run 的 0.96／0.959 秒偏移均与对应 fMRIPrep StartTime 一致，完整审计通过后已进入真实试跑。代码不自动修正或忽略差异。
- QC／汇总：若后续需要筛选后的被试×任务 FC 或多 run 汇总，应先明确 task 的头动阈值、最低有效时长和汇总口径；本计划先保留逐 run 结果及描述指标。
