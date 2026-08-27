# Experimentforge — Présentation complète

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