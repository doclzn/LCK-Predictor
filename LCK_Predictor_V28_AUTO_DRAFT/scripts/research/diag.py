import os,sys,sqlite3,importlib
os.environ["MODEL_LEAGUES"]="LCK,LPL"; os.environ["EVAL_LEAGUES"]="LCK"
sys.path.insert(0,r"c:\Users\pc\OneDrive\Desktop\LCK_Predictor_V28_AUTO_DRAFT (1)\LCK_Predictor_V28_AUTO_DRAFT\scripts")
import run_validation_v19 as V
con=sqlite3.connect(V.DB);con.row_factory=sqlite3.Row
df=V.build_dataset(con)
print("cobertura de features por liga (fracao NAO nula):")
for lg in ("LCK","LPL"):
    d=df[df.league==lg]
    print(f"  {lg} n={len(d)}")
    for f in V.MODEL_SPECS["core"]:
        print(f"     {f:24s} {d[f].notna().mean():.3f}")
