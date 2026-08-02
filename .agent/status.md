# Status — ha-alert-plus
> MàJ : 2026-08-03

**État :** https://github.com/AntorFr/ha-alert-plus — public, Apache-2.0 comme HA
core. **v0.1.0 publiée**, manifest bumpé en 0.2.0 (reload, pas encore releasé).
CI verte : hassfest ✓, HACS 8/8 ✓, ruff ✓, pytest 28/28 ✓ sur HA 2026.8.0b3.

**Deux sources d'alertes qui cohabitent** : bloc `alert_plus:` en YAML (schéma
identique à `alert:` de core) **et** helpers créés par l'UI. Dans les deux cas
unique_id + registre → icône / pièce / nom éditables par le front. Le service
`alert_plus.reload` recharge le YAML sans restart, sans toucher aux alertes UI.
**Jamais encore chargée dans un vrai Home Assistant.**

**Décision (2026-08-03) : PAS de migration YAML → UI.** Demande explicite de
l'utilisateur : il veut gérer ses alertes « en yaml et/ou en graphique ». Le YAML
reste une source permanente, pas une passerelle. Un flux d'import avait été
commencé puis jeté.

**Contexte de conception :**
- Le `alert` de core est **gelé et déprécié** (issue home-assistant.io#42151) → une
  PR qui le patche serait refusée. La cible core est donc une **nouvelle intégration
  helper**, d'où le pattern `SchemaConfigFlowHandler` (calqué sur `threshold`).
- Art antérieur : [Alert2](https://github.com/redstone99/hass-alert2), riche mais sa
  config par alerte passe par un websocket maison + une carte Lovelace dédiée. Ici on
  ne veut que de l'UI native.
- Le domaine `alert_plus` est un nom de travail : à renommer si ça part en PR core.
- HA 2026.8 exige **Python ≥ 3.14.2** (et pytest-homeassistant-custom-component
  ≥ 0.13.317 suit) — la CI est sur 3.14, pas 3.13.

**Prochaines étapes :**
- [ ] Charger dans le vrai HA : une alerte YAML + une alerte UI (seule inconnue restante)
- [ ] Basculer les alertes de Home-AssistantConfig en renommant `alert:` → `alert_plus:`
      (`packages/integrations/automower.yaml`, `ico.yaml`, `packages/functions/battery_monitor.yaml`,
      `securtity_system.yaml`) — puis corriger les automatisations (`alert.x` → `binary_sensor.x`)
- [ ] Release GitHub v0.2.0 (manifest déjà bumpé) — v0.1.0 est publiée
- [ ] Release GitHub taguée v0.1.0 (= manifest.json.version)
- [ ] Condition par template (au-delà de entity_id + state) — la demande la plus courante
- [ ] Éventuel regroupement des 2 entités sous un device (pièce assignée en un seul point)
- [ ] Puis seulement : ouvrir une discussion architecture chez HA avant toute PR
