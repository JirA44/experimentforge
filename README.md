# ExperimentForge V1.07 Starter

ExperimentForge est un registre d'expériences reproductibles. Il fige les hypothèses et chaque version de protocole, conserve les observations brutes avec leur provenance, puis calcule côté serveur les agrégats, l'intervalle de confiance et un verdict conservateur.

La V1.07 ajoute un dossier de couverture des preuves de réplication sur **2 à 100 évaluations**. La requête accepte uniquement des `evaluation_ids` uniques. Le serveur impose l'ordre canonique (date, expérience, version, identifiant), recharge et revérifie expériences, protocoles, observations et SHA-256, puis régénère aussi chaque dossier d'écart au protocole.

Huit contrôles explicites couvrent les hashes, les groupes requis, le plan d'échantillonnage, les provenances source et sujet, l'actualité de l'instantané, l'adhérence au protocole et la disponibilité du résultat analytique. Le dossier restitue contrôles couverts, lacunes par évaluation, lacunes communes, ratios moyen/minimal et pire évaluation :

- `COMPLETE` : contrats compatibles, au moins deux expériences, aucun contrôle manquant ;
- `PARTIAL` : données analysables mais au moins une lacune documentaire ou un écart ;
- `INSUFFICIENT` : une seule expérience, résultat insuffisant ou preuve d'exécution insuffisante ;
- `INCOMPATIBLE` : hypothèses, groupes, directions, effets minimaux, métriques, unités ou méthodes analytiques différents.

Cette couverture est documentaire : elle ne certifie ni réplication, ni causalité, ni vérité universelle.

La V1.06 ajoute un dossier de robustesse de réplication sur **2 à 100 évaluations**. Le client transmet uniquement des `evaluation_ids` persistés et uniques. Le serveur impose l'ordre de référence par date de création, expérience, version de protocole et identifiant ; il recharge expériences, protocoles et observations, revérifie leurs hashes, recalcule effets, variances et intervalles à 95 %, et produit les dossiers d'adhérence correspondants.

Les contrats doivent conserver hypothèse, rôles/groupes, direction, effet minimum, métrique/unité et méthode analytique. Le dossier expose cohérence du signe, recouvrement avec la référence, effets soutenant ou contredisant la référence, transitions consécutives, moyenne, étendue, dispersion relative, écart-type, I², pire réplication et pire transition.

Seuils fixes : `DIVERGENT` si le signe devient incohérent, si une réplication contredit la référence ou ne recouvre pas son intervalle, si l'étendue relative atteint **20 %**, si I² atteint **50 %**, ou si un écart matériel au protocole existe. `ROBUST` exige des données complètes et qu'aucun de ces seuils ne soit franchi. `INSUFFICIENT` protège tout effet, intervalle, variance ou preuve d'exécution manquant ; `INCOMPATIBLE` signale des contrats analytiques différents.

Cette qualification porte uniquement sur les instantanés sélectionnés. Elle ne conclut ni causalité, ni validité externe, ni vérité universelle.

La V1.01 ajoute les rapports déterministes de réplication entre deux expériences distinctes. Le serveur vérifie lui-même la compatibilité des hypothèses, rôles de groupes, directions, effets minimaux, métriques, unités, méthodes de collecte, méthodes d'analyse et tailles minimales planifiées. Il recharge les observations immuables, recalcule les deux effets et leurs intervalles, puis produit un verdict qui ne peut jamais être fourni par le client :

- `REPLICATED` : l'original et la réplication soutiennent l'effet planifié et leurs intervalles à 95 % se recouvrent ;
- `NOT_REPLICATED` : l'original soutient l'effet, mais la réplication le rejette ou produit un effet soutenu d'amplitude incompatible ;
- `INSUFFICIENT` : l'original ne fournit pas d'effet positif à répliquer ou au moins une analyse reste insuffisante/inconclusive ;
- `INCOMPATIBLE` : les contrats expérimentaux ne sont pas assez comparables.

Le rapport fige les hashes des expériences, protocoles, instantanés d'observations et évaluations. Un rejeu sur les mêmes instantanés retourne le même rapport, tandis que l'audit reste append-only.

La V1.02 ajoute une synthèse déterministe de deux à cent évaluations provenant d'expériences distinctes. Le client transmet uniquement leurs identifiants : il ne peut fournir ni effet, ni variance, ni métrique, ni verdict. Le serveur recharge les observations append-only, vérifie le hash de chaque instantané, recalcule les effets, intervalles et variances, puis contrôle la compatibilité des hypothèses, rôles de groupes, directions, effets minimaux, métriques, unités et méthodes d'analyse.

L'agrégation emploie un modèle à effet fixe simple pondéré par l'inverse de la variance (plancher numérique documenté de `1e-12`). Elle restitue l'effet pondéré et son intervalle à 95 %, le pire effet et son intervalle, la cohérence directionnelle, le Q de Cochran et I² lorsque les données le permettent :

- `CONSISTENT` : contrats compatibles, données suffisantes, même direction et I² inférieur à 50 % ;
- `HETEROGENEOUS` : effets de directions opposées ou I² supérieur ou égal à 50 % ;
- `INSUFFICIENT` : moins de deux expériences distinctes ou au moins un effet/variance non calculable ;
- `INCOMPATIBLE` : les contrats analytiques diffèrent.

Chaque synthèse est immuable, hashée, auditée et idempotente, y compris si les identifiants sont rejoués dans un ordre différent. Une ancienne évaluation devenue non courante après l'ajout d'observations est refusée : il faut d'abord créer une nouvelle évaluation afin que le serveur ne mélange jamais des instantanés.

La V1.03 ajoute un diagnostic d'influence *leave-one-experiment-out*. Le client fournit uniquement le `synthesis_id` d'une synthèse V1.02 persistée. Le serveur recharge ses identifiants d'évaluations, revérifie tous les contrats, recalcule la synthèse complète, puis retire successivement chaque expérience et recalcule l'effet fixe, sa variance, son intervalle à 95 %, Q et I².

Pour chaque retrait, le rapport expose le delta d'effet groupé, son ratio par rapport au maximum entre l'effet complet, l'effet minimal déclaré et `1e-12`, ainsi que tout changement de cohérence directionnelle ou de qualification. Une expérience est influente si le ratio atteint **10 %**, si la cohérence directionnelle change, ou si la qualification `CONSISTENT/HETEROGENEOUS` change. L'expérience la plus influente privilégie d'abord ces bascules, puis le ratio maximal, avec départage déterministe par identifiant.

- `ROBUST` : au moins trois évaluations issues de trois expériences distinctes et aucun retrait ne franchit ces seuils ;
- `INFLUENTIAL` : au moins un retrait franchit un seuil fixe ;
- `INSUFFICIENT` : moins de trois évaluations/expériences ou effets non calculables ;
- `INCOMPATIBLE` : les contrats analytiques revalidés diffèrent.

Ces seuils sont des règles opérationnelles prudentes et fixes, pas une preuve statistique universelle. Le diagnostic est immuable, hashé, idempotent et inscrit dans l'audit append-only.

La V1.04 ajoute un dossier d'écart entre le protocole/préenregistrement et l'exécution persistée. La requête ne contient que `experiment_id` + `protocol_version`, un `evaluation_id`, ou les deux pour contrôler leur compatibilité. Le serveur recharge les hashes et observations, puis compare tailles d'échantillon, endpoint/unité, fenêtre temporelle, exclusions, méthode, graine, paramètres et données manquantes.

Seuils fixes : une taille utilisable inférieure à 80 % du plan est matérielle ; toute discordance d'endpoint/unité ou de méthode/paramètre est matérielle ; plus de 10 % d'observations hors fenêtre est matériel. Les exclusions et données manquantes utilisent les plafonds préenregistrés du protocole (10 % et 5 % par défaut). Une présence sous les plafonds ou une taille comprise entre 80 % et 100 % est mineure.

Qualifications serveur : `ADHERENT`, `MINOR_DEVIATIONS`, `MATERIAL_DEVIATIONS`, `INSUFFICIENT`, `INCOMPATIBLE`. Le client ne peut fournir ni résultat ni qualification. Le dossier est immuable, idempotent, hashé et audité, sans certification automatique.

La V1.05 ajoute un dossier de stabilité d'effet entre **2 et 50 évaluations uniques** d'une même expérience, chacune associée à une version distincte du protocole. La requête contient uniquement les `evaluation_ids`. Le serveur recharge expériences, protocoles et observations, recalcule leurs hashes, effets et intervalles à 95 %, puis ordonne les instantanés par numéro de version.

Les contrats doivent conserver hypothèse, métrique/unité, rôles et groupes, direction et méthode analytique. Pour chaque transition, le dossier expose le delta d'effet, le delta relatif, un éventuel changement de signe et le recouvrement des intervalles ; il indique aussi l'étendue relative et la pire transition. Le dénominateur du delta relatif est `max(|effet avant|, |effet après|, 1e-12)`. La qualification est :

- `SHIFTED` si le signe change, si les intervalles ne se recouvrent pas ou si le delta relatif atteint **10 %** ;
- `STABLE` si aucune transition ne franchit ces seuils fixes ;
- `INSUFFICIENT` si un effet/intervalle manque ou si les versions ne sont pas distinctes ;
- `INCOMPATIBLE` si les contrats ne correspondent pas ou les évaluations ne portent pas sur la même expérience.

Cette qualification est un diagnostic reproductible, jamais une certification ni une preuve de vérité.

Le client ne peut jamais envoyer un verdict. Les quatre verdicts possibles sont :

- `INSUFFICIENT` : au moins un groupe n'atteint pas la taille minimale planifiée ;
- `SUPPORTED` : l'intervalle calculé satisfait entièrement la direction et l'effet minimum planifiés ;
- `REJECTED` : l'intervalle se situe entièrement dans la direction opposée (ou dans la zone d'équivalence pour une hypothèse `different`) ;
- `INCONCLUSIVE` : les données sont suffisantes mais l'incertitude ne permet pas de conclure.

Une expérience, même reproductible, ne prouve jamais à elle seule une vérité universelle. La causalité, la validité externe et les biais du protocole doivent être examinés séparément.

## Démarrage sous Windows PowerShell

Guides complémentaires : [exemples d'utilisation](docs/USAGE_EXAMPLES.md) et [contribution](CONTRIBUTING.md).

```powershell
./scripts/Setup.ps1
./scripts/Start.ps1
```

Documentation interactive : `http://127.0.0.1:8016/docs`.

## Parcours minimal

1. `POST /v1/experiments` fige une hypothèse et le protocole V1 (groupes, graine, seuil, méthode et taille minimale).
2. `POST /v1/experiments/{id}/protocols` ajoute une nouvelle version immuable sans modifier les précédentes.
3. `POST /v1/experiments/{id}/observations` ajoute une observation brute. Une clé d'idempotence rejouée avec une autre charge est refusée.
4. `POST /v1/experiments/{id}/evaluations` calcule le résultat sur l'instantané courant. Le même instantané retourne exactement la même évaluation.
5. `POST /v1/replication-reports` compare deux expériences et fige un rapport de réplication calculé côté serveur.
6. `POST /v1/syntheses` reçoit uniquement `evaluation_ids` et calcule la synthèse multi-expériences.
7. `GET /v1/syntheses/{id}` restitue exactement ce snapshot immuable.
8. `POST /v1/influence-reports` reçoit uniquement un `synthesis_id` et recalcule le diagnostic leave-one-out.
9. `GET /v1/influence-reports/{id}` restitue exactement ce diagnostic immuable.
10. `POST /v1/deviation-reports` compare les artefacts persistés à partir de leurs seuls identifiants.
11. `GET /v1/deviation-reports/{id}` restitue exactement le dossier immuable.
12. `POST /v1/effect-stability-dossiers` reçoit uniquement 2 à 50 `evaluation_ids` et recalcule la stabilité entre versions.
13. `GET /v1/effect-stability-dossiers/{id}` restitue exactement ce dossier immuable.
14. `GET /v1/replication-reports/{id}` restitue exactement le snapshot de réplication.
15. `GET /v1/experiments/{id}/audit` expose le journal append-only.
16. `POST /v1/replication-robustness-dossiers` recalcule la robustesse depuis 2 à 100 évaluations.
17. `GET /v1/replication-robustness-dossiers/{id}` restitue le snapshot immuable.
18. `POST /v1/replication-evidence-coverage-dossiers` recalcule la couverture documentaire de 2 à 100 évaluations.
19. `GET /v1/replication-evidence-coverage-dossiers/{id}` restitue ce dossier immuable.

## Test

```powershell
./scripts/Test.ps1
```

Le moteur V1.07 emploie une différence de moyennes et un intervalle normal bilatéral à 95 % (`z=1,96`). Ses synthèses et dossiers sont des diagnostics reproductibles, pas une certification automatique. Ils ne démontrent ni causalité, ni vérité universelle, ni validité externe.
