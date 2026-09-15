# BOLD DICOM 与 NIfTI 数量不一致的容错处理

`dicom2bids_checked.m` 原先要求每个已转换 BOLD 序列的源 DICOM 文件数与 NIfTI
第四维帧数严格相等；不一致时由 `assert` 中断整名被试的后续处理。

现将该检查改为 `DICOM2BIDS:BoldVolumeMismatch` warning。warning 保留源序列路径、
DICOM 文件数和 NIfTI 帧数，便于后续核查；该序列仍保持选中状态，并继续使用已成功生成
的 NIfTI 和 JSON 完成元数据处理及 BIDS 文件写出。转换命令本身失败时，仍沿用原有规则
跳过对应序列。

本次仅修改控制流和说明文档，不改变 DICOM 计数、NIfTI 帧数读取方式、序列选择规则或
输出目录。

使用 MATLAB R2025a `checkcode` 对修改后的转换脚本进行静态解析，未发现语法或代码
分析问题（`CHECKCODE_COUNT=0`）。完整 DICOM 转换依赖真实影像且运行时间较长，本次未
重跑；正式验证入口仍为 `run_dicom2bids_checked`。
