# 场图相位编码方向异常的容错处理

`dicom2bids_checked.m` 原先要求每对已转换 functional fieldmap 的
`PhaseEncodingDirection` 必须相反；方向不相反时由 `assert` 中断整名被试的后续处理。

现将方向不相反改为 `DICOM2BIDS:NonOpposingPhaseEncoding` warning。该 warning 不修改
场图序列的选中状态或 AP/PA 配对关系，后续继续使用已经生成的 NIfTI 和 JSON，并照常
写入 BIDS。缺少 `PhaseEncodingDirection`、AP/PA NIfTI 尺寸不同或两方向共有采集参数
不一致仍保留原有硬性校验，避免静默接受本次需求之外的科学数据异常。

使用 MATLAB R2025a `checkcode` 对修改后的转换脚本进行静态解析，未发现语法或代码
分析问题（`CHECKCODE_COUNT=0`）。完整 DICOM 转换依赖真实影像且运行时间较长，本次未
重跑；正式验证入口仍为 `run_dicom2bids_checked`。
