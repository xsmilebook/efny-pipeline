# DICOM 清单与 DICOM2BIDS 前置核查

## 目标

为 `Z:\xuhaoshu\20260909_bp_DICOM` 先生成可供人工和 GPT 分析的去标识化目录事实清单，用于忠实记录各被试的直接子目录、扫描组、序列文件夹和文件数。此阶段不执行 DICOM/BIDS 分类或冲突裁决。

## 数据结构观察

- 根目录当前包含 18 个被试目录。
- 常见结构为“被试 / MRIdata / 导出患者目录 / Study / 序列目录 / DICOM 文件”。
- 被试直接子目录通常为 `MRIdata`、`PHYSIO` 和 `PSYCH`，但存在缺失情形。
- 序列文件主要为 `.IMA`，另有 `.SR`；生理和行为文件包括 `.puls`、`.resp`、`.csv`、`.log` 和 `.psydat`。

## 实现决策

- `folder_inventory.jsonl` 为 GPT 主输入，每行对应一个被试，便于分批处理并保留层级结构。
- `series_folders.csv` 为每序列文件夹一行的长表，便于电子表格核查。
- 默认不导出原始被试目录名或含姓名的中间相对路径；中间 MRI 容器匿名编号为 `scan_01`、`scan_02`。
- 仅导出目录名、文件数和扩展名分布，不读取 DICOM 头，不生成 `bids_guess`，不判断协议缺失或冲突。
- SMB 映射盘使用单次 `os.walk()` 枚举，避免重复访问网络目录。

## 运行命令

```powershell
python .\scripts\neuroimaging\export_series_folders.py "Z:\xuhaoshu\20260909_bp_DICOM"
```

JSONL 默认写入 `outputs/logs/neuroimaging/series_folder_inventory/`，CSV 默认写入 `outputs/tables/neuroimaging/series_folder_inventory/`。
