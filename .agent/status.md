# Status — ha-alert-plus
> MàJ : 2026-08-02

**État :** v0.1.0 poussée sur https://github.com/AntorFr/ha-alert-plus (public,
Apache-2.0 comme HA core). **CI entièrement verte** : hassfest ✓, HACS 8/8 ✓,
ruff ✓, pytest 18/18 ✓ sur HA 2026.8.0b3. Intégration helper `alert_plus` :
1 config entry = 1 alerte, donc unique_id + registre + config par le front
(nom, icône, pièce) — ce que le `alert` de core ne permet pas.
**Jamais encore chargée dans un vrai Home Assistant.**

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
- [ ] Charger dans le vrai HA et créer une alerte via l'UI (seule inconnue restante)
- [ ] Migrer les alertes YAML de Home-AssistantConfig (`packages/integrations/automower.yaml`,
      `ico.yaml`, `packages/functions/battery_monitor.yaml`, `securtity_system.yaml`)
- [ ] Release GitHub taguée v0.1.0 (= manifest.json.version)
- [ ] Condition par template (au-delà de entity_id + state) — la demande la plus courante
- [ ] Éventuel regroupement des 2 entités sous un device (pièce assignée en un seul point)
- [ ] Puis seulement : ouvrir une discussion architecture chez HA avant toute PR
