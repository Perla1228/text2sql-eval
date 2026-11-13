Get-Content .env | ForEach-Object { if ($_ -match '^[A-Z_]+=') { $n,$v = $_ -split '=',2; Set-Item "env:$n" $v } }
cd C:\Users\perla\Documents\Trae-CN\temp_20261028_01\text2sql-eval
.\.venv\Scripts\Activate.ps1
python scripts/run_eval.py --model glm-4.5-flash --api-url https://open.bigmodel.cn/api/paas/v4 --api-key $env:ZHIPU_API_KEY --limit 3 --enhanced
