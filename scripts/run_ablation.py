"""
消融实验：简单提示词 vs 加强提示词
用两个模型各跑一遍 --cache 已缓存的（会跳过），所以清缓存先
"""
import json, time
from pathlib import Path
import pandas as pd
import subprocess, sys

ROOT = Path(__file__).resolve().parent.parent

# 要对比的模型（两个 flash 就够了，省时间省钱）
MODELS = [
    ("glm-4.5-flash", "智谱 glm-4.5-flash"),
    ("deepseek-flash", "DeepSeek flash"),
]

def run_one(model, enhanced, label):
    """运行一个模型+提示词组合"""
    print(f"\n{'='*70}")
    print(f"跑 {model} | {label} ({'加强提示' if enhanced else '简单提示'})")
    print(f"{'='*70}")
    
    cmd = [sys.executable, str(ROOT / "scripts" / "run_eval.py"),
           "--model", model,
           "--limit", "50"]
    if enhanced:
        cmd.append("--enhanced")
    
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    elapsed = time.time() - t0
    
    # 从输出里解析指标
    out = (result.stdout + result.stderr).splitlines()
    ex_line = [l for l in out if "EX（执行准确率）" in l]
    valid_line = [l for l in out if "Valid SQL" in l]
    easy_line = [l for l in out if "easy" in l and "%" in l]
    med_line = [l for l in out if "medium" in l and "%" in l]
    hard_line = [l for l in out if "hard" in l and "%" in l]
    
    def extract_pct(line):
        if not line:
            return None
        import re
        m = re.search(r'= (\d+\.\d)%', line)
        return float(m.group(1)) if m else None
    
    return {
        "model": model,
        "prompt": "enhanced" if enhanced else "simple",
        "elapsed_min": round(elapsed/60, 1),
        "valid_pct": extract_pct(valid_line[0]) if valid_line else None,
        "ex_pct": extract_pct(ex_line[0]) if ex_line else None,
        "easy_pct": extract_pct(easy_line[0]) if easy_line else None,
        "medium_pct": extract_pct(med_line[0]) if med_line else None,
        "hard_pct": extract_pct(hard_line[0]) if hard_line else None,
    }

def metrics_from_cache(model, prompt):
    """直接从 results/ 缓存汇总指标，不调 API"""
    cache_dir = ROOT / "results"
    if prompt == "simple":
        files = cache_dir.glob(f"{model}_simple_*.json")
    else:
        files = [f for f in cache_dir.glob(f"{model}_*.json") if "_simple_" not in f.name]

    records = [json.load(open(f, encoding="utf-8")) for f in files]
    records = [r for r in records if r.get("pred_sql")]  # 空输出是接口失败，不计入分母
    n = len(records)
    if n == 0:
        return None

    def pct(rs, key):
        return round(sum(1 for r in rs if r.get(key, r.get("ex"))) / len(rs) * 100, 1) if rs else None

    return {
        "model": model,
        "prompt": prompt,
        "elapsed_min": None,
        "valid_pct": pct(records, "valid_sql"),
        "ex_pct": pct(records, "ex_answer"),
        "easy_pct": pct([r for r in records if r["difficulty"] == "easy"], "ex_answer"),
        "medium_pct": pct([r for r in records if r["difficulty"] == "medium"], "ex_answer"),
        "hard_pct": pct([r for r in records if r["difficulty"] == "hard"], "ex_answer"),
        "n": n,
    }


FROM_CACHE = "--from-cache" in sys.argv
results = []

if FROM_CACHE:
    for model, label in MODELS:
        for prompt in ("simple", "enhanced"):
            r = metrics_from_cache(model, prompt)
            if r:
                results.append(r)
            else:
                print(f"⚠️ {model} | {prompt} 缓存为空")
else:
    # 先清缓存，然后跑 simple → 再跑 enhanced
    for model, label in MODELS:
        # 清这个模型的缓存
        cache_dir = ROOT / "results"
        for f in cache_dir.glob(f"{model}_*.json"):
            if "simple" not in f.stem and "enhanced" not in f.stem:
                f.unlink()

        # 跑 simple（重命名缓存避免覆盖）
        r = run_one(model, enhanced=False, label=label)
        results.append(r)

        # 把这次的结果改成 simple 标记
        for f in cache_dir.glob(f"{model}_*.json"):
            new_name = f.with_name(f"{model}_simple_{f.name.split('_',1)[1]}")
            f.rename(new_name)

    for model, label in MODELS:
        # 跑 enhanced（清 enhanced 缓存）
        cache_dir = ROOT / "results"
        for f in cache_dir.glob(f"{model}_*.json"):
            if "enhanced" not in f.stem and "simple" not in f.stem:
                f.unlink()

        r = run_one(model, enhanced=True, label=label)
        results.append(r)

# 汇总表
df = pd.DataFrame(results)
print("\n" + "=" * 70)
print("消融实验结果汇总")
print("=" * 70)

for _, r in df.iterrows():
    print(f"\n{r['model']} | {'加强提示' if r['prompt']=='enhanced' else '简单提示'}")
    print(f"  Valid:  {r['valid_pct']}%")
    print(f"  EX:     {r['ex_pct']}%")
    print(f"    easy:   {r['easy_pct']}%")
    print(f"    medium: {r['medium_pct']}%")
    print(f"    hard:   {r['hard_pct']}%")
    print(f"  耗时:   {r['elapsed_min']} 分钟")

# 计算提升
print("\n--- 加强提示 vs 简单提示 的 EX 提升 ---")
for model, label in MODELS:
    simple = df[(df.model == model) & (df.prompt == "simple")].iloc[0]
    enhanced = df[(df.model == model) & (df.prompt == "enhanced")].iloc[0]
    delta = enhanced["ex_pct"] - simple["ex_pct"]
    delta_e = enhanced["easy_pct"] - simple["easy_pct"]
    delta_m = enhanced["medium_pct"] - simple["medium_pct"]
    delta_h = enhanced["hard_pct"] - simple["hard_pct"]
    print(f"\n{model}: 总 EX {simple['ex_pct']}% → {enhanced['ex_pct']}% ({delta:+.1f}%)")
    print(f"  easy {simple['easy_pct']}% → {enhanced['easy_pct']}% ({delta_e:+.1f}%)")
    print(f"  medium {simple['medium_pct']}% → {enhanced['medium_pct']}% ({delta_m:+.1f}%)")
    print(f"  hard {simple['hard_pct']}% → {enhanced['hard_pct']}% ({delta_h:+.1f}%)")

df.to_excel(ROOT / "reports" / "ablation_results.xlsx", index=False)
print(f"\n✅ 消融结果已保存到 reports/ablation_results.xlsx")
