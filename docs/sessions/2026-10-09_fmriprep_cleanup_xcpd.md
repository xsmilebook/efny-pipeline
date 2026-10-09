# 2026-10-09：fMRIPrep 完成判定、缓存清理与 XCP-D

## 用户指令

先按 `data_driven_EF/scripts/neuroimaging/check_fmriprep_success.sh` 判断有数据被试是否全部成功。
随后删除所有被试的 fMRIPrep work/temp；14 名缺少 T1w 的失败被试不保留断点重跑缓存。
依次执行正式审计、少量 XCP-D 试跑、成功后批量提交。
不改变 fMRIPrep／XCP-D 科学参数，仍使用既定项目根目录、THU BIDS 和 q_fat_c。

## 已完成只读检查

- 集群项目：`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
- BIDS：`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
- 原提交清单：`outputs/logs/neuroimaging/fmriprep/THU/rest/submission_batch_20261006_newroot.csv`。
- 检查时项目版本：`e4c0745`，本地与集群工作区均干净。
- q_fat_c 计算节点 fat19，检查作业 `15233412`，1 CPU。
- 读取用户指定参考脚本，仅在内存中适配路径、输出到计算节点临时目录和下划线日志匹配；
  用 Bash 执行完整判断逻辑。临时成功／失败名单在检查结束后移除。
- 745 人中 731 人通过，共 2459 个 run；14 人失败，均有静息态 BOLD 但 T1w 数为 0。
- 731 人均有 T1w；参考成功名单与 731 份完成记录完全一致。
- Slurm accounting：731 COMPLETED、14 FAILED；与参考判断逐人一致。
- BIDS 中有静息态 BOLD 的 745 人全部已提交，没有漏提交或名单内无 BOLD 者。

## 执行准备

增加三份科研执行脚本：参考标准加时间轴审计、8 核受限范围缓存清理、试跑成功后提交其余 XCP-D。
完整 fMRIPrep／XCP-D 命令继续位于原 sbatch，不修改科学设置或统一配置。
参考检查副本、名单、清理记录、试跑及全批提交记录均进入对应模块日志，数据和结果不传回本地。
具体检查标准和执行条件见[说明](../fmriprep_cleanup_xcpd.md)。

## 作业链已提交

执行脚本版本为 `bc1800c`，本地提交并推送后集群干净工作区通过 Git 快进更新。
三份 Bash 及内嵌 Python 语法检查通过；集群 `uv sync --check --offline --frozen` 确认环境无需修改。
提交时显式把 `$HOME/.local/bin` 加入 PATH，计算节点读取既有 `.venv`。
提交前检查确认两个缓存根目录各有 745 个被试目录，均在配置项目根目录内且不是符号链接；
无本项目活动 fMRIPrep／XCP-D 作业或执行锁，试跑被试完成记录和 FreeSurfer 目录存在。

| 阶段 | 作业编号 | CPU | 启动条件 |
| --- | --- | ---: | --- |
| 所有被试缓存清理 | 15233422 | 8 | 直接排队 |
| 参考标准及正式时间轴审计 | 15233423 | 1 | afterok:15233422 |
| XCP-D 试跑 | 15233424 | 1 | afterok:15233423 |
| 试跑再审计并提交剩余 XCP-D | 15233425 | 1 | afterok:15233424 |

全部使用 q_fat_c。试跑为 `sub-THU202311180133`（3 个静息态 run）；
保持现有 XCP-D 26.0.2、1／1、36P、0.01–0.1 Hz、无逐帧 censoring 和三个图谱设置。
试跑通过后控制作业计划提交其余 730 人，不重复提交试跑被试，14 名缺少 T1w 者不提交。
从属作业启用 `--kill-on-invalid-dep=yes`，上游失败则不能启动或继续提交下游。
实际完整命令与依赖保存在集群
`outputs/logs/neuroimaging/xcpd/THU/rest/workflow_submission_20261009.json`。

刚提交时清理为 PENDING，其余三项为依赖等待；这不表示清理、试跑或全批处理已完成。
随后确认清理作业在 fat19 RUNNING，输出为 `Deleting 1490 subject cache directories with 8 workers`，
stderr 暂为空；其余三项仍依赖等待。清理尚未结束，正式审计和 XCP-D 尚未开始。
