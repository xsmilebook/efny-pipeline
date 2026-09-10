# dcm2niix Windows 长路径规避

## 问题判断

MATLAB 在序列目录中能够找到 `.IMA` 文件并读取首个 DICOM header，但 Windows 版
`dcm2niix` 随后报告目录中没有 DICOM。这说明失败发生在 `dcm2niix` 自行枚举目录的
阶段，而不是 MATLAB 的序列选择阶段。日志中的序列目录本身约为 161–174 个字符；
叠加较长的扫描仪文件名后，完整路径容易达到 Windows 传统的 260 字符限制。

被试级 `parfor` 会增加同时进行的磁盘访问，但不能解释“MATLAB 可读、dcm2niix 枚举
不到同一文件”的稳定差异，因此不作为首要原因。并行只可能放大 I/O 延迟或临时空间
压力。

## 修改

`scripts/neuroimaging/dicom2bids_checked.m` 现在仅在所选序列至少有一个 DICOM 完整
路径达到 260 字符时启用短路径输入：

1. 优先在系统临时目录中创建指向原序列目录的唯一 directory junction；不复制数据，
   `dcm2niix` 看到的是较短的输入路径。若 junction 下的完整文件路径仍达到 260 字符，
   则不使用该 junction。
2. 如果 junction 创建失败（例如来源位置不支持 junction），则只把当前序列复制到唯一
   的本机临时目录，并按顺序改成短文件名后转换。
3. 每次转换持有独立的临时路径，适用于多个 `parfor` worker；函数正常返回或异常退出时
   均执行清理。
4. 原始 DICOM 不移动、不改名；`dcm2niix` 参数继续使用 `-i y`。

短于 260 字符的输入保持原有直接转换路径。复制回退会发出
`DICOM2BIDS:LongPathCopyFallback` warning，便于识别额外 I/O 和临时磁盘占用。

## 验证范围

本次只进行代码级和临时目录级小规模验证，不重新运行完整队列。正式验证时应优先重跑
一个此前出现 `Unable to find any DICOM images` 的 T1 或 DWI B0 序列，并确认日志不再
出现该错误、临时 junction/复制目录已清理且输出 JSON/NIfTI 数量符合原有断言。
