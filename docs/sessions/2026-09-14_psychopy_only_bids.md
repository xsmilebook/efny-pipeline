# PsychoPy-only BIDS events 覆盖包

## 目标

新增一个不重新转换影像、只生成任务 events 的 MATLAB 入口。输出作为独立的 BIDS
覆盖包，可将其中的同名 events 文件重新上传至集群并覆盖旧版本。

## 实现

- 新增 `scripts/neuroimaging/psychopy2bids_checked.m`，输入原始被试根目录、独立输出
  BIDS 根目录和源文件夹名单。
- 输出根目录写入 BIDS 必需的 `dataset_description.json`；每个被试目录只创建 `func`
  子目录，其中包含 SST、n-back 和 switch 的 `events.tsv` 及对应 JSON sidecar。
- 被试标签及 events 文件名与完整 DICOM-to-BIDS 转换保持一致，因此上传到正式 BIDS
  根目录时可以按同名路径覆盖旧 events。
- 多份同任务 PsychoPy CSV 先按数据行数选择最完整者；最大行数并列时，再按文件名时间
  戳选择最新者。
- events 的 onset、duration、trial type、response time 和 accuracy 计算沿用当前转换逻辑；
  数值缺失按 BIDS 规则写为 `n/a`，JSON sidecar 描述自定义列和 PsychoPy 来源。
- 本地重复运行时，MATLAB 会覆写同名 TSV、JSON 和根级 `dataset_description.json`，但
  不删除输出目录中的其他文件。
- 合并到集群正式数据集时只上传覆盖包中的 `sub-*` 目录，并启用同名文件覆盖；根级
  `dataset_description.json` 仅用于覆盖包独立验证，不应替换正式数据集的根元数据。

## 验证

完成以下验证：

- MATLAB R2025a `checkcode` 静态检查无问题。
- 使用真实被试 `THU_20231230_160_DHL` 的三份 PsychoPy CSV 转换，SST、n-back、
  switch 分别生成 120、120、144 行 events。
- 在同一输出目录连续运行两次，三份 TSV 和 JSON 均可按同名路径正常覆写。
- 合成同任务多候选场景：较旧文件行数更多时选择较旧文件；行数相同时选择时间戳较新
  且内容可识别的文件。
- 使用 BIDS Validator 3.0.1 验证真实转换结果：7 个文件、1 名被试，0 error。剩余 6 个
  warning 均为独立覆盖包没有填写 README、Authors、License、HEDVersion 和
  SourceDatasets 等推荐级根元数据，不影响 BIDS 合规通过。
