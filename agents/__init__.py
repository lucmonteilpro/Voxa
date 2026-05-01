"""Voxa — Multi-agents architecture.

Sub-modules:
- base : classe abstraite Agent (logging DB + gestion erreurs)
- gap_analyzer : exploite sources Perplexity pour identifier angles morts
- crawlability_agent : audit technique GEO du site cible (accès des bots IA)
- content_creator : génère contenu GEO + JSON-LD (à venir)
- quality_controller : re-crawle pour valider l'amélioration (à venir)
- orchestrator : chaîne les agents en boucle (à venir)
"""