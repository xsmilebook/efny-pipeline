# THU 任务态 background FC 规划

## 请求与边界

用户要求规划：在 rest 的 XCP-D 基础上增加任务效应回归，协变量根目录为 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK`，用于 background FC，生成目录显式包含该含义。

本轮只读核对本地代码、配置、方法与集群规则，并通过 SSH 查询外部协变量及上游清单／既有审计。仅新增计划与补充文档、更新 README 链接；没有修改工程代码、运行配置、外部输入或运行产物，没有提交 Slurm 作业或重跑分析。

## 来源与核查结果

- 本地仓库：`D:\projects\efny-pipeline`，起始代码 `0872053`，`main`，工作区干净。
- 集群仓库：`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`；工作区查询未显示文件修改，当前 tracking 状态为 `main...origin/main [ahead 20]`，本轮未 fetch/pull/push，未据此声称两端最新远程同步。
- 只读扫描时间：2026-10-27 15:46:29，北京时间。使用集群项目 `.venv/bin/python`；系统 `python` 缺少 pathlib，未用其开展数据检查。系统 Git 不支持 `-C`，后续改用 subprocess 的 cwd 参数只读查询状态。
- 上游 task manifest：569 人、1,522 个 run；569 份完成记录；既有 `retry_audit_15438020.out` 报告全部通过，stderr 为空。本轮未重新执行全量影像产品与调度审计。
- 外部 confounds：530 人、1,239 份匹配 `*_desc-confounds_timeseries.tsv` 的文件；另有 events TSV，不能混计。
- 与项目 scan 身份交集：528 人、1,234 个 run（nback 500、sst 316、switch 418）；缺失 288 个（21、251、16），41 人完全未匹配，另有 5 份协变量不在项目 manifest。
- 外部 processing summary：1,239 ok、289 error，统计范围不同于项目 manifest；未把全部 error 直接等同于项目缺失。
- 抽查三个任务的 JSON：已作 SPM canonical HRF 卷积、无导数／drift、dummy 未删除，frame offset 为 0；相应 STC BOLD `StartTime` 为 0.96／0.959 秒。需核查生成器与实际时轴，尚未判定全量协变量就绪。

## 形成的计划

以 36P＋任务 nuisance 联合回归为主，保留 rest 的其他 XCP-D 参数。按 task 隔离 `task_background` 输出、缓存、日志和完成记录；保留原 task fMRIPrep 与 rest 路径。上游完成审计仍使用原完整清单，下游另存选中子集，避免错误失效或覆盖上游身份。

实施前解决覆盖、CSV/BOLD 来源和 STC 时间参考；必要时另建衍生设计而保留外部原件。保留逐 task/run FC，头动先提供描述，不直接迁移 rest 的两 run 门槛或自动跨任务合并。

交付为根目录 `PLAN.md`、`docs/task_background_fc_plan.md` 和 README 入口。方法来源核对 XCP-D 26.0.2 官方 usage/workflows 与内置 36P YAML；关键问题及验证顺序详见补充方案。

## 验证

本轮为文档修改，检查差异、链接、本地文件状态及 `git diff --check`；不运行影像处理测试。文档中的新增入口／路径为拟议方案，不能作为现已实现的功能或完成结果。
