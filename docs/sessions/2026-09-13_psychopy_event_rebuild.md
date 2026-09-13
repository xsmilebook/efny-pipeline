# PsychoPy 任务识别修正

## 背景

批处理日志显示，nback 和 switch 普遍未找到事件 CSV，而 SST 经常从 nback 或 switch
CSV 读取并因缺少 `bad` 列失败。根因是旧实现对一个文件名同时传入三个 `contains`
pattern；MATLAB 对标量文件名返回“是否命中任一 pattern”的单个逻辑值，随后该逻辑值
索引到任务数组的第一个元素 `sst`，使三个任务均被归为 SST。

## 修改

- PsychoPy 任务识别及 CSV 选择、字段解析、events 表生成全部作为局部函数整合进
  `dicom2bids_checked.m`。任务识别仅接受由下划线分隔的 `SST`、`nback` 和 `switch`
  token；无任务或同时出现多个不同任务 token 时返回空值。
- 多份同任务 CSV 仍按文件名时间选择最新记录；时间解析同时接受有毫秒和无毫秒的
  PsychoPy 文件名。
- 删除一次性 events 重建模式及删除既有 events 的代码。后续流程只执行完整
  DICOM-to-BIDS 转换，并在同一次转换中生成正确的 SST、nback 和 switch events。
- 最终运行时仅依赖 `dicom2bids_checked.m` 和 `run_dicom2bids_checked.m`，便于在不同
  转换环境中拷贝使用。

## 验证

MATLAB R2025a 验证覆盖标准 SST/nback/switch 文件名、混合文件列表、带额外
`SST_0702` token 的文件、无毫秒时间戳和多任务歧义文件名。

另外使用 `Z:\xuhaoshu\20260909_bp_DICOM` 中 160 和 188 的真实 PSYCH CSV，在系统
临时目录完成只写冒烟测试。两名被试均正确生成三个任务 events：SST 120 行、nback
120 行、switch 144 行；临时目录由测试自动清理，未修改现有 BIDS 数据。
