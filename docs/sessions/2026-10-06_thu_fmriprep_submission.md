# THU fMRIPrep 集群提交

## 用户要求与部署

用户要求在集群批量提交 THU 全部被试的 fMRIPrep。

- SSH 登录节点：`CIBR-login`（login01），用户 `xuhaoshu`。
- 已有代码位于 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，版本 `470d55e`，工作区干净。
- 用户指定的 `/ibmgpfs/cuizaixu_lab/xuhaoshu/DATA_C/projects/efny-pipeline` 原先不存在；
  已从已有仓库通过 Git 建立独立检出，正式结果仍使用这个指定根目录。
- 本项目代码已部署，未同步或复制输入、衍生数据与已有结果。
- 登录节点使用 uv 0.10.12，建立独立 `.venv`：Python 3.11.15、NumPy 2.2.6、NiBabel 5.4.2。
  `uv sync --frozen --python 3.11 --python-platform x86_64-manylinux_2_17 --link-mode copy`
  及只读离线环境检查、依赖兼容检查、导入验证通过。
- fMRIPrep 镜像 25.2.5、license 与 TemplateFlow 目录可访问，Singularity 3.7.0 模块可用。

## 输入与计算节点验证

- 输入根目录：`/ibmgpfs/cuizaixu_lab/liyang/BrainProject25/Tsinghua_data/BIDS_new`。
- 共 764 个 `sub-THU*` 目录，其中 745 个有静息态 BOLD，19 个没有。
  直接全量 `prepare --dataset THU` 因首个缺失被试 `sub-THU202311180137` 停止；
  该被试检查到的输入只有解剖影像，未自动排除或填补。
- 对有静息态数据的候选名单进行只读科学身份检查：745 名被试、2483 个 run，
  无 session、整数 run 编号唯一的要求通过。被试 run 数分布为
  1 个：16 人；2 个：11 人；3 个：434 人；4 个：282 人；5 个：1 人；10 个：1 人。
- 审计与候选／缺失名单保存在集群项目的
  `outputs/logs/neuroimaging/fmriprep/THU/rest/`：
  `input_availability_20261006.csv`、`subjects_rest_available_20261006.txt`、
  `subjects_missing_rest_20261006.txt`。用户随后明确回复“直接提交”，已采用 745 人的名单。
- 计算节点预检作业 `15214450`，q_fat_c、6 CPU，在 fat17 完成，退出码 0。
  验证离线 Python 环境、科学库导入和真实 fMRIPrep 镜像的版本启动；未执行影像预处理。
- 提交前查到的既有作业 `15073160` 为 data_driven_EF 路径下的 bash 作业，
  未发现 efny-pipeline 同批 fMRIPrep 作业。

## 正式提交状态

用户明确同意先提交有静息态数据的 745 人，19 人保留缺失名单。

- `prepare --dataset THU --subjects outputs/logs/neuroimaging/fmriprep/THU/rest/subjects_rest_available_20261006.txt`
  已生成正式清单，745 人、2483 个 run。
- 首批于集群时间 02:04:26–02:04:38 提交，作业编号 `15214451`–`15215195`，
  提交清单 `submission_batch_20261006.csv`，运行代码版本 `25fcbdb`。
- 首批作业在版本检查时失败：脚本导出 `TEMPLATEFLOW_HOME=/templateflow` 后，
  无挂载调用镜像 `--version`，导入 TemplateFlow 时尝试在镜像只读文件系统建立该目录。
  失败发生在正式预处理前，既有无挂载预检未覆盖这一环境组合。
- 检查剩余活动作业时首批已全部结束，没有实际执行取消；不影响其他项目的作业。
- 已修正 fMRIPrep／XCP-D 版本检查，复用完整命令的挂载和环境，追加 `--version`。
  不改变已确认的科学分析参数。
- 修正后的计算节点验证和重提交状态将继续记录。
