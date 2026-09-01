"""Sela o GOVERNANCE_LOCK_V21 sobre o congelamento V19 atual do banco.

O lock guarda a impressao digital (SHA-256) de cada candidata congelada. Quando
o congelamento e reescrito -- rodar run_validation_v19.py faz isso --, as
digitais deixam de bater, `v21_verified_v19_freezes()` nao devolve nenhuma
candidata e a captura prospectiva para em silencio. Este script e a unica forma
suportada de reselar.

RESELAR TEM CUSTO CIENTIFICO: cria uma pre-registro NOVA. As previsoes
prospectivas capturadas sob a epoca anterior deixam de valer como prova para as
candidatas reseladas, porque a definicao que elas testavam nao e mais esta. O
script mostra exatamente quanto historico sera invalidado e exige --confirm.

Uso:
    python3 scripts/seal_governance_v21.py             # dry-run, nao escreve
    python3 scripts/seal_governance_v21.py --confirm   # sela
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, shutil, sqlite3, sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lck_server_v21", ROOT / "server.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="escreve de fato; sem isso e dry-run")
    ap.add_argument("--note", default="", help="motivo da reselagem, gravado no lock e no log")
    args = ap.parse_args()

    m.v21_ensure_schema()
    now = datetime.now(timezone.utc).isoformat()

    rows = m.db_rows(
        "SELECT * FROM validation_freeze_v19 WHERE status='FROZEN_AWAITING_PROSPECTIVE' ORDER BY candidate"
    )
    if not rows:
        print("ERRO: nenhuma candidata FROZEN_AWAITING_PROSPECTIVE no banco. Rode o gate v19 antes.")
        return 1

    old_lock = m._v21_json_file(m.V21_LOCK_FILE, {})
    old_hashes = old_lock.get("candidate_definition_hashes") or {}

    candidates, new_hashes = [], {}
    for r in rows:
        obj, h = m._v21_db_freeze_definition(r)
        candidates.append(obj)
        new_hashes[r["candidate"]] = h

    frozen_ats = sorted({r["frozen_at"] for r in rows})

    print(f"Congelamento no banco : {len(rows)} candidatas, frozen_at {', '.join(frozen_ats)}")
    print(f"Lock atual            : created_at {old_lock.get('created_at')}, {len(old_hashes)} digitais\n")
    print("Candidata                 digital confere?")
    for name, h in sorted(new_hashes.items()):
        exp = old_hashes.get(name)
        state = "ja confere" if exp == h else ("AUSENTE do lock" if not exp else "DIFERE")
        print(f"  {name:<24} {state}")

    # Quanto historico prospectivo perde validade ao reselar.
    with m.db_connect() as con:
        lost = con.execute(
            """SELECT COUNT(*), COUNT(DISTINCT game_id), COUNT(DISTINCT series_key)
                 FROM prospective_predictions_v19
                WHERE model_frozen_at NOT IN (%s)"""
            % ",".join("?" * len(frozen_ats)),
            frozen_ats,
        ).fetchone()
    print(
        f"\nHistorico prospectivo de epocas anteriores: {lost[0]} previsoes, "
        f"{lost[1]} mapas, {lost[2]} series -- perde validade como prova."
    )

    if not args.confirm:
        print("\nDRY-RUN. Nada foi escrito. Repita com --confirm para selar.")
        return 0

    # Backup dos artefatos que serao reescritos.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in ("GOVERNANCE_LOCK_V21.json", "V19_FROZEN_CANDIDATES.json"):
        src = m.GOVERNANCE_DIR / name
        if src.exists():
            shutil.copy2(src, m.GOVERNANCE_DIR / f"{name}.backup-{stamp}")

    frozen_doc = m._v21_json_file(m.V21_FROZEN_FILE, {})
    frozen_doc.update(
        {
            "artifact": "V19_FROZEN_CANDIDATES",
            "schema_version": frozen_doc.get("schema_version", 1),
            "created_for_release": frozen_doc.get("created_for_release", "V21 Model Governance"),
            "sealed_at": now,
            "candidates": candidates,
        }
    )
    m.V21_FROZEN_FILE.write_text(
        json.dumps(frozen_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lock = {
        "release": old_lock.get("release", "V21 Model Governance"),
        "created_at": now,
        "artifacts": {
            name: _sha_file(m.GOVERNANCE_DIR / name)
            for name in (
                "V19_FROZEN_CANDIDATES.json",
                "PROMOTION_POLICY_V21.json",
                "LIVE_TRAINING_PROTOCOL_V21.json",
            )
        },
        "candidate_definition_hashes": new_hashes,
        "promotion_policy_hash": old_lock.get("promotion_policy_hash"),
        "live_protocol_hash": old_lock.get("live_protocol_hash"),
        "supersedes": {
            "created_at": old_lock.get("created_at"),
            "candidate_definition_hashes": old_hashes,
            "invalidated_prospective": {
                "predictions": lost[0], "games": lost[1], "series": lost[2]
            },
            "note": args.note,
        },
    }
    m.V21_LOCK_FILE.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # O proprio lock e o arquivo de candidatas estao registrados em
    # release_integrity_v21; sem atualizar isso, trocariamos um bloqueio por outro.
    with m.db_connect() as con:
        for rel in ("governance/GOVERNANCE_LOCK_V21.json", "governance/V19_FROZEN_CANDIDATES.json"):
            con.execute(
                "UPDATE release_integrity_v21 SET expected_sha256=? WHERE path=?",
                (_sha_file(ROOT / rel), rel),
            )
        con.commit()

    # experiment_registry_v21 nao se atualiza sozinho: sem isto, candidatas novas
    # ficam seladas mas nao registradas, e o relatorio de governanca segue
    # mostrando o conjunto antigo.
    with m.db_connect() as con:
        for r in rows:
            name = r["candidate"]
            con.execute(
                """INSERT INTO experiment_registry_v21
                   (experiment_id,layer,candidate,created_at,epoch_start,status,
                    definition_hash,gate_policy_hash,retrospective_verdict,note)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(experiment_id) DO UPDATE SET
                     status=excluded.status, definition_hash=excluded.definition_hash,
                     epoch_start=excluded.epoch_start, gate_policy_hash=excluded.gate_policy_hash,
                     retrospective_verdict=excluded.retrospective_verdict, note=excluded.note""",
                (f"v19:{name}:{r['frozen_at']}", "V19 prospective feature gate", name, now,
                 r["frozen_at"], "PRE_REGISTERED", new_hashes[name],
                 lock["promotion_policy_hash"], r["retrospective_verdict"],
                 args.note or None),
            )
        con.commit()

    m.v21_log_event(
        "INFO",
        "GOVERNANCE_RESEAL",
        {
            "sealed_at": now,
            "candidates": sorted(new_hashes),
            "frozen_at": frozen_ats,
            "superseded_lock_created_at": old_lock.get("created_at"),
            "invalidated_prospective_predictions": lost[0],
            "note": args.note,
        },
    )
    print(f"\nSelado. {len(new_hashes)} candidatas no lock, created_at {now}.")
    print(f"Backups dos artefatos: governance/*.backup-{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
