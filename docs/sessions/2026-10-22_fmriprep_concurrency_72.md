# fMRIPrep 并发上限调整为 72

用户要求将当前等待的 fMRIPrep 队列调整为最多同时运行 72 个作业。

2026-10-22 09:56–09:57（北京时间）核对：当前活动的 fMRIPrep 仅为 THU 任务态数组
`15428647`，并发上限为 48，48 个 RUNNING、444 个 PENDING。
两端代码为 `35ae7fc`，工作区干净；既有 no-STC 扩容控制作业不再等待。
每个被试仍为 6 CPU／`--nprocs 6 --omp-nthreads 6`、q_fat_c／high_c。

09:57:07 执行：

```bash
scontrol update JobId=15428647 ArrayTaskThrottle=72
```

Slurm 读回所有相关数组任务的 `ArrayTaskThrottle=72`，命令成功；
紧接更新时仍为 48 RUNNING、444 PENDING，实际启动数量取决于空闲资源和调度周期。
操作记录保存在集群任务态日志的 `array_throttle_72_20261022.json`，
包括时间、完整命令、更新前后状态、代码版本和不改变分析参数的说明。
未取消或重新提交数组，未改动固定被试索引、分析产物或缓存。

主配置 `configs/neuroimaging_stc.json` 的 `slurm.fmriprep_max_concurrent` 同步改为 72，
使后续主分析提交使用 `--array=0-N%72`；历史 no-STC 配置保留原值。
README、集群手册与静息态／任务态流程说明同步更新。
既有配置一致性测试允许此次明确授权的并发差异，仍逐项检查其余资源和科学参数。

验证：本地影像测试 18 项通过，1 项 Bash 模拟容器测试因本次未设置原生 Bash 环境变量跳过；
本次没有修改容器命令或脚本。配置和文档差异检查通过，合成测试目录已清理。

代码提交 `abd636b` 已推送并由集群 fast-forward 拉取，工作区干净。
集群 task 提交 dry-run 明确为 569 人、`--array 0-568%72`、每任务 6 CPU。
09:59:20 再次核对上限为 72，当前 51 RUNNING、441 PENDING，等待原因均为 Resources；
实际运行数已增加，不能把上限调整理解为立即有 72 个运行。
