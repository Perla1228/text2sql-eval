# Text2SQL × EvalScope 评测项目

基于 EvalScope 搭建 Text2SQL 模型评测体系：自建中文电商业务评测集 + 执行准确率（EX）指标，横向对比多个大模型并完成错误归因。

## 快速开始

```powershell
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 配置 API Key
copy .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY / DEEPSEEK_API_KEY

# 3. 环境自检
python scripts/check_env.py
```

## 环境要求

- Python 3.11+
- 云端大模型 API（DashScope / DeepSeek，OpenAI 兼容）
- 无需 GPU

## 项目结构

```
text2sql-eval/
├─ data/                 # 评测数据与自建业务库
├─ text2sql_eval/        # adapter / schema / prompts / sql_utils / metrics
├─ scripts/              # check_env / build_biz_db / run_eval / compute_metrics / make_report
├─ results/              # summary.csv / per_sample.csv / error_taxonomy.csv
└─ reports/              # 评测报告 HTML
```

## 指标口径

- **Valid SQL**：生成的 SQL 能被 SQLite 解析（EXPLAIN 不报错）。
- **EM（Exact Match）**：规范化后字符串完全相等（参考指标）。
- **EX（Execution Accuracy）**：预测 SQL 与 gold SQL 在各自库上执行，结果集一致（核心指标）。
