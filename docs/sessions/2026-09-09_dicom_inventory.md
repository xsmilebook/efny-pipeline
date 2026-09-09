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
