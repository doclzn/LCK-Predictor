# Auto Changelog — V20 → V21

## V21 Model Governance

- Criado lockbox SHA-256 para as cinco candidatas V19.
- Criado `experiment_registry_v21`.
- Criado `prospective_capture_ledger_v21` com feature/model hashes.
- Criado `governance_events_v21` para drift/violações.
- Criado gate de promoção pré-registrado e mais rígido.
- Corrigida a condição de incerteza do resumo legado V19: agora Log Loss **e** Brier precisam satisfazer o IC95%.
- Criado protocolo live V1 pré-registrado antes do primeiro treino elegível.
- Split live congelado em 65/15/20 cronológico por mapa.
- Criadas duas famílias live pré-especificadas.
- Criado trainer portátil em Python stdlib com weighting por mapa.
- Test set live passa a ser one-shot por protocol ID.
- Criado `VERIFICAR_GOVERNANCA.bat`.
- Criado `TREINAR_LIVE_QUANDO_PRONTO.bat`.
- Model page ganhou Prospective Lockbox, gate checks e Live Protocol status.
- Nenhum modelo novo foi promovido nesta versão.
