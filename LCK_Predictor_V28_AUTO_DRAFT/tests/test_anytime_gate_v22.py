"""A garantia da sequencia de confianca e aproximada (o parametro sub-gaussiano
e estimado dos dados), entao ela precisa ser verificada empiricamente -- nao
basta a formula estar certa. Estes testes usam as proprias series da LCK."""
from pathlib import Path
import importlib.util, sqlite3
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "anytime_gate_v22", ROOT / "scripts" / "anytime_gate_v22.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def gate():
    return _mod()


@pytest.fixture(scope="module")
def lck_series():
    """Diferencas por mapa reais, agrupadas por serie, da avaliacao de 2026."""
    con = sqlite3.connect(ROOT / "data" / "lck_data_v1.sqlite")
    rows = con.execute(
        "SELECT series_key, elo_diff FROM validation_dataset_v19 "
        "WHERE year=2026 AND series_key IS NOT NULL ORDER BY date, gameid").fetchall()
    con.close()
    return [r[0] for r in rows]


def test_radius_shrinks_with_more_data(gate):
    r = [gate.cs_radius(t, sigma=0.05) for t in (5, 20, 80, 320)]
    assert all(a > b for a, b in zip(r, r[1:])), r
    # E nunca chega a zero cedo demais: com poucas series a faixa tem de ser larga.
    assert gate.cs_radius(2, sigma=0.05) > 0.05


def test_decide_states(gate):
    better = {"lower": -0.02, "upper": -0.006}
    worse  = {"lower": +0.001, "upper": +0.02}
    wait   = {"lower": -0.01, "upper": +0.01}
    assert gate.decide(better, -0.005) == "BETTER"
    assert gate.decide(worse,  -0.005) == "WORSE"
    assert gate.decide(wait,   -0.005) == "WAITING"
    # Faixa que exclui zero mas nao alcanca o limiar pratico nao promove.
    assert gate.decide({"lower": -0.004, "upper": -0.001}, -0.005) == "WAITING"


def test_early_checkpoints_are_honest(gate, lck_series):
    """Conferir em 10/15/20 mapas e permitido e nao custa nada -- mas nesse
    tamanho a faixa tem de ser larga demais para concluir qualquer coisa."""
    rng = np.random.default_rng(3)
    deltas = rng.normal(-0.004, 0.35, size=len(lck_series))
    st = gate.confidence_sequence(deltas, lck_series)
    for target in (10, 15, 20):
        s = next(x for x in st if x["maps"] >= target)
        assert gate.decide(s, -0.005) == "WAITING", (target, s)
        assert s["upper"] - s["lower"] > 0.05, s


def test_false_positive_under_continuous_monitoring(gate, lck_series):
    """O teste que importa: sob a hipotese nula, monitorando em TODAS as series,
    a faixa pode excluir o zero em no maximo ~5% das repeticoes.

    Um IC comum conferido repetidamente falha aqui -- foi medido em 2,8% com
    apenas 14 conferidas, e cresce sem limite com mais olhadas."""
    rng = np.random.default_rng(11)
    keys = np.array(lck_series)
    uniq = np.unique(keys)
    idx = {s: np.flatnonzero(keys == s) for s in uniq}
    RUNS = 150
    hits = 0
    for _ in range(RUNS):
        deltas = rng.normal(0.0, 0.35, size=len(keys))   # efeito verdadeiro = 0
        order = rng.permutation(uniq)
        ix = np.concatenate([idx[s] for s in order])
        st = gate.confidence_sequence(deltas[ix], keys[ix])
        hits += any(s["upper"] <= 0 for s in st)
    rate = hits / RUNS
    assert rate <= 0.08, f"falso positivo {rate:.1%} acima do tolerado"
