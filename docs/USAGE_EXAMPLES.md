# Utilisations d'ExperimentForge

## Pour quelles utilisations ?

- figer un protocole et ses versions avant collecte ;
- conserver des observations brutes avec provenance et idempotence ;
- évaluer une expérience sans recevoir de verdict du client ;
- comparer une réplication à l'expérience originale ;
- synthétiser plusieurs expériences compatibles et mesurer l'influence de chacune ;
- auditer les écarts entre préenregistrement et exécution.
- suivre la stabilité d'un effet lorsque le protocole évolue, sans accepter de résultat client.
- comparer prudemment la robustesse de plusieurs réplications compatibles.
- contrôler la couverture documentaire des preuves et protocoles de réplication.

## Exemple

Un test A/B prévoit deux groupes de 100 observations, un endpoint et une fenêtre de collecte. Après ingestion, l'évaluation recalcule effet et intervalle. Le dossier d'écart signale une collecte hors fenêtre, une taille sous le plan ou un changement de méthode. `ADHERENT` décrit seulement les artefacts contrôlés : ce n'est pas une preuve de causalité ni de validité externe.

## Dossier de stabilité V1.05

Créer une évaluation pour chaque version de protocole, puis transmettre uniquement leurs identifiants :

```powershell
$body = @{
  evaluation_ids = @("evaluation-v1", "evaluation-v2", "evaluation-v3")
} | ConvertTo-Json

$dossier = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8016/v1/effect-stability-dossiers" `
  -ContentType "application/json" `
  -Body $body

Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8016/v1/effect-stability-dossiers/$($dossier.id)"
```

`SHIFTED` signifie seulement qu'au moins une transition franchit la règle fixe (changement de signe, intervalles non recouvrants ou delta relatif d'au moins 10 %). Cela ne certifie ni l'expérience ni la vérité de son hypothèse.

Installation et lancement sous PowerShell :

```powershell
./scripts/Setup.ps1
./scripts/Start.ps1
```

La documentation API est disponible sur `http://127.0.0.1:8016/docs`.

## Dossier de robustesse V1.06

```powershell
$body = @{
  evaluation_ids = @("evaluation-originale", "replication-a", "replication-b")
} | ConvertTo-Json

$robustesse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8016/v1/replication-robustness-dossiers" `
  -ContentType "application/json" `
  -Body $body

$robustesse.qualification
$robustesse.worst_replication
$robustesse.transitions
```

Le corps n'accepte aucun effet, intervalle, seuil ou résultat client. `ROBUST` décrit seulement la cohérence de ces instantanés selon les règles fixes ; ce n'est pas une preuve de causalité ou de vérité universelle.

## Couverture des preuves de réplication V1.07

```powershell
$body = @{
  evaluation_ids = @("evaluation-originale", "replication-a", "replication-b")
} | ConvertTo-Json

$couverture = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8016/v1/replication-evidence-coverage-dossiers" `
  -ContentType "application/json" `
  -Body $body

$couverture.qualification
$couverture.evaluations | Select-Object evaluation_id, coverage_ratio, gap_codes
$couverture.worst_evaluation
```

Le serveur recalcule les huit contrôles depuis les artefacts persistés. `COMPLETE` signifie seulement qu'aucune lacune documentaire définie par cette méthode n'a été trouvée ; ce n'est pas une certification scientifique.
