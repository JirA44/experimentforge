# Changelog

## 1.0.7 — ExperimentForge V1.07

- ajout des dossiers de couverture des preuves de réplication sur 2..100 évaluations ;
- ordre canonique serveur, rechargement et vérification des hashes, protocoles, observations et dossiers d'écart ;
- huit contrôles de couverture, lacunes par évaluation/communes, ratios moyen/minimal et pire évaluation ;
- qualifications prudentes `COMPLETE`, `PARTIAL`, `INSUFFICIENT`, `INCOMPATIBLE` ;
- snapshots immuables/idempotents, SHA-256, audit append-only, SQLite/PostgreSQL et OpenAPI exact.

## 1.0.6 — ExperimentForge V1.06

- ajout des dossiers de robustesse de réplication fondés sur 2..100 évaluations ;
- ordre canonique serveur et recalcul des effets, intervalles, hashes et adhérence ;
- cohérence du signe, recouvrements, soutiens/contradictions et transitions ;
- dispersion, étendue relative, I², pire réplication et pire transition ;
- seuils fixes de 20 % et 50 %, qualifications `ROBUST`, `DIVERGENT`, `INSUFFICIENT`, `INCOMPATIBLE` ;
- snapshots immuables/idempotents, audit, SQLite/PostgreSQL et OpenAPI statique égal au runtime.

## 1.0.5 — ExperimentForge V1.05

- ajout des dossiers immuables de stabilité d'effet entre versions d'un protocole ;
- entrée limitée à 2..50 `evaluation_ids` uniques, sans résultat ni qualification client ;
- rechargement et contrôle serveur des expériences, protocoles, observations et hashes ;
- effets, intervalles, deltas, signes, recouvrements, étendue relative et pire transition recalculés ;
- seuil fixe de 10 % et qualifications prudentes `STABLE`, `SHIFTED`, `INSUFFICIENT`, `INCOMPATIBLE` ;
- snapshots SHA-256 idempotents, audit append-only, API et persistance SQLite/PostgreSQL.

## 1.0.4 — ExperimentForge V1.04

- ajout des dossiers immuables d'écart au protocole/préenregistrement ;
- entrée limitée aux identifiants persistés d'expérience, protocole et évaluation ;
- comparaison serveur des échantillons, endpoints, fenêtres, exclusions, méthodes, paramètres et données manquantes ;
- seuils fixes documentés et qualifications prudentes `ADHERENT`, `MINOR_DEVIATIONS`, `MATERIAL_DEVIATIONS`, `INSUFFICIENT`, `INCOMPATIBLE` ;
- hashes, idempotence, audit append-only, API et persistance SQLite/PostgreSQL.

## 1.0.3 — ExperimentForge V1.03

- ajout des rapports d'influence leave-one-experiment-out fondés sur un `synthesis_id` persisté ;
- recalcul intégral côté serveur de la synthèse complète et de chaque retrait ;
- effet, variance, intervalle, Q, I², delta, cohérence et qualification pour chaque cas ;
- seuil fixe de delta relatif à 10 %, plus bascules de direction ou qualification ;
- verdicts prudents `ROBUST`, `INFLUENTIAL`, `INSUFFICIENT` et `INCOMPATIBLE` ;
- snapshots immuables, idempotents, hashés et audités ;
- endpoints et persistance SQLite/PostgreSQL associés.

## 1.0.2 — ExperimentForge V1.02

- ajout des synthèses immuables et idempotentes de plusieurs expériences ;
- entrée limitée aux identifiants d'évaluations, sans effet, métrique ou verdict client ;
- recalcul serveur des effets, variances et intervalles depuis les observations ;
- contrôle de compatibilité des hypothèses, rôles, directions, métriques et unités ;
- agrégation fixe inverse-variance, pire effet, Q de Cochran et I² ;
- qualifications prudentes `CONSISTENT`, `HETEROGENEOUS`, `INSUFFICIENT` et `INCOMPATIBLE` ;
- endpoints `/v1/syntheses`, persistance SQLite/PostgreSQL et audit hashé.

## 1.0.1 — ExperimentForge V1.01

- ajout des rapports immuables et idempotents de réplication ;
- contrôle serveur de compatibilité des hypothèses, métriques, directions et protocoles ;
- recalcul des effets et intervalles depuis les observations append-only ;
- verdicts prudents `REPLICATED`, `NOT_REPLICATED`, `INSUFFICIENT` et `INCOMPATIBLE` ;
- hashes des snapshots et événement d'audit chaîné ;
- nouveaux endpoints `/info` et `/v1/replication-reports`.

## 1.0.0 — ExperimentForge V1.00

- registre initial d'expériences, protocoles, observations et évaluations immuables.
