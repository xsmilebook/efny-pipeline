# THU task 头动 confounds 重算与 XCP-D 重跑

用户明确授权使用 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/ADHDnetwork/batchcode/brainproject` 的 `batch_run_recomputemotion.sh` 和 `recompute_motion_25_2_7.sh` 重算 task 头动、覆盖旧 confounds，删除旧 task XCP-D 并重新生成结果。范围仅为 STC THU task，rest、no-STC、BIDS、FreeSurfer 和 fMRIPrep 影像不变；已有 task 效应 regressors 不重建。

检查发现外部脚本输入与选择器均写死 rest，计算脚本指定 q_cn。仓库保存同名 task 适配版，外部原文件只读保留。算法沿用指定脚本：25.2.7 FSLMotionParams 从 HMC 变换及 boldref 重建六参数，ExpandModel 生成 24 项，半径 50 mm 的 Power FD，按 FD>0.5 mm 或标准化 DVARS>1.5 重建 motion_outlier，保留其他 confounds 和 JSON 元数据。适配仅改变显式 task 输入路径、任务选择与项目要求的 singularity/3.7.0、q_fat_c；每个重算作业保留原脚本 3 CPU，数值线程 1，不重新启动完整 fMRIPrep。

当前集群项目根目录 `/ibmgpfs/cuizaixu_lab/xuhaoshu/projects/efny-pipeline`，输入为 `data/interim/neuroimaging/fmriprep/THU/task/`，清单 569 人／1,522 run。已抽查 HMC boldref 和 orig→boldref xfm 存在。起始 Git 5bbccd7，两端工作区干净；账号队列仅有无关交互 bash，没有活动影像作业。旧结果在 2026-10-29 曾通过原检查，但未包含上游 25.2.5 头动参数修复，不能作为本次校正后的最终结果。

先在独立 staging 路径重算一人的三个任务，确认数值和非头动项后提交全量。完整新文件必须全部通过时间轴、非头动列、24 项和 FD 一致性检查，才备份并原子替换 task fMRIPrep confounds。之后归档旧日志、检查终态／锁／路径和符号链接，清理仅属 task_background 的旧 XCP-D 结果、work/temp 及受其影响的下游产物，重新 prepare。沿用三个 task 的真实试跑→残差门槛→全批→审计链，不改变回归、滤波、censoring、atlas 或任务采样偏移。

代码和实际运行作业号、范围、版本及成功／失败状态继续补充；本轮尚未重算或清理正式产物。

## 首次试算与环境阻塞

适配代码 `4b35fbe` 已提交推送并在集群干净工作区快进同步。在 `outputs/logs/neuroimaging/fmriprep/THU/task/confounds_refresh_20261101/` 冻结原输入清单、569 人名单、首人试跑／其余名单、原 1,507-run background 范围，保存外部原脚本副本及 run.json；校正 staging 为其下 `corrected_confounds/`，不会直接写入正式 fMRIPrep。

首次试算 `15494320`（sub-THU202311180133，3 个 task）在容器启动前 FAILED、127:0，用时 2 秒。指定镜像 `/ibmgpfs/cuizaixu_lab/xuxiaoyu/softwarepackages/singularity/fmriprep-25.2.7.simg` 的父目录权限是 700，仅 xuxiaoyu 可访问；xuhaoshu 无进入／读取权限。当前账号可读镜像目录没有 25.2.7。已向用户说明并请求开放读取权限或提供可读的 25.2.7 镜像／环境；未绕过权限、未使用旧版实现代替、未重算完整 fMRIPrep。旧 confounds 和 XCP-D 均未修改。

用户询问为何需要镜像：指定脚本本身通过 singularity exec 调用 25.2.7 的修正实现和依赖，而非单纯 Bash 数值计算。容器不是算法的必要形式，但正确版本的 FSLMotionParams、FD、ExpandModel 和依赖环境是必要条件；项目 uv 环境目前未安装完整 fMRIPrep 依赖。继续准备核验和替换入口，计算等待可用的指定版本环境。

## 核验、替换与清理入口

新增 `refresh_thu_task_confounds.sbatch`（q_fat_c、3 CPU）和 `refresh_thu_task_confounds.py`。从根目录以 `python -m scripts.neuroimaging.refresh_thu_task_confounds` 执行，复用 rest 的同一个 `audit_run`，无 sys.path 修改或新依赖。参数为 `--refresh-root <本轮目录> --jobs <subject/job_id TSV>`，可加 `--subjects <首人名单>` 做试跑检查；不加 `--apply` 只核验，完整范围加 `--apply` 才备份覆盖、归档旧日志和表格、删除有明确归属的 task XCP-D/work/temp 与旧独立 FC、重新 prepare 并提交原试跑→全批→审计链。

入口验证所有重算作业 COMPLETED／0:0、TSV／JSON 与原清单完全匹配、24 项与 50 mm FD 的数值一致、非头动列不变和帧数不变。覆盖前保留压缩备份与原 fMRIPrep marker，使用逐文件原子替换，追加含 25.2.7 来源的 confounds_override。删除前验证旧成功作业的终态、活动作业与锁，以及每个 owner／子路径的边界和符号链接；保留日志和删除明细，不删除 rest、fMRIPrep 影像、BIDS 或 FreeSurfer。全量 prepare 完成后就绪名单须仍等于原 1,507-run 范围。部分覆盖后不自动重试，已有备份或 override 时要求先审阅对应记录。

本地完整测试发现 43 项，41 项通过、2 项因本地无 Nilearn 跳过（容器专用投影测试在前轮已通过），耗时 13.174 秒。新增验证覆盖 task 与 rest 共用的运动／FD／非头动不变性、只枚举 task 归属清理目标、拒绝 owner／child 符号链接和拒绝 rest 配置。三个新增 shell 入口通过 bash -n，Python 模块 --help 和 git diff --check 通过；本轮合成目录已自动清理，前轮已记录的清理受限目录未另行操作。

## 用户指定复制镜像

用户进一步要求将镜像复制到 `/ibmgpfs/cuizaixu_lab/xuhaoshu/packages/singularity/` 再使用。已尝试从指定原镜像复制到该目录的 `fmriprep-25.2.7.simg`，采用 `.copying` 临时文件、大小核验后更名；但在打开源文件时仍被真实文件系统权限拒绝，未生成目标镜像，也未创建部分副本。已说明复制仍需要源目录／文件读取权限，请用户开放源读取或由有权限账号放置镜像。任务计算入口已改为用户指定的自有目标路径，尚不能启动真实重算。

核验与清理代码提交为 `d17a682`，已推送并在集群干净工作区快进同步。集群 uv 离线只读检查通过，模块 --help 可正常使用，三项 task 清理边界测试在 Linux 同环境通过（0.017 秒）。最终复查源镜像仍不可读、自有目标镜像不存在、没有遗留 .copying 副本；因此不得提交后续重算、覆盖或删除作业。此次阻塞是源目录的操作系统访问权限，不是自动审批拒绝。

## 按新授权自行构建 25.2.7 镜像

用户取消复制方案，明确授权自行打包 fMRIPrep 25.2.7。使用 NiPreps 官方镜像 `docker://nipreps/fmriprep:25.2.7`，按[官方 Singularity 方法](https://www.nipreps.org/apps/singularity/#preparing-a-singularity-image)构建到自有目录 `packages/singularity/fmriprep-25.2.7.simg`。登录节点短时测试代理 `http://10.11.100.5:3128` 可连接 registry-1.docker.io，Docker Hub 的 25.2.7 标签可访问；共享文件系统可用空间约 104 TB。

新增 `build_fmriprep_motion_image.sbatch`，在 q_fat_c 申请 3 CPU，沿用 Singularity 3.7.0 和原代理；不修改管理员配置。该版本无逐次构建的压缩线程 flag，且系统 mksquashfs procs=0，所以仅在本次构建 PATH 中给真实 mksquashfs 追加 `-processors $SLURM_CPUS_PER_TASK`，Go 并行也限制为申请核数。临时 bundle 和 OCI cache 位于自有容器目录的独立作业子目录，失败时保留来源和缓存，不覆盖任何已有镜像。先构建唯一临时镜像，实际验证 fMRIPrep=25.2.7，并导入指定计算脚本所需 FSLMotionParams／FD／ExpandModel／spike_regressors 后，才更名发布到正式路径。这里只构建工具，不运行完整 fMRIPrep。

首个构建作业 `15494321` 在下载前因 PATH 不包含压缩工具所在目录而退出（FAILED、1:0，1 秒）；现场确认 mksquashfs 位于 `/usr/sbin/mksquashfs`，明确补入 `/usr/sbin` 后重提，不自动寻找其他版本或修改系统配置。旧影像、confounds 和 XCP-D 结果未受影响。

构建重提 `15494322` 已在计算节点开始下载官方镜像；代码 `94b46bb`。准备 `advance_task_motion_refresh.sbatch`：只有单人三个 run 的实际运动重算与 audit_run 审计通过且 Slurm 0:0，才用指定 batch 脚本提交原冻结名单中的剩余 568 人。按每次成功回执冻结 569 人／作业 TSV，afterok 全部重算成功后提交全量审计与 --apply；--apply 内部核验完成后才备份替换、清理、重新 prepare 并衔接原 task XCP-D 试跑链。任何前置失败都不覆盖或删除正式数据。首个权限失败的历史作业不混入成功重算清单。
