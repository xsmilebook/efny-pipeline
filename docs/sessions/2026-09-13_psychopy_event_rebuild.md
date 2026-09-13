# PsychoPy 任务识别与 events 重建

## 背景

批处理日志显示，nback 和 switch 普遍未找到事件 CSV，而 SST 经常从 nback 或 switch
CSV 读取并因缺少 `bad` 列失败。根因是旧实现对一个文件名同时传入三个 `contains`
pattern；MATLAB 对标量文件名返回“是否命中任一 pattern”的单个逻辑值，随后该逻辑值
索引到任务数组的第一个元素 `sst`，使三个任务均被归为 SST。

## 修改

- 新增 `classify_psychopy_task.m`，仅识别由下划线分隔的 `SST`、`nback` 和 `switch`
  token；无任务或同时出现多个不同任务 token 时返回空值。
- 将 PsychoPy CSV 选择、字段解析和 events 表生成提取到共享函数
  `write_bids_events.m`，供 DICOM 主转换器和 events 重建脚本共同调用。
- 多份同任务 CSV 仍按文件名时间选择最新记录；时间解析同时接受有毫秒和无毫秒的
  PsychoPy 文件名。
- 新增 `rerun_bids_events.m`。脚本先验证 BIDS 被试到 raw 被试目录的一一映射及
  `PSYCH` 目录，再删除本流程拥有的 SST、nback、switch task-level events TSV，最后
  仅对 BIDS 中实际存在的任务 BOLD 重建 events。影像和其他任务 events 不受影响。

## 验证

MATLAB R2025a 的函数测试覆盖标准 SST/nback/switch 文件名、混合文件列表、带额外
`SST_0702` token 的文件、无毫秒时间戳和多任务歧义文件名，共 3 项测试全部通过。

另外使用 `Z:\xuhaoshu\20260909_bp_DICOM` 中 160 和 188 的真实 PSYCH CSV，在系统
临时目录完成只写冒烟测试。两名被试均正确生成三个任务 events：SST 120 行、nback
120 行、switch 144 行；临时目录由测试自动清理，未修改现有 BIDS 数据。
