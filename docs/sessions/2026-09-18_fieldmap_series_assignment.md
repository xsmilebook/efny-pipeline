# 基于序列编号的 functional fieldmap 分配

`dicom2bids_checked.m` 原先在同一个 scan 同时存在普通和 `_TASK` functional
fieldmap 时，按 rest/task 类型分配；同一类型存在多对 fmap 时，一个 BOLD 还可能同时
引用多对场图。该规则不能正确表达重复采集按扫描顺序服务后续 BOLD 的情况。

现改为在每个 scan 内按 DICOM `SeriesNumber` 建立一对一关联。AP 和 PA 候选分别按
`SeriesNumber` 排序后配对；每个保留的 BOLD 只选择位于它之前、且 pair 中较大序列编号
最接近该 BOLD 的完整 fmap pair。因此序列 5/6 分配给 BOLD 7，序列 10/11 分配给
BOLD 12。普通和 `_TASK` 名称仍用于分开形成 AP/PA pair，但不再决定 rest/task 关联。

选择阶段若某个保留的 BOLD 在同一 scan 内找不到前置完整 pair，立即报错。转换后还会
再次验证每个成功转换的 BOLD 是否恰好由一个仍保留的 fmap pair 索引；若 AP 或 PA
转换失败导致关联丢失，同样报错，不继续写出缺少场图关联的 BIDS。BOLD JSON 的
`B0FieldSource` 与 fmap JSON 的 `IntendedFor` 使用同一份序列编号分配结果。

使用 MATLAB R2025a `checkcode` 静态检查主脚本，结果为 `CHECKCODE_COUNT=0`。另以合成
序列完成定向冒烟测试：两对 fmap 的序列编号分别为 5/6 和 10/11，两个 BOLD 的编号
分别为 7 和 12，验证得到 5/6→7、10/11→12；将第一个 BOLD 编号改为 4 后，验证脚本
按预期报出缺少前置完整 fmap pair。测试文件位于系统临时目录并已清理。完整 DICOM
转换依赖真实影像且运行时间较长，本次未重跑。
