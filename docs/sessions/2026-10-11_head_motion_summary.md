# 2026-10-11：头动 QC 汇总表阅读形式

用户指出逐 run 长表不便判断每名被试的情况，要求汇总表去掉无助于理解结果的路径。
其原文前后出现“长表”歧义，已询问确认；根据逐人阅读与前文参考宽表的语境，
本次按每名被试一行的宽表实现。

## 改动范围

- `subject_qc.csv` 保留被试级 QC 与 run 数字段，增加按整数 run 编号排序的
  `restN_frame`、`restN_fd`、`restN_high_motion_ratio`、`restN_valid`。
- 未采集 run 留空，保留已采集但 QC 不合格的 `false`；不补零或填充数据。
- 汇总表不包含路径，`run_qc.csv` 去除 source_bold、confounds、func_dir，
  保留 FC 需要的身份、时间轴和 QC 指标。逐被试来源明细及运行记录保留。
- 新增 `efny-imaging export-motion-qc`，可将已完成的 run QC 重新整理为表格，
  不重新拟合阈值、不修改完成时间或 QC 来源记录、不重新生成 FC。
- 不调整原始 fMRIPrep FD、首帧分母、浮点精度、run 范围、阈值或至少 2 个
  合格 run 的规则。保留当前 run > 4；本次不执行参考范围或数值口径的额外对齐。

部署前集群 HEAD 为 `acf7a248d086023fa20be935cd3f6681aba4433b`、工作区干净，
本项目无活动作业。后续补充验证、部署和实际导出结果。

## 本地验证

15 项影像验证中 14 项通过，1 项 Windows Bash 模拟容器验证未启用。
新增验证覆盖非连续 run 编号、缺失 run 留空、失败 run 的明确标记，
以及重复 subject/run 被拒绝；原有直接拼接 FC 数值验证仍通过。
Git 差异检查通过，所有临时 smoke_neuroimaging 目录已自动清理。
本地沿用现有 Python 3.12 环境，通过 uv 的离线 no-sync 运行；
它与项目默认 Python 3.11 的提示不涉及本次依赖或环境改动。
