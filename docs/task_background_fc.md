# THU 任务态 background FC

## 实现状态与输入限制

2026-10-28 已实现 THU task XCP-D、协变量就绪审计、逐 run 头动描述、background FC 导出及完成审计。用户进一步授权对修正后的输入实际提交 XCP-D；运行状态和作业号见[提交记录](sessions/2026-10-28_task_background_submission.md)。提交不等于完成。

外部输入为 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/BrainProject/THU/custom_confounds_TASK`，生成器版本现为 `build_task_confounds.py` 1.4.0。只读取 `sub-*/func/*_desc-confounds_timeseries.tsv` 和 JSON，不将同目录 events TSV 混入回归。

2026-10-28 再次更新后的只读扫描，以既有 task fMRIPrep 清单为范围：

| 任务 | 上游 run | 匹配 confounds | 缺失 |
| --- | ---: | ---: | ---: |
| nback | 521 | 513 | 8 |
| sst | 567 | 562 | 5 |
| switch | 434 | 432 | 2 |
| 合计 | 1,522 | 1,507 | 15 |

上游 569 人中，568 人至少匹配一个任务；当前外部目录共 1,507 份 confounds，全部在现有上游清单之内。缺失的 15 个 run 保留在审计与运行 registry，不自动补齐。

旧 1.3.1 文件的零偏移问题记录在[实现日志](sessions/2026-10-28_task_background_fc_implementation.md)。1.4.0 抽查已将 `FrameTimeOffsetSeconds` 对齐各 run 的 0.96／0.959 秒，并记录 `FrameTimeOffsetSource=fMRIPrep StartTime` 及参考 JSON。全量 prepare 仍逐项核对原始 BOLD、CIFTI、TSV、TR、身份和采样参考。代码不改写外部文件，也不提供忽略时间偏移的开关。

## 模型与路径

使用 `configs/neuroimaging_stc.json` 的独立 `task_xcpd` 设置；`task_fmri` 和已有 fMRIPrep 完成记录的科学设置不变。

`configs/xcpd_36p_task_background.yml` 为 JSON 语法的合法 YAML，包含与 XCP-D 26.0.2 内置 36P 完全相同的 36 列，以及 custom dataset 中的 `^task_.*$` 列。已有任务列已经 SPM canonical HRF 卷积，不重复卷积，不添加 `signal__` 前缀。SST 可因没有某类事件而缺少相应条件列，也可因任务版本包含 cue；审计只接受明确列出的任务条件，保留实际列集合，不补零、不删除条件。

完整容器命令见 `scripts/neuroimaging/run_xcpd_task_background.sbatch`：

- 保留 rest 的 XCP-D 26.0.2、CIFTI、0.01–0.1 Hz／阶数 2、dummy 0、平滑 0、despike n、censoring 关闭、combine-runs n、min-coverage 0、motion low-pass 6 BPM、随机种子 42，以及三套 4S 图谱。
- 额外只读挂载 custom derivative dataset、回归 YAML 与逐被试过滤文件，通过一个 `--datasets` 参数列表合并 custom 与可选 atlas datasets。
- 每个作业为一个 subject×task，严格选择该任务的已有 run；允许单 run 缺少 run 实体。按任务隔离报告、工作缓存和锁，不并发写相同 subject×task 输出。
- 保持 q_fat_c、1 CPU、`--nprocs 1 --omp-nthreads 1` 与参考代理的 `SINGULARITYENV_*` 传递。

路径由 `src/imaging/config.py` 统一生成，详见 [ARCHITECTURE.md](../ARCHITECTURE.md)。例如：

```text
data/interim/neuroimaging/fmriprep/THU/task/                      # 既有只读上游
data/interim/neuroimaging/xcpd/THU/task_background/sst/          # 独立 XCP-D 结果
data/interim/neuroimaging/xcpd/THU/work_task_background/sst/     # subject 工作缓存
outputs/logs/neuroimaging/xcpd/THU/task_background/sst/          # 审计、过滤、完成记录
outputs/tables/neuroimaging/xcpd/THU/task_background/sst/        # 输入就绪宽表
data/processed/neuroimaging/background_fc/THU/task_background/sst/
```

三个任务的输入清单在各自 XCP-D 日志目录另存。不会为了下游子集而覆盖 fMRIPrep 的完整 `input_scans.csv`；检查上游完成记录时仍使用完整原被试清单。

## 准备与命令预览

所有命令从集群仓库根目录 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline` 执行。代码同步先检查工作区／分支，提交推送后在另一端使用 `git pull --ff-only`，不覆盖未提交修改。运行前按[集群说明](cluster_usage.md)准备并检查 `.venv`，不在作业内安装依赖。

全量审计涉及多个输入文件，提供单 CPU 的准备作业，避免在登录节点批量扫描。先创建 Slurm 日志父目录：

```bash
mkdir -p outputs/logs/neuroimaging/xcpd/THU/task_background
sbatch --chdir "$PWD" \
  --output outputs/logs/neuroimaging/xcpd/THU/task_background/prepare_%j.out \
  --error outputs/logs/neuroimaging/xcpd/THU/task_background/prepare_%j.err \
  scripts/neuroimaging/prepare_task_background.sbatch THU configs/neuroimaging_stc.json
```

准备作业分别运行三个任务的以下入口；少量指定被试也可直接做短时检查：

```bash
uv run --offline --no-sync efny-imaging prepare --dataset THU --scope task \
  --stage xcpd --task sst --subjects <reviewed_sst_subjects.txt>
```

每个 task 的日志保存 `input_scans.csv`、完整 `confounds_audit.json`、逐被试 `filters/*.json`、`subjects_ready.txt` 和 `subjects_blocked.txt`；表格 `input_readiness.csv` 每名被试一行，列出任务、run 总数／就绪数和阻塞原因。存在缺失或科学不一致的 run 时不会从输入清单消失；某被试只要一个选中 run 不就绪，就不会被标为整任务就绪。

对单人的实际容器命令做无执行预览：

```bash
uv run --offline --no-sync efny-imaging run --dataset THU --scope task \
  --stage xcpd --task sst --subject <subject> --dry-run
```

该命令仅展示参数，不表示输入已就绪。以下提交 dry-run 会真正验证上游完成记录、采样时间及 prepared 输入来源。

```bash
uv run --offline --no-sync efny-imaging submit --dataset THU --scope task \
  --stage xcpd --task sst --subjects <reviewed_sst_subjects.txt> --dry-run
```

## 输入对齐后的试跑与下游

全量 prepare 完成后，可用单 CPU 控制作业冻结范围并自动推进。该作业必须依赖 prepare 成功退出，registry 路径每轮唯一：

```bash
sbatch --dependency=afterok:<prepare_job_id> --kill-on-invalid-dep=yes \
  --job-name thu_background_pilot \
  --output outputs/logs/neuroimaging/xcpd/THU/task_background/pilot_all_%j.out \
  --error outputs/logs/neuroimaging/xcpd/THU/task_background/pilot_all_%j.err \
  scripts/neuroimaging/submit_task_background.sbatch pilot \
  outputs/logs/neuroimaging/xcpd/THU/task_background/run_<timestamp>.json
```

控制作业先核对三个任务的全部阻塞原因：仅缺失 confounds 的 run 可保留为明确未提交项；任何现有文件的科学不一致均停止本轮。试跑按实际采样偏移和 SST 是否有 cue 选取代表，冻结全部就绪被试及试跑名单。三个任务的试跑成功后，依赖作业再次检查真实联合设计、时间轴、ROI 和成功记录，通过才提交其余被试；每个任务分别安排 afterok 全批完成审计。任何试跑失败均不启动剩余批次，保留日志与逐次提交回执，不自动重试。已有提交或产物时禁止重复初始化。

registry 保存代码 commit、干净工作区、路径、冻结范围、缺失 run、试跑／批量作业和完整提交命令；输入快照、版本、完整容器命令与执行记录由原 pipeline 保存。最终完成审计独立写入各 task 目录，不并发改写共同 registry。本入口仅推进 XCP-D，不自动增加头动筛选、跨 run 汇总或独立 background_fc 导出。

批量放行还在同一 XCP-D 镜像内执行 `audit_task_pilot_residuals.py`：将实际 design.tsv 按已安装 Nilearn 的 `standardize_signal(detrend=True, standardize=False)` 和 `butterworth` 规则处理，沿用 0.01–0.1 Hz、order 2、constant padding、padlen=N−1，与镜像 `xcp_d/utils/utils.py` 的 `_denoise_with_nilearn` 一致。dummy 0、无 censoring 时，残差应与处理后的联合设计正交，parcel 平均保留此关系。逐 run／atlas 保存最大归一化内积和滤波后秩；归一化内积须小于 `1e-5`（允许 float32 保存误差）。原始 task 列与残差的普通相关不是该门槛。该检查不推导自相关校正后的有效自由度。

先更新／核清上游时间参考，重新 prepare，并审核逐项原因和被试范围。首次仅提交少量覆盖三个任务的样本；删除提交命令的 `--dry-run` 才会执行 sbatch。submit 默认检查所选任务清单中的全部被试，不自动改用就绪名单；使用明确审核后的 `--subjects` 控制范围。

每次启动重新核查 custom TSV、JSON、原始 BOLD、fMRIPrep confounds 和 CIFTI 的身份、帧数、TR、STC 偏移、dummy 与任务列。输入 provenance、文件大小／mtime 和完整元数据须与 prepare 时相同；不计算内容哈希。容器开始前保存输入、设置和上游完成时间，结束时再次比较，运行期间被修改的设计不能登记为成功。

完成审计要求 denoised CIFTI、所有图谱 ptseries、报告、成功记录以及每个 run 的 `*_design.tsv`。设计须包括 24 个滤波后 motion 项、12 个组织／全局信号项及实际 task 列；任务列数值应与输入相同，记录联合设计秩和名义剩余自由度。该设计 TSV 是带通前的联合设计，名义自由度不代表带通和自相关后的有效自由度；不以原始未滤波任务列与残差的相关为零作为错误验收条件。

task 残差的 CIFTI 时间单位须为秒、步长须直接匹配原始 BOLD 的 TR；再要求各图谱 ptseries 与其时间轴一致，避免输出之间同时带有同一个错误 TR 而误通过。

```bash
uv run --offline --no-sync efny-imaging check --dataset THU --scope task --stage xcpd --task sst
```

还需检查实际版本、stdout／stderr、HTML、调度退出码和真实残差回归效果；本地模拟容器测试不替代这些检查。试跑通过后再按审核的固定范围提交全批，并记录代码 commit、工作区、命令、路径、版本、作业号与耗时。

XCP-D 审计生成该任务的 `subjects_success.txt` 后，可分别提交头动描述和逐 run FC：

```bash
uv run --offline --no-sync efny-imaging submit --dataset THU --scope task --task sst \
  --stage head_motion \
  --subjects outputs/logs/neuroimaging/xcpd/THU/task_background/sst/subjects_success.txt --dry-run
uv run --offline --no-sync efny-imaging submit --dataset THU --scope task --task sst \
  --stage background_fc \
  --subjects outputs/logs/neuroimaging/xcpd/THU/task_background/sst/subjects_success.txt --dry-run
uv run --offline --no-sync efny-imaging check --dataset THU --scope task --task sst --stage background_fc
```

head_motion 仅描述原始 fMRIPrep FD、帧数及 FD>0.3 mm 比例，不拟合 task QC 阈值、不应用 rest 的至少两 run 门槛，不自动剔除任务。background_fc 不依赖未定义的任务筛选结论。

background_fc 每个残差 run 独立计算 Pearson r，Fisher z 使用与 rest 相同的 ±0.999999 裁剪及 z 对角线 0、r 对角线 1 约定，保留原 ROI 标签顺序。输入帧数／ROI／有限性检查后才输出；三个任务和多个 run 均不拼接。汇总表每个 run 一行，图谱并列为列，来源路径及 ROI 名单另存日志。`check --stage background_fc` 逐矩阵核对形状、行列标签与对应残差时序的 r／z 数值。

## 验证边界与依据

本地验证命令：

```powershell
$env:EFNY_TEST_BASH = 'C:\Program Files\Git\bin\bash.exe'
uv run --offline --no-sync --python .venv/Scripts/python.exe python -m unittest discover -s tests -p 'test_*.py' -q
```

测试覆盖原 rest 流程、task fMRIPrep 记录兼容、任务子集、无 run 名称、实际列集合、缺失／错位／非有限设计、输入变更、容器命令／联合设计登记、逐 run FC 与标签。合成文件位于 `temp/smoke_*` 并由测试清理。真实试跑与最终批次完成情况以集群记录为准。

- [XCP-D 26.0.2 任务回归](https://xcp-d.readthedocs.io/en/26.0.2/usage.html#task-regression)
- [XCP-D 26.0.2 内置 36P](https://github.com/PennLINC/xcp_d/blob/26.0.2/xcp_d/data/nuisance/36P.yml)
- [该版本实际合并和 motion 滤波逻辑](https://github.com/PennLINC/xcp_d/blob/26.0.2/xcp_d/interfaces/censoring.py)
- [该版本 design.tsv 输出逻辑](https://github.com/PennLINC/xcp_d/blob/26.0.2/xcp_d/workflows/bold/outputs.py)
