# Status — ha-alert-plus
> MàJ : 2026-08-02

**État :** v0.1.0 fonctionnelle et testée en local (18 tests verts, ruff clean sur
HA 2026.8.0b3). Intégration helper `alert_plus` : 1 config entry = 1 alerte, donc
unique_id + registre + config par le front (nom, icône, pièce) — ce que le `alert`
de core ne permet pas. Pas encore poussée sur GitHub, ni testée dans un vrai HA.

**Contexte de conception :**
- Le `alert` de core est **gelé et déprécié** (issue home-assistant.io#42151) → une
  PR qui le patche serait refusée. La cible core est donc une **nouvelle intégration
  helper**, d'où le pattern `SchemaConfigFlowHandler` (calqué sur `threshold`).
- Art antérieur : [Alert2](https://github.com/redstone99/hass-alert2), riche mais sa
  config par alerte passe par un websocket maison + une carte Lovelace dédiée. Ici on
  ne veut que de l'UI native.
- Le domaine `alert_plus` est un nom de travail : à renommer si ça part en PR core.

**Prochaines étapes :**
- [ ] Créer le repo GitHub public `ha-alert-plus` et pousser (CI hassfest/HACS à voir tourner)
- [ ] Tester dans le vrai HA, et migrer les alertes YAML existantes de Home-AssistantConfig
      (`packages/integrations/automower.yaml`, `ico.yaml`, `packages/functions/*`)
- [ ] Release GitHub taguée v0.1.0 (= manifest.json.version)
- [ ] Condition par template (au-delà de entity_id + state) — la demande la plus courante
- [ ] Éventuel regroupement des 2 entités sous un device (pièce assignée en un seul point)
- [ ] Puis seulement : ouvrir une discussion architecture chez HA avant toute PR
