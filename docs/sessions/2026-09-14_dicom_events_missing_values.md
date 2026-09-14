# DICOM 转换 events 缺失值修复

## 背景

`dicom2bids_checked.m` 原先将 PsychoPy 的 `duration`、`response_time` 和 `value`
保持为 MATLAB double 后直接写入 TSV。原始数据缺失时会产生 `NaN`，不符合 BIDS 对
TSV 缺失值必须使用 `n/a` 的要求。

## 修改

- events 写出前验证 onset 必须有限、duration 必须为非负有限值或缺失值、trial type
  不得缺失，response time 和 accuracy 不得为无穷值。
- 将 duration、response time 和 accuracy 转为 BIDS 文本表示，并将其中的 `NaN` 明确
  写为 `n/a`。
- 不改变 onset、duration、response time、accuracy 和 trial type 的原有计算公式。

## 验证

MATLAB R2025a `checkcode` 静态检查无问题。使用真实被试
`THU_20231230_160_DHL` 的 SST、n-back 和 switch CSV 运行相同计算及序列化逻辑：

- 三个文件分别包含 3、1、4 个缺失 duration，以及 21、1、0 个缺失 response time；
- 所有非缺失 duration 均为有限非负值；response time 和 accuracy 不含无穷值；
- 写出的临时 TSV 中所有缺失值均为 `n/a`，未残留 `NaN`；
- 系统临时目录中的测试文件在 MATLAB 结束时自动清理。

同一套 `prepareEventsForBids` 和 `numericToBidsText` 规则已由 PsychoPy-only 输出使用
BIDS Validator 3.0.1 验证为 0 error。
