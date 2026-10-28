# THU task fMRIPrep StartTime CSV 导出

## 请求与范围

用户要求导出所有现有 THU task fMRIPrep 结果的 `subid`、`task`、`starttime` 三列 CSV。
每个 run 一行；本次现有结果不存在 subject×task 多 run，所以三列可唯一识别每条记录。
保留完整 `sub-THU...` 标识，不聚合、不重算或统一四舍五入 StartTime。

本地项目为 `D:\projects\efny-pipeline`，导出时本地代码 `f8e4780`、`main`、已跟踪工作区干净。
集群项目为 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，读取时实际代码
`20b12498cf483a114015d18a5407452299685217`。本轮没有同步代码、提交 Slurm、传输影像或更改上游结果。

## 来源与生成

扫描时间为 2026-10-28 10:58:10，北京时间。只读扫描
`data/interim/neuroimaging/fmriprep/THU/task/sub-*/func/*_task-*_space-MNI152NLin2009cAsym_desc-preproc_bold.json`，
排除 rest，直接提取 StartTime；要求对应预处理 NIfTI 存在、STC 标志为 true、StartTime 有限。
逐文件解析 subject/task，保留原完整 scan 身份；扫描结果与上游 `input_scans.csv` 的 scan_id 集合完全相同。

通过 SSH 执行集群项目 `.venv/bin/python`（3.11.15）的标准库元数据提取，返回只读 JSON。
本地使用 bundled runtime 26.1015.12040 的 Node 和 `@oai/artifact-tool` 填入三列并逐格验证，
将验证后的原始单元格值序列化为 UTF-8 BOM／CRLF CSV。源表未新增路径、计数或说明列。
实际 Node 版本、导出时刻、源根目录、完整逐条 JSON 路径和输出路径保存在来源 JSON。

## 产物与核验

- CSV：`outputs/tables/neuroimaging/fmriprep/THU/task/thu_task_fmriprep_starttime_20261028.csv`。
- 来源记录：`outputs/logs/neuroimaging/fmriprep/THU/task/thu_task_fmriprep_starttime_20261028_source.json`。
- 569 名被试、1,522 行，列名严格为 `subid,task,starttime`；nback 521、sst 567、switch 434。
- 0.96 秒 282 行、0.959 秒 1,240 行；不把 0.959 改成 0.96。0.96 与 0.960 为相同数值。
- 已用独立 CSV reader 重新读取全部行，逐条核对 subject、task 和 StartTime 与提取来源完全一致；检查唯一身份、总行数和按任务计数。
- CSV 为 49,269 字节；没有计算文件内容哈希。已检查临时表格头部渲染，未额外交付 XLSX。

临时 JSON、构建文件、预览和依赖 junction 位于 `temp/task_starttime_export_20261028/`，
验证完成后清理，仅保留正式 CSV 和来源记录。按用户要求完成单次元数据导出，不建立两端数据同步。
