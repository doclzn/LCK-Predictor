# V19 → V20

## V19 Validation Lab

- 900 mapas reconstruídos cronologicamente.
- rolling-origin 2025 para tuning.
- 2026 explicitamente marcado como retrospectivo/não-pristine.
- pool exhaustion: pequena melhora, inconclusiva.
- remaining pool: pequena melhora, inconclusiva.
- flex isolado: rejeitado retrospectivamente.
- modelos congelados para gate prospectivo.
- captura tardia excluída do gate.
- bug de persistência `series_strategy_runs_v18` corrigido.

## V20 Live Validation

- dataset compacto live por minuto.
- completed-state snapshots excluídos.
- posterior labeling pelo vencedor Riot.
- readiness gate por mapas, times e checkpoints temporais.
- treinamento bloqueado antes da cobertura mínima.
- script de treino cronológico preparado.
- novo `COLETAR_LCK_LIVE.bat`.
- Match Page mostra checkpoint do dataset live.
