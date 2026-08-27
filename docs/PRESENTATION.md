# ExperimentForge — Présentation complète

## Présentation
experimentforge est un registre immuable, hashé (SHA-256), auditable et rejouable.

## À quoi ça sert ? (problèmes réglés)
- **Expérience non reproductible** → résolu par un dossier déterministe, ordre-indépendant
- **Protocole changé sans version** → résolu par un dossier déterministe, ordre-indépendant
- **Résultat annoncé sans preuve de réplication** → résolu par un dossier déterministe, ordre-indépendant

## Cas d'utilisation concrets
- Labo R&D: rejouer une expérience à l'identique 6 mois plus tard
- ML: prouver que le modèle X a bien été répliqué sur 3 seeds
- Essai clinique: chaînage protocole -> run -> résultat

## Exemples d'utilisation (API)
```bash
curl -X POST http://localhost:8000/v1/replication-dossiers -d '{"experiment_ids": [...] }'
# → { "qualification": "COMPLETE|GAPPED|INSUFFICIENT|INCOMPATIBLE", "coverage_ratio": 0.94, ... }
```

## À quoi ça pourrait servir (futur / possibilités)
- Reproductibilité scientifique automatique
- Méta-analyse vérifiable
- Certification labo ISO 17025

## Pour qui ?
Devs, auditeurs, ops, chercheurs — qui ont besoin d'une preuve opposable, pas d'un verdict déclaratif.

## Problèmes réglés (détaillés)
- **Experimentforge** → - Preuve / dossier / trace non opposable → résolu par dossier immuable et hash SHA-256
- **Experimentforge** → - Verdict déclaratif sans justification → le dossier expose obligations, fournisseurs et ratios
- **Experimentforge** → - Chaînage caché ou lacune invisible → serveur recharge et recalcule indépendamment du client
- **Experimentforge** → - Tiers qui ne peut pas relancer → le dossier est public et rejouable sans clé client

## Exemples d'utilisation (scénarios réels)
- **Labo R&D : réplication 6 mois après** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **ML : 3 seeds prouvés** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **Essai clinique : protocole→run→résultat** → le dossier sert de preuve technique (pas d'autorité déclarative)


