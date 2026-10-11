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

## 集群部署与既有结果导出

代码提交 `2ff7d8d226ef5681bc93df74529180996adfdd49` 已通过 Git 推送，
集群干净工作区快进部署。使用登录环境，在项目根目录执行：

```bash
uv run --offline --no-sync efny-imaging export-motion-qc --dataset THU
```

该操作为短时表格整理，未提交影像处理或 FC 作业。实际更新：

- `outputs/tables/neuroimaging/head_motion/THU/rest/subject_qc.csv`：
  731 名被试、46 列；先列被试级结论，后列 run 1–10 的指标和 QC。
- 同目录 `run_qc.csv`：2459 行、13 列，删除汇总表中的路径和 func_dir。

逐项比较导出前后所有保留的 run 字段、被试级原有字段及每个宽表单元格，
均完全一致。阈值表和 QC 来源记录未改变；FC 完成记录的被试集合仍为 674 人，
被试排除数仍为 57。没有重算 FD、QC 阈值或 FC，没有同步数据到本地。

正式导出命令、解析配置、Python／NumPy／NiBabel 版本、commit、干净工作区状态、
输入范围、输出列名及验证结论已写入集群头动日志模块：
`outputs/logs/neuroimaging/head_motion/THU/rest/table_export_20261011.json`。

## 协作规则补充

按用户要求，在 `AGENTS.md` 第 6 节增加简洁的结果表可读性指导：
面向读者的汇总按判断对象组织，被试级质控优先宽表，程序用长表可单独保留；
主汇总保留理解结果所需字段，追溯信息放日志或来源记录；
展示调整不得改变科学口径，并区分未采集／缺失与 QC 不合格。
这不是要求所有数据统一改成宽表，也未增加代码、数据或结果改动。
本次仅检查文档差异，不重复运行科学计算或测试。

用户进一步明确，该原则适用于所有汇总表，不限于用户阅读或被试级 QC。
已将指导改为汇总表默认优先宽表，一行对应明确的汇总单位，
例如被试或被试 × session；相关指标、条件或 run 并列为列。
原始明细和程序所需长表仍可单独保留。本次仅更新协作规则及日志。
