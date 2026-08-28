"""Salva ou restaura o banco versionado no git, comprimido.

O SQLite tem ~55 MB e cresce; o git guarda cada versao para sempre, entao
commitar o arquivo cru incharia o repositorio em 55 MB por atualizacao.
VACUUM + gzip derruba isso para ~14 MB.

Uso:
    python scripts/db_snapshot.py save      # banco  -> data/lck_data_v1.sqlite.gz
    python scripts/db_snapshot.py restore   # .gz    -> banco
    python scripts/db_snapshot.py status    # compara os dois

`save` nao toca no banco original: o VACUUM roda sobre uma copia.
`restore` recusa sobrescrever um banco mais novo que o snapshot, a menos
que receba --force.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "lck_data_v1.sqlite"
GZ = ROOT / "data" / "lck_data_v1.sqlite.gz"


def mb(p: Path) -> float:
    return p.stat().st_size / 1048576


def stamp(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def save() -> int:
    if not DB.exists():
        print(f"ERRO: banco nao encontrado: {DB}")
        return 2
    # VACUUM numa copia, para nunca mexer no banco que o app pode estar usando.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "vacuum.sqlite"
        src = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        dst = sqlite3.connect(str(tmp))
        src.backup(dst)          # copia consistente mesmo com WAL ativo
        dst.execute("VACUUM")
        dst.close(); src.close()
        with open(tmp, "rb") as f, gzip.open(GZ, "wb", compresslevel=9) as g:
            shutil.copyfileobj(f, g)
    print(f"snapshot salvo: {GZ.name}  {mb(DB):.1f} MB -> {mb(GZ):.1f} MB")
    print("agora: git add data/lck_data_v1.sqlite.gz && git commit && git push")
    return 0


def restore(force: bool) -> int:
    if not GZ.exists():
        print(f"ERRO: snapshot nao encontrado: {GZ}")
        return 2
    if DB.exists() and DB.stat().st_mtime > GZ.stat().st_mtime and not force:
        print(f"ABORTADO: o banco local e MAIS NOVO que o snapshot.")
        print(f"  banco    {stamp(DB)}")
        print(f"  snapshot {stamp(GZ)}")
        print("Se quer mesmo descartar o banco local, repita com --force.")
        return 1
    if DB.exists():
        bak = DB.with_name(f"{DB.stem}.pre-restore-"
                           f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}{DB.suffix}")
        shutil.copy2(DB, bak)
        print(f"backup do banco atual: {bak.name}")
    for suf in ("-wal", "-shm"):     # restos de WAL apontariam para o banco antigo
        p = DB.with_name(DB.name + suf)
        if p.exists():
            p.unlink()
    with gzip.open(GZ, "rb") as g, open(DB, "wb") as f:
        shutil.copyfileobj(g, f)
    print(f"banco restaurado: {mb(DB):.1f} MB (snapshot de {stamp(GZ)})")
    return 0


def status() -> int:
    for p, rot in ((DB, "banco   "), (GZ, "snapshot")):
        print(f"  {rot} {'ausente' if not p.exists() else f'{mb(p):6.1f} MB  {stamp(p)}'}")
    if DB.exists() and GZ.exists():
        d = DB.stat().st_mtime - GZ.stat().st_mtime
        print("  -> " + ("banco mais novo que o snapshot (rode save)" if d > 60
                         else "snapshot mais novo que o banco (rode restore)" if d < -60
                         else "em sincronia"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["save", "restore", "status"])
    ap.add_argument("--force", action="store_true",
                    help="restore: sobrescreve mesmo se o banco local for mais novo")
    a = ap.parse_args()
    return {"save": save, "restore": lambda: restore(a.force), "status": status}[a.acao]()


if __name__ == "__main__":
    sys.exit(main())
