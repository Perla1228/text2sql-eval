# deploy/ — GitHub Pages 部署目录

这个目录里只有一份 `index.html`，就是 `reports/text2sql_eval_report.html` 的副本。
报告是**单文件、零外部依赖**（CSS 内联，不引用任何图片 / CDN / JS），放到任意静态托管都能直接打开。

## 部署方式 A：GitHub Actions（已配好，推荐）

项目根目录已附带 `.github/workflows/pages.yml`，推送到 `main` 分支即自动发布。

1. 新建一个 GitHub 仓库（Public），把本项目推上去：

   ```powershell
   git init
   git add .
   git commit -m "Text2SQL 评测项目与 HTML 报告"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/text2sql-eval.git
   git push -u origin main
   ```

2. 打开仓库 **Settings → Pages**，把 **Source** 设为 **GitHub Actions**（只需设置一次）。

3. 等 Actions 跑完（约 1 分钟），访问：

   ```
   https://<你的用户名>.github.io/text2sql-eval/
   ```

## 部署方式 B：不用 Actions（零配置）

GitHub Pages 的分支发布会直接读取根目录或 `/docs`，所以：

1. 把 `deploy` 目录改名为 `docs`
2. **Settings → Pages → Source** 选 `Deploy from a branch`，分支 `main`，目录 `/docs`
3. 保存后等 1 分钟，访问同一个地址

> 若使用方式 B，可以删掉 `.github/workflows/pages.yml`，避免重复发布。

## 更新报告

报告内容变了以后，重新生成并覆盖副本即可：

```powershell
python scripts/make_report.py
copy reports\text2sql_eval_report.html deploy\index.html
```

## 公开前检查

- `.env` 已在 `.gitignore` 中，**不要**提交（里面是真实的模型 API Key）
- `.venv/`、`__pycache__/`、临时调试脚本也已忽略
- `results/` 是逐题缓存（只含问题、SQL、分数），不含密钥；如不想公开可加进 `.gitignore`
- 报告正文已核对：不含任何 API Key、Bearer token 或本地绝对路径
