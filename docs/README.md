# docs/ — GitHub Pages 站点目录

这里只有一份 `index.html`，即 `reports/text2sql_eval_report.html` 的副本。
报告是**单文件、零外部依赖**（CSS 内联，不引用任何图片 / CDN / JS），任何静态托管都能直接打开。

## 发布方式：从分支的 /docs 目录发布（无需 Actions）

1. 仓库页面 → **Settings → Pages**
2. **Source** 选 **Deploy from a branch**
3. 分支选 **main**，目录选 **/docs**，点 **Save**
4. 等 1 分钟左右，访问：

   ```
   https://perla1228.github.io/text2sql-eval/
   ```

## 更新报告

```powershell
python scripts/make_report.py
copy reports\text2sql_eval_report.html docs\index.html
git add docs/index.html
git commit -m "更新评测报告"
git push
```

推送后 Pages 会自动重建，约 1 分钟生效。

## 公开前检查

- `.env` 已在 `.gitignore` 中，里面是真实 API Key，**不要**提交
- `.venv/`、`__pycache__/`、临时调试脚本与日志也已忽略
- `results/` 为逐题缓存（问题、SQL、分数），不含密钥；如需隐藏可加入 `.gitignore`
- 报告正文已核对：不含 API Key、Bearer token 或本地绝对路径
