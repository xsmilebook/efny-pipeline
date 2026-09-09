# Project Structure

正式流程和推荐入口见 `README.md` 与 `docs/workflow.md`。
注册的命令或 `scripts/` 下的专用入口；目录结构与输出归属以本文为准。

```
personalized_prediction/        # 项目根目录
├── README.md                   # 项目简介与快速入口
├── AGENTS.md                   # AI 协作与修改约束
├── PLAN.md                     # 计划与任务拆解
├── ARCHITECTURE.md             # 结构说明（本文）
├── configs/                    # 项目配置文件
│
├── docs/                       # 方法、流程与决策记录
│   ├── data_dictionary.md      # 数据字典（数据说明）
│   ├── workflow.md             # 可复现流程
│   ├── methods.md              # 方法学细节
│   ├── reports/                # 研究计划、阶段性总结与正式文档
│   └── sessions/               # 会话记录
│
├── src/                        # 可复用模块（不含硬编码路径）
│   ├── imaging/                # 影像预处理与影像指标提取
│   ├── behavior/               # 行为任务与人口学预处理
│   └── inventory/              # 问卷下载、量表清洗、Session 匹配与计分
│
├── scripts/                    # 执行入口（本地/HPC/主流程脚本）
│   ├── neuroimaging/
│   ├── behavior/
│   └── inventory/              # 可直接运行的量表流水线 Python 入口
│
│
├── data/                       # 项目分析数据（不纳入版本控制），用于存放数据型对象：预处理结果、connectivity matrix、analysis-ready tables
│   ├── external/               # 外部第三方输入
│   ├── raw/                    # 原始输入（非脚本产出）
│   │   ├── app_data/       # 原始的行为任务数据
│   │   ├── inventory/      # 原始的量表数据
│   │   ├── neuroimaging/
│   │   │   ├── BIDS/       # 原始 BIDS 影像数据
│   │   │   ├── PHYSIO/     # 按 APBN 采集目录组织的原始生理日志
│   │   │   └── PSYCH/      # 按 APBN 采集目录组织的心理任务原始文件
│   │   └── metadata/
│   ├── interim/                # 中间衍生结果
│   └── processed/              # 可复用清洗结果
│
├── outputs/                    # 运行产物（不纳入版本控制）；各类型下必须继续按生产模块分目录
│   ├── figures/                # 图形；含 app、inventory、psychometrics、psychopy_nback、neuroimaging 等模块
│   ├── tables/                 # CSV/XLSX 表格；共享根目录不直接放文件
│   ├── logs/                   # JSON manifest 与作业日志；采用与生产模块相同的层级
│   ├── results/                # 模型等非表格结果；当前主要为 fc_app_prediction/
│   └── reports/                # 正式交付附件；继续按报告模块组织
│
├── tests/                      # 项目测试脚本（不纳入版本控制）
└── notebooks/                  # 探索性分析（不纳入版本控制）
```

`outputs/<type>/` 是共享类型根目录，不是生产模块。新增产物必须进入上述模块目录；若新增
跨模块分析，应先在本节登记其独立模块。生产端与直接读取端必须共同使用配置或路径常量中
记录的新路径，不读取旧的平铺位置作为兼容回退。模块级清理只能删除该模块拥有的目录。
