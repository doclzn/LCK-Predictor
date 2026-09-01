"""Sequencia de confianca (anytime-valid) para o gate prospectivo.

PROBLEMA QUE RESOLVE
Um intervalo de confianca comum vale para UMA olhada. Conferir a cada rodada e
promover quando o intervalo cruza zero infla o falso positivo: medido nos dados
da LCK 2026, uma candidata sem vantagem nenhuma passava de 1,0% para 2,8% de
aprovacao (2,8x) com apenas 14 conferidas. Com monitoramento indefinido ao longo
de temporadas, essa probabilidade tende a 1.

Por isso o V21 usava amostra fixa (100 mapas / 40 series): remedio tosco para um
problema real. Este modulo troca o remedio -- a sequencia de confianca vale em
TODOS os instantes simultaneamente, entao da para olhar quando e quantas vezes
quiser, e parar quando quiser, sem inflar nada.

METODO
Mistura normal de Robbins (Howard et al. 2021, "Time-uniform Chernoff bounds"),
aplicada em nivel de SERIE -- mapas da mesma serie nao sao observacoes
independentes (mesmos times, mesmo dia, muitas vezes os mesmos campeoes).
A unidade estatistica e a media por serie da diferenca de log-loss por mapa.

O parametro sub-gaussiano e estimado dos proprios dados (plug-in). Isso torna a
garantia aproximada, nao exata, entao a cobertura e verificada empiricamente por
simulacao sob a hipotese nula em tests/test_anytime_gate_v22.py. Nao confie na
formula sem esse teste passando.
"""
from __future__ import annotations
import math
import numpy as np

# Tamanho em que a sequencia e "afinada" para ser mais apertada. Escolhido como
# ~60 series (cerca de um terco de temporada da LCK); a validade vale em qualquer
# t, isto so desloca onde ela e mais eficiente.
RHO_TUNED_AT = 60


def _rho(t_star=RHO_TUNED_AT):
    return 1.0 / max(1, t_star)


def cs_radius(t, sigma, alpha=0.05, t_star=RHO_TUNED_AT):
    """Raio da sequencia de confianca para a media de t observacoes.

    Mistura normal: o raio decresce como ~sqrt(log(t)/t) em vez de sqrt(1/t).
    Esse log a mais e exatamente o preco de poder olhar sempre.
    """
    if t < 1 or sigma <= 0:
        return float("inf")
    rho = _rho(t_star)
    inner = (t * rho + 1.0) / (t * t * rho)
    return float(sigma * math.sqrt(2.0 * inner * math.log(math.sqrt(t * rho + 1.0) / alpha)))


def series_units(deltas, series_keys):
    """Agrega diferenca por mapa em uma observacao por serie.

    Retorna (medias_por_serie, mapas_por_serie) na ordem de primeira aparicao --
    a ordem cronologica de chegada, que e o que a sequencia consome.
    """
    order, groups = [], {}
    for d, s in zip(deltas, series_keys):
        if s not in groups:
            groups[s] = []
            order.append(s)
        groups[s].append(float(d))
    means = np.array([np.mean(groups[s]) for s in order])
    sizes = np.array([len(groups[s]) for s in order])
    return means, sizes


def confidence_sequence(deltas, series_keys, alpha=0.05, t_star=RHO_TUNED_AT):
    """Estado da sequencia apos cada serie observada.

    `deltas` e a diferenca de log-loss POR MAPA (candidata - core); negativo
    significa candidata melhor.
    """
    means, sizes = series_units(deltas, series_keys)
    out = []
    for t in range(1, len(means) + 1):
        window = means[:t]
        est = float(window.mean())
        # Desvio amostral das medias por serie; com t<2 nao ha estimativa.
        sigma = float(window.std(ddof=1)) if t >= 2 else float("nan")
        r = cs_radius(t, sigma, alpha, t_star) if t >= 2 and sigma > 0 else float("inf")
        out.append({
            "series": t,
            "maps": int(sizes[:t].sum()),
            "estimate": est,
            "lower": est - r if math.isfinite(r) else float("-inf"),
            "upper": est + r if math.isfinite(r) else float("inf"),
        })
    return out


def decide(state, practical_threshold):
    """Decisao a partir de um ponto da sequencia.

    BETTER  -- toda a faixa plausivel esta abaixo do limiar pratico: promover.
    WORSE   -- toda a faixa esta acima de zero: a candidata piora, descartar.
    WAITING -- a faixa ainda cobre as duas hipoteses.

    Nao existe "inconclusivo por ter acabado a amostra": a sequencia so espera.
    """
    if state["upper"] <= practical_threshold:
        return "BETTER"
    if state["lower"] >= 0.0:
        return "WORSE"
    return "WAITING"
