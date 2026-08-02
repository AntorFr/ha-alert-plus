# Status — ha-alert-plus
> MàJ : 2026-08-03

**État :** https://github.com/AntorFr/ha-alert-plus — public, Apache-2.0 comme HA
core. v0.1.0 → v0.3.0 publiées ; **v0.4.0 (option `icon:`) pas encore releasée**.
CI verte : hassfest ✓, HACS 8/8 ✓, ruff ✓, pytest 30/30 ✓ sur HA 2026.8.0b3.
**Jamais encore chargée dans un vrai Home Assistant.**

**Pivot v0.3.0 (2026-08-03) — décision structurante de l'utilisateur :**
le but est de **remplacer le domaine `alert` de core**, donc on doit être
*exactement* core + nos améliorations. Les entités vivent dans le domaine
**`alert`** (via `EntityComponent(LOGGER, "alert", hass)`), pas en
`binary_sensor` + `switch`. `alert.fire_alert` reste `alert.fire_alert`, états
`idle`/`on`/`off`, services `alert.turn_on`/`turn_off`/`toggle`. Le switch
d'acquittement a disparu (redondant avec `alert.turn_off`).

**Nos ajouts sur core :** unique_id (→ registre → icône/pièce/nom dans l'UI),
création graphique (helper), `alert_plus.reload`, acquittement qui survit au
redémarrage, déclenchement si la condition est déjà vraie au démarrage, entités
`notify`, option `icon:` en YAML (défaut surchargeable par le registre —
`entity.py:1144` de core : l'icône du registre gagne).

**Pièges vérifiés :**
- Poser un `entity_id` d'un autre domaine que sa plateforme est **déprécié et
  casse en HA 2027.5** → seul le vrai `EntityComponent` sur `alert` marche.
- `Platform.ALERT` n'existe pas ; le chemin config entry passe par
  `EntityComponent.async_setup_entry` + un module de plateforme `alert.py`,
  ce qui lie l'entité à sa config entry dans le registre.
- ⚠️ Aucun bloc `alert:` ne doit subsister, sinon core alert se charge et les
  deux se disputent le domaine et ses services.
- HA 2026.8 exige Python ≥ 3.14.2 — la CI est sur 3.14.

**Contexte :** `alert` de core est gelé/déprécié (home-assistant.io#42151). Art
antérieur : [Alert2](https://github.com/redstone99/hass-alert2), mais config par
websocket maison + carte Lovelace ; ici on ne veut que de l'UI native.

**Prochaines étapes :**
- [ ] Release GitHub v0.4.0 (manifest bumpé)
- [ ] Charger dans le vrai HA (seule inconnue restante)
- [ ] Renommer `alert:` → `alert_plus:` dans Home-AssistantConfig
      (`packages/areas/piscine.yaml`, `packages/functions/{battery_monitor,securtity_system}.yaml`,
      `packages/integrations/{automower,ico}.yaml`) — 12 alertes, entity_id inchangés.
      ⚠️ `alert.swiming_pool` est déclarée dans deux fichiers : doublon à trancher.
- [ ] Condition par template (au-delà de entity_id + state)
- [ ] Puis : discussion architecture chez HA avant toute PR
