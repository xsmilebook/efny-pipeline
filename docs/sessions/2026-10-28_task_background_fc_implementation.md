# THU task background FC：更新协变量核查与代码实现

## 授权与范围

用户说明外部 `custom_confounds_TASK` 已更新，要求检查并实现代码。本轮实现原 `PLAN.md` 的 task background 分支，修改配置、路径解析、提交／审计逻辑、sbatch、逐 run FC 与文档。保留 rest 科学设置、原 task fMRIPrep 清单／完成记录和全部数据；没有修改外部协变量或正式运行产物，没有提交真实 Slurm 作业，没有同步集群工作区。

本地根目录 `D:\projects\efny-pipeline`，起始 `main`、代码 `ffb929d`、工作区干净。集群只读检查通过 `CIBR-login`，Python 显式使用 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline/.venv/bin/python`；本次不调用系统 Python，不更新远程环境或依赖。

## 核查来源与结果

2026-10-28 09:20 起，北京时间。以集群现有 `outputs/logs/neuroimaging/fmriprep/THU/task/input_scans.csv` 为上游身份范围，读取原始 BOLD 路径及 task/run，不重新发现或扩大样本。

- 集群项目根目录：`/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`。
- 现有 BIDS：`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
- 只读外部协变量：`/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK`。
- 根 JSON 的生成器从此前 1.2.0 更新为 `build_task_confounds.py` 1.3.1；目录共 1,513 份 `*_desc-confounds_timeseries.tsv`，另有 events 和 summary，不混计。
- 上游仍为 569 人／1,522 run，全部省略 run 实体；匹配 568 人／1,507 run，其中 nback 513、sst 562、switch 432。外部有 6 份不在现有 manifest 中；不自动纳入。
- 缺少 15 个 run：nback 8、sst 5、switch 2；涉及 13 名被试，其中一人没有任何已匹配任务。
- 外部 summary 自报 1,513 ok、15 error：11 个无完整 CSV、2 个模型事件超出 BOLD 时长、2 个无匹配 PsychoPy CSV。本轮不修复或重新选择日志。
- 对全部 1,507 个匹配项读取 custom TSV／JSON 和 fMRIPrep BOLD JSON：SourceBOLD 与 manifest 相同；TSV 行数与 sidecar 的 NFrames 相同；sidecar TR 与 STC BOLD JSON 相同；无非有限值、无常量任务列。
- **全部 1,507 个设计仍声明 `FrameTimeOffsetSeconds=0`。** STC BOLD 的 StartTime 为 0.96 秒（279 个）或 0.959 秒（1,228 个）。本轮没有根据行数相同判定时间对齐，没有把 CIFTI 序列起点直接等同于 STC 物理参考，也没有自动平移／修改设计。

本轮全量核查没有重新执行全部原始影像／CIFTI 头、fMRIPrep 完成与 Slurm accounting 审计；新实现的准备入口将执行所选 run 的帧数／TR／采样参考核验。

### 缺失协变量清单

以下每名被试一行，只列已采集任务中未匹配 confounds 的任务，不据此推断其他任务是否采集。

| 被试 | 缺失协变量任务 |
| --- | --- |
| sub-THU202403240245 | nback |
| sub-THU202405260281 | switch |
| sub-THU202406290308 | sst |
| sub-THU202408080358 | nback、sst |
| sub-THU202507150649 | nback |
| sub-THU202508060696 | nback |
| sub-THU202508070700 | nback |
| sub-THU202508200731 | nback |
| sub-THU202602030850 | sst |
| sub-THU202603080915 | switch |
| sub-THU202607281004 | sst |
| sub-THU202607281006 | nback |
| sub-THU202610111034 | nback、sst |

SST 的实际条件列有八种集合：部分 run 无 go_error／stop_fail／go_correct 条件，较新协议另有 task_cue。实现允许每个 run 的已声明有效条件子集，不强行要求全体条件或填零；nback 和 switch 分别匹配各自实际条件列。

## 实现与科学边界

新增 `src/imaging/background.py`、36P＋任务项 YAML、task XCP-D／头动／FC 三个执行入口和一个全量准备 sbatch。统一 `--scope task --task <task>` 路由；完整容器命令仍保留在 sbatch。没有新增 Python 依赖；JSON 格式 YAML 由标准库读取并由 XCP-D 正常作为 YAML 解析。

输入审计保留全部所选 run 的就绪／阻塞原因；提交、启动与完成阶段检查输入来源和时间轴，不静默缩小范围。已完成的 task fMRIPrep 仍使用原完整被试清单验证，background 清单另存。task_xcpd 配置独立于 task_fmri，新增下游设置不会让已有 fMRIPrep marker 失效。

XCP-D 保留 rest 的 26.0.2、36P、0.01–0.1 Hz、dummy 0、无 censoring／平滑／despike、三套 4S 图谱、motion low-pass 6 BPM、seed 42、代理和 1/1 线程。仅增加现有 HRF 任务 nuisance 项；不重复卷积，不使用 signal__，不擅自升级工具版本。

独立 `task_background/<task>` 输出与 `work_task_background/<task>/<subject>` 缓存；输入过滤、锁、完成、来源和 FC 也按任务隔离。检查 XCP-D 实际 design.tsv 的 36P 选列（motion 项的 _filtered 名称）、task 项及其数值，登记联合设计秩和名义剩余自由度；其为带通前设计，不将该自由度当作最终有效自由度。

background_fc 每 run 独立计算 r／Fisher z，继承 rest 的裁剪与对角线约定并保留标签。头动仅描述原始 FD，不套用 rest 的至少两 run 门槛或总体阈值，不跨任务／run 拼接。矩阵完成审计核对标签和对应残差时序的实际 r／z。

方法与执行命令见 [task_background_fc.md](../task_background_fc.md)。目录登记在 ARCHITECTURE，README 与原 task 文档已同步；原 2026-10-27 计划文档保留并注明历史日期。

## 验证与未完成事项

2026-10-28 截至 09:35 再次完成本地验证：34 项 Python unittest 全部通过，最后一轮 12.386 秒，验证代码为 `ffb929d` 加本轮未提交修改。其中包含真实 Git Bash 调用、模拟容器完成登记、三个任务的协变量、错位／缺失／变化设计、逐 run FC 和原 rest 回归检查。四个新 sbatch 通过 `bash -n`，并确认 LF 换行。测试仅创建合成数据，所有 `temp/smoke_task_background_*` 已自动清理；没有真实容器去噪运行。

验证命令：

```powershell
$env:EFNY_TEST_BASH = 'C:\Program Files\Git\bin\bash.exe'
uv run --offline --no-sync --python .venv/Scripts/python.exe python -m unittest discover -s tests -p 'test_*.py' -q
```

输入采样参考尚未解决，当前不能据此声明 task background 处理就绪。真实计算节点试跑、实际残差去除效果、滤波后设计秩、全批提交与产物审计均未完成。没有将本地测试或 confounds 文件生成成功等同于正式分析完成。
