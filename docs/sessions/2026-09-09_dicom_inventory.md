# DICOM 清单与 DICOM2BIDS 前置核查

## 目标

为 `Z:\xuhaoshu\20260909_bp_DICOM` 生成可供 GPT 分析的序列文件夹名称清单。只读取“被试 / MRIdata / 导出目录 / Study / 序列文件夹”这一层，不检查序列内文件。

## 数据结构观察

- 根目录当前包含 18 个被试目录。
- 常见结构为“被试 / MRIdata / 导出患者目录 / Study / 序列目录 / DICOM 文件”。
- 被试直接子目录通常为 `MRIdata`、`PHYSIO` 和 `PSYCH`，但存在缺失情形。
- 序列文件主要为 `.IMA`，另有 `.SR`；生理和行为文件包括 `.puls`、`.resp`、`.csv`、`.log` 和 `.psydat`。

## 实现决策

- `series_folders.jsonl` 为 GPT 主输入，每行对应一个被试。
- `series_folders.csv` 为每序列文件夹一行的长表。
- 不导出原始被试目录名，以解析得到的精简被试 ID 代替；保留 `MRIdata` 以下的容器相对路径。相对路径可能含扫描仪导出名称，对外分享前需要检查。
- 从 `MRIdata` 向下递归；当某目录的直接子目录命中 `EP2D_`、`LOCALIZER`、`PHOENIXZIPREPORT`、`SMS*_BOLD_`、`SMS*_DIFF_`、`T1_` 或 `T2_` 时，记录该目录相对 `MRIdata` 的路径，并仅导出命中前缀的直接子目录。
- 不再把命中的容器解释为一次 scan，也不生成 `scan_01`、`scan_02`。检测不依赖固定深度，因此兼容 `MRIdata/container/sequence` 和 `MRIdata/wrapper/container/sequence`。
- 不统计文件数，不读取 DICOM 头，不生成 `bids_guess`。

## 运行命令

```powershell
python .\scripts\neuroimaging\export_series_folders.py "Z:\xuhaoshu\20260909_bp_DICOM"
```

JSONL 默认写入 `outputs/logs/neuroimaging/series_folder_inventory/`，CSV 默认写入 `outputs/tables/neuroimaging/series_folder_inventory/`。

## 新版 DICOM2BIDS 转换

新增 `scripts/neuroimaging/dicom2bids_checked.m`、
`run_dicom2bids_checked.m` 和 `bids_subject_label.m`，不修改 `docs/ref/` 中的
参考脚本。新版转换仍将一个被试的所有原始 scan 合并为一个 BIDS session，
但在内部重新递归识别直接包含序列目录的 scan 容器，并在复制到 BIDS 前完成
序列取舍。

主要规则：

- REST0--REST99 只保留 180 帧且采集时间最晚的一条；重复 SST、NBACK、SWITCH
  保留被试内帧数最多、时间最晚的一条。FM、PM、PR 和 NBACK_V 不处理。
- 同一个 scan 容器内不能同时出现普通 fmap 和 `_TASK` fmap；二者位于不同
  scan 时不冲突。较短的 fmap 视为未完成，
  过滤后 AP/PA 数量必须平衡。所有有效配对按采集时间统一编号为
  `run-1`、`run-2` 等，同一对 AP/PA 共用 run。
- fmap 的 `IntendedFor` 只包含同一来源 scan 中最终保留的 BOLD，并同时写入
  `B0FieldIdentifier`/`B0FieldSource`。
- T1 仅接受唯一的 Prescan Normalize MPRAGE；多个或缺少该重建时终止。
- 主 DWI 使用精确目录名识别；ADC、FA、COLFA、TENSOR、TRACEW 等派生序列
  显式忽略。重复主 DWI 和 T2 均先选择 DICOM 文件数最多者，数量相同时选择
  采集时间最晚者。DWI B0 只允许从最终主 DWI 所在的同一个 scan 中选择，再按
  文件数和采集时间取舍；该 scan 中没有 DWI B0 时终止转换。这里约束的是 DWI
  B0 JSON 指向主 DWI 的 `IntendedFor`，不改变 functional fmap 指向 BOLD 的规则。
- 同一任务存在多个行为 CSV 时，解析文件名中的日期和时间到毫秒，并选择
  时间最晚者；无法解析时间或最晚时间并列时终止。
- 批处理入口在转换前拒绝重复源目录和映射到同一 BIDS 标签的多个源目录。
- 转换不依赖文件夹清单 CSV；每个被试在 NIfTI 中间目录写出
  `conversion_manifest.tsv`。

转换后的每对 fmap 还会核对 NIfTI 维度、相反的
`PhaseEncodingDirection`，以及两方向共有的 `EchoTime`、`RepetitionTime`
和 `TotalReadoutTime`。

使用 `Z:\xuhaoshu\THU_604` 做了真实 DICOM 冒烟验证：74 张的
`EP2D_SE_2MM_AP_TASK_0014` 被标记为不完整并排除；192 张的
`AP_TASK_0015` 与 192 张的 `PA_TASK_0013` 被保留为同一个 `run-1`。
测试产生的临时 NIfTI/BIDS 文件已清理。
