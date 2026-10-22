# THU 静息态 confounds 替换与下游重算

## 原因与范围

fMRIPrep 25.2.7 的[更新日志](https://fmriprep.org/en/25.2.7/changes.html)指出，
25.0.0–25.2.6 从变换矩阵重建的六个头动参数未忠实还原 MCFLIRT 输出。
本项目使用 25.2.5，2026-10-21 用户指定用下列目录的校正文件替换 STC 静息态 confounds：

```text
/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/rest
```

保留当前审核后的 731 人、2,459 个 run；不重新运行 fMRIPrep，不改变影像、STC、
XCP-D 参数、图谱或头动 QC 规则。task、no-STC、原始 BIDS 和 FreeSurfer 不在替换或清理范围内。
修复来源是用户指定的文件；本流程验证其对应关系和数值一致性，不自行推断其生成软件版本。

## 执行顺序

入口为 `scripts/neuroimaging/refresh_thu_rest_confounds.sbatch`，使用 q_fat_c、8 CPU，
每个进程的数值线程为 1，审计和删除的 worker 数均等于实际申请的 CPU 数；
可在 sbatch 命令中用 `--cpus-per-task` 明确覆盖默认值。

1. 全批核验源文件集合与既有清单完全一致，TSV、JSON 均逐 run 对应。
   检查原始 BOLD、现有 CIFTI 和替换 TSV 的帧数一致；非异常帧列的顺序及非头动列的数值保持不变。
   校验六个头动参数、差分、平方项和 50 mm 半径的 Power FD，及 mm／rad 单位。
   允许校正 FD 后 `motion_outlier*` 列增减或变化，但必须为不重复的单帧指示列，
   并准确对应源 JSON 所声明的 FD > 0.5 mm 或标准化 DVARS > 1.5 规则。
2. 完整审计通过后，压缩备份原 TSV、JSON 与 fMRIPrep 完成记录。
   将源文件复制到目标目录的临时文件，再逐文件原子替换；不改写外部源文件。
   fMRIPrep 原执行时间和版本保持不变，在完成记录中追加 `confounds_override` 来源。
3. 将旧 XCP-D、头动、FC 日志以及旧头动和 FC 来源表移入本次修复日志目录。
   删除 STC THU rest 的旧 XCP-D 衍生结果、`THU/work/`、容器临时目录，及旧被试级 FC 矩阵。
   先保存删除目标，验证解析后的目标属于项目自有模块，再删除；没有活动下游作业或锁才执行。
4. 提交首名被试作为真实 XCP-D 试跑，成功并通过产物审计后，
   `submit_xcpd_after_pilot.sbatch THU <pilot> keep-scope` 提交其余 730 人。
   `keep-scope` 明确保留既定清单，不重新准备或覆盖历史原始批次存档。
5. 沿用 `advance_rest_pipeline.sbatch` 的 afterok 链：全批 XCP-D 审计 → 逐人头动 →
   全数据集重新拟合 IQR 阈值、导出宽表 → 合格被试 FC → 矩阵与来源审计。
   任一前置步骤失败则停止推进，不静默剔除被试。

审计与备份保存在 fMRIPrep 日志目录的 `confounds_refresh_<job_id>/`，
包括 `refresh.json`、`confounds_audit.csv`、`original_confounds_and_records.tar.gz`、
旧日志和 `removed.jsonl`。新结果仍写入原有 STC 模块路径。
QC 合格人数和阈值必须重新计算，不能沿用此前的 674 人。

## 命令

从配置定义的集群项目根目录运行；先创建 Slurm 日志父目录。
不带 `--apply` 只审计，带 `--apply` 才会执行替换、删除与重提。

```bash
mkdir -p outputs/logs/neuroimaging/fmriprep/THU/rest
sbatch --output=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_audit_%j.out \
  --error=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_audit_%j.err \
  scripts/neuroimaging/refresh_thu_rest_confounds.sbatch \
  --source /ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/rest

sbatch --output=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_refresh_%j.out \
  --error=outputs/logs/neuroimaging/fmriprep/THU/rest/confounds_refresh_%j.err \
  scripts/neuroimaging/refresh_thu_rest_confounds.sbatch \
  --source /ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/rest --apply
```

头动宽表仍为 `outputs/tables/neuroimaging/head_motion/THU/rest/subject_qc.csv`；
FC 仍为 `data/processed/neuroimaging/rest_fc/THU/rest/` 下三个图谱的 Pearson r／Fisher z。
本次是否已替换、删除或完成重算，以当日会话记录和 Slurm／产物审计为准。

2026-10-22 的检查发现，重算中 35 人遭遇节点故障，自动重排后被遗留锁阻止启动。
用户授权清理这些空锁并补提失败者，保留 696 人的成功结果和失败任务的工作缓存；
新建全批审计依赖全部重试作业，继续原头动和 FC 链。
实际作业编号及验证见[锁清理和补提记录](sessions/2026-10-22_xcpd_node_failure_retry.md)。
