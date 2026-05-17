# wf-runner

一个极简的命令行工作流管理器，只做一件事：按顺序跑你的 `.sh` 脚本，失败重试，反复失败则跳过当前阶段，继续下一个。

零依赖，仅需 bash。

## 快速开始

```bash
chmod +x wf-runner
./wf-runner my_workflow.conf
```

## 配置文件格式

```ini
# 注释以 # 开头
# TASK 定义一个任务阶段，内含多个脚本，按顺序执行

TASK: 数据预处理
RETRIES: 1                          # 本任务脚本失败后的重试次数（可选，默认 3）
DELAY: 10                           # 重试间隔秒数（可选，默认 5）
TIMEOUT: 3600                       # 单个脚本最长执行秒数（可选，默认无限制）
./scripts/download.sh
./scripts/tokenize.sh

TASK: 模型训练
RETRIES: 2
DELAY: 30
TIMEOUT: 259200
torchrun --nproc_per_node=8 train.py --epochs 10

TASK: 通知
./scripts/notify.sh
```

### 指令说明

| 指令 | 作用域 | 说明 |
|------|--------|------|
| `TASK: <名称>` | - | 开始一个新任务阶段 |
| `RETRIES: N` | 当前 TASK | 脚本失败后重试 N 次（默认 3） |
| `DELAY: N` | 当前 TASK | 重试前等待 N 秒（默认 5） |
| `TIMEOUT: N` | 当前 TASK | 单个脚本最长运行 N 秒，超时则 kill（默认无限制） |

### 脚本命令支持两种形式

```ini
./path/to/script.sh --arg1 --arg2    # 路径形式，会检查文件是否存在
torchrun --nproc_per_node=8 train.py # 命令形式，会检查命令是否在 PATH 中
python eval.py --batch_size=4        # 同样支持
```

## 执行逻辑

```
对于每个 TASK:
  对于 TASK 内的每个脚本（按顺序）:
    执行脚本
    ├── 成功 → 继续下一个脚本
    └── 失败 → 重试（等 DELAY 秒，最多 RETRIES 次）
              ├── 重试成功 → 继续下一个脚本
              └── 重试耗尽 → 跳过当前 TASK 剩余脚本，进入下一个 TASK

所有 TASK 跑完后打印汇总
```

关键行为：
- **事务性**：一个 TASK 内某脚本反复失败，该 TASK 的后续脚本直接跳过，不会跑
- **任务隔离**：当前 TASK 失败不影响后续 TASK 的执行
- **退出码**：有任一 TASK 失败则退出码为 1，全部通过则为 0

## 命令行参数

```bash
./wf-runner [config_file]

# 环境变量覆盖默认值
MAX_RETRIES=5 RETRY_DELAY=60 LOG_DIR=./logs ./wf-runner my.conf
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `config_file` | `workflow.conf` | 配置文件路径 |
| `MAX_RETRIES` | `3` | 全局默认重试次数 |
| `RETRY_DELAY` | `5` | 全局默认重试间隔（秒） |
| `LOG_DIR` | `./logs` | 日志输出目录 |

## 输出

### 终端

实时显示每个脚本的执行状态和最终汇总：

```
══════════════════════════════════════════════
  wf-runner
  Config:   demo.conf
  Tasks:    4
  Retries:  3 / Delay: 1s
  Started:  Sun May 17 10:06:53 2026
══════════════════════════════════════════════

── TASK: data_preprocessing ──
[10:06:53] INFO  Run: ./test/test_ok.sh
[10:06:53] PASS  ./test/test_ok.sh
[10:06:56] PASS  ./test/test_sleep.sh
  >> TASK PASS

── TASK: model_training ──
[10:06:56] INFO  Run: ./test/test_flaky.sh
[10:06:56] FAIL  Failed (exit=1): ./test/test_flaky.sh
[10:06:56] WARN  Retry 1/2: ./test/test_flaky.sh
[10:06:57] PASS  ./test/test_flaky.sh
  >> TASK PASS

── TASK: model_evaluation ──
[10:07:02] FAIL  Failed (exit=1): ./test/test_fail.sh
[10:07:03] FAIL  All 2 retries exhausted: ./test/test_fail.sh
[10:07:03] WARN  Aborting task — remaining scripts skipped
  >> TASK FAIL

── TASK: deploy ──
[10:07:04] PASS  ./test/test_ok.sh
  >> TASK PASS

══════════════════════════════════════════════
  SUMMARY
  Elapsed:  13s
  Passed:   7    Failed:   1
══════════════════════════════════════════════
  [PASS] data_preprocessing
  [PASS] model_training
  [FAIL] model_evaluation
  [PASS] deploy

  Logs: ./logs/
══════════════════════════════════════════════
```

### 日志文件

每个 TASK 的完整 stdout/stderr 保存在 `logs/<任务名>.log`，任务名中的 `/` 替换为 `_`。

## 实战示例：MindSpeed 模型训练 + 评测

```ini
# mindspeed_workflow.conf

TASK: data_prepare
RETRIES: 1
DELAY: 10
TIMEOUT: 3600
./scripts/00_check_env.sh
./scripts/01_preprocess_data.sh
./scripts/02_pack_dataset.sh

TASK: model_train
RETRIES: 2
DELAY: 30
TIMEOUT: 259200
torchrun --nproc_per_node=8 pretrain_gpt.py --global-batch-size 128

TASK: ckpt_convert
TIMEOUT: 7200
./scripts/20_convert_to_hf.sh

TASK: model_eval
RETRIES: 1
DELAY: 30
TIMEOUT: 86400
./scripts/30_eval_perplexity.sh
./scripts/31_eval_ceval.sh
./scripts/32_eval_mmlu.sh

TASK: notify
./scripts/99_send_webhook.sh
```

```bash
nohup ./wf-runner mindspeed_workflow.conf > wf.log 2>&1 &
```

## 适用场景

- 模型训练/评测的多阶段流水线
- 数据处理 ETL
- 批量实验脚本编排
- CI/CD 中的多步骤 shell 任务

## 不适用场景

- 需要 DAG 复杂依赖的（这个工具只有线性的阶段内顺序 + 阶段间顺序）
- 需要并行执行的（所有任务严格串行）
- 需要分布式调度的（只是一个单机 runner）

## 依赖

仅需 `bash`（4.0+），以及系统自带的 `timeout`（GNU coreutils，Linux 默认有）。
