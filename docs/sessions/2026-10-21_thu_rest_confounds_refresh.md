# THU 静息态校正 confounds 与下游重算

## 用户授权与当前核验

用户明确授权：用 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/rest` 的 confounds
替换本项目 fMRIPrep STC 静息态对应文件，删除旧 XCP-D 结果及工作目录，再提交 XCP-D，
最终重新导出头动和 FC。保留 task、no-STC、BIDS、FreeSurfer 及 fMRIPrep 影像。

2026-10-21 19:49–19:53（北京时间）核对：当前 rest 清单为 731 人、2,459 个 run；
外部来源恰有 2,459 个 TSV 和 2,459 个 JSON。首个 run 的新旧列名和帧数相同，
差异仅为 FD 与 24 个头动参数／展开项；其他列相同。
当前没有活动 XCP-D／头动／FC 作业，模块锁均为空。
集群代码初始为 `da3bead`，两端工作区干净，Python 3.11.15，离线环境检查通过。

官方 25.2.7 更新日志确认 25.0.0–25.2.6 的 MCFLIRT 参数重建问题；本项目镜像为 25.2.5。
外部校正文件的生成版本不自行推断，来源按用户指定路径记录。

## 改动与计划执行

新增审计／替换／清理／试跑提交入口，详见[执行说明](../thu_rest_confounds_refresh.md)。
试跑后的既有提交脚本增加显式 `keep-scope` 模式，以保留现有 731 人范围及历史存档。
科学参数不变，XCP-D 仍为 26.0.2、1 CPU／1／1、36P、0.01–0.1 Hz，三个既定图谱。
群体 QC 阈值与合格被试集合在新头动计算后重新拟合。

下文按实际进展记录，不将已提交控制作业或完成输入替换写成下游重算完成。

## 本地验证

新增 4 项定向验证通过：接受一致的头动替换，拒绝非头动信号变化、错误 FD 和帧数错位。
既有 19 项影像测试（包括 Git Bash 模拟容器）全部通过，两份变更 sbatch 的 Bash 语法及
嵌入式 Python 语法检查通过。合成测试目录均已清理；真实文件的全批数值核验交由 Slurm 执行。

## 首次全批检查

代码 `4a6dc55` 已推送并由集群拉取；集群额外通过 4 项定向测试及首个真实 run 的数值审计。
首个 8 核准备任务 `15429474` 在启动前取消，改为 1 核任务 `15429477`，
以使用队列中的零散空闲资源。该任务于 19:59:08 在 fat20 启动。
首次检查在 `sub-THU202311180135_task-rest_run-1` 因异常帧列数不同而停止；
当时尚未备份、替换或删除任何原有文件。

核对发现源文件新增了 `motion_outlier05`，且全部 6 个异常帧列与校正 FD／DVARS 阈值逐帧一致。
源 JSON 明确写出 FD > 0.5 mm 或标准化 DVARS > 1.5。
据此增加对异常帧列增减的明确检查；其余非头动列仍不允许变化。
该检查不改变输入、不改变 XCP-D 的不做逐帧 censoring 设置或项目自己的头动 QC 阈值。

调整后新增 6 项测试在本地及集群均通过，真实异常帧增列 run 也通过。
任务 `15429483` 于 20:03:12 在 fat20 开始全批检查，前 100 个 run 通过。
为减少全批读取和数值核验的等待，后续审计改为与申请 CPU 数相同的进程池；
每个 worker 独立读取 run，不改变文件、顺序或统计检查。原 1 核审计在替换前停止后重提。
用户再次确认异常帧列不参与当前 XCP-D 的逐帧删除；本次仍完整保留这些源文件列，
不改变 36P 或 `--fd-thresh 0`。

## 正式全批检查

`15429483` 确认仍处于只读审计阶段后取消，未替换或删除原文件。
提交代码 `8d74eeb`，两端工作区干净。最终准备作业为 **15429496**，
q_fat_c／high_c、4 CPU／4 个审计进程和最多 4 个删除 worker，
20:06:46 在 fat15 启动。实际提交命令：

```bash
sbatch --parsable --cpus-per-task=4 --qos=high_c --job-name=efny_confounds_refresh \
  --output=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_refresh_%j.out \
  --error=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_refresh_%j.err \
  scripts/neuroimaging/refresh_thu_rest_confounds.sbatch \
  --source /ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/rest --apply
```

20:13:18 全部 731 人／2,459 个 run 的检查通过。所有 run 都有校正后的头动列变化，
非头动信号列均保持不变；89 个 run 的异常帧列数变化。
新旧逐 run 平均 FD 最大绝对差为 0.156651920269127 mm，不能直接沿用旧 QC 结论。
原 TSV／JSON 共 5,281,289,160 bytes，随后开始压缩备份。
本次记录根目录为 `outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_refresh_15429496/`。

## 替换和清理

原 confounds 与原 fMRIPrep 完成记录的压缩备份共 2,273,896,847 bytes，
文件名为 `original_confounds_and_records.tar.gz`。20:20:48 全部 4,918 个 TSV／JSON 替换完成，
随后为 731 人的原完成记录追加 `confounds_override`；原 fMRIPrep 执行时间、版本和影像保留。
旧 XCP-D、头动、FC 日志及头动／FC 来源表归档到本次记录根目录。

删除目标清单共 3,601 个模块目录下的直接子项：

- XCP-D `THU/rest/`：1,465 项（包括被试目录、HTML 及数据集级文件）；
- XCP-D `THU/work/`：731 项；
- XCP-D 临时目录 `THU/rest/`：731 项；
- 被试级 FC `THU/rest/`：674 项。

实际删除逐项写入 `removed.jsonl`，全部完成后验证四个根目录为空，才提交新 XCP-D。

## 本次交付时状态

截至 2026-10-21 20:27:54（北京时间），`15429496` 仍在 fat15 RUNNING（4 CPU）。
3,601 个删除目标中，1,481 项已在删除日志中确认完成；旧 XCP-D 正式衍生结果根目录已为空。
当前在删除 work 缓存，该阶段较慢；temp 和旧被试级 FC 的全部清理仍在后续。
stderr 仅有离线环境检查信息，无错误。

本时点尚未产生新的 XCP-D 试跑或全批作业编号，头动／FC 也尚未重算完成。
准备作业内已包含清理后的自动提交代码：先提交首名被试试跑，再提交依赖其成功的
`submit_xcpd_after_pilot.sbatch THU <pilot> keep-scope`；后者提交其余 730 人，
并衔接全批产物审计、头动、全数据集 QC、FC 和最终审计。
这些实际编号将写回本次 `refresh.json`、新的 XCP-D 日志及后续阶段来源记录，
无需用户手工重新提交。任一前置步骤失败则不继续推进。

验证总结：新增 6 项科学检查在本地和集群通过；既有 19 项影像测试通过；
真实全批输入检查通过。真实 XCP-D 试跑仍须在清理后执行，不提前宣称容器重跑已验证。
