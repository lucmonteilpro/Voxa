"""
Voxa — Classe abstraite Agent
==============================
Base de tous les agents Voxa (Gap Analyzer, SEO, Content Creator, QC,
Orchestrateur).

Responsabilités prises en charge automatiquement par cette classe :
- Logging dans la table `agent_runs` (status, durée, input/output JSON)
- Gestion des erreurs (catch + log error_msg + status='failed')
- Chaînage parent_run_id (pour orchestrateur)
- Numérotation iteration (pour boucles)

Les sous-classes n'ont qu'à implémenter UNE seule méthode : `execute(input)`.
Le reste (logging, timing, gestion d'erreur) est géré.

Architecture standard d'une sous-classe :

    class MonAgent(Agent):
        name = "mon_agent"

        def execute(self, input_data: dict) -> dict:
            # Faire le travail métier
            # Lire la DB Voxa, appeler Claude API, fetcher des URLs, etc.
            # Retourner un dict sérialisable JSON
            return {"resultats": [...], "stats": {...}}

Usage :

    agent = MonAgent(slug="betclic", language="fr")
    output = agent.run({"param": "value"})
    # → log automatique en DB, retour de l'output
"""

from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent.parent.resolve()


class Agent(ABC):
    """Classe abstraite que tous les agents Voxa doivent étendre.

    Sous-classe DOIT définir :
        - `name` : identifiant string de l'agent (ex: "gap_analyzer")
        - `execute(input_data: dict) -> dict` : la logique métier

    Sous-classe PEUT override :
        - `validate_input(input_data: dict)` : pre-checks avant execute
        - `validate_output(output: dict)` : post-checks après execute
    """

    # À override dans chaque sous-classe
    name: str = "abstract_agent"

    def __init__(self,
                 slug: str,
                 language: Optional[str] = None,
                 parent_run_id: Optional[int] = None,
                 iteration: int = 1,
                 db_path: Optional[Path] = None):
        """
        Args:
            slug: identifiant client (ex: 'betclic', 'psg')
            language: marché ('fr', 'pt', 'fr-ci', 'pl') — None si multi-marchés
            parent_run_id: id d'un run parent (pour chaînage par orchestrateur)
            iteration: numéro d'itération (pour boucle orchestrateur)
            db_path: override du chemin DB (utile pour tests)
        """
        self.slug = slug
        self.language = language
        self.parent_run_id = parent_run_id
        self.iteration = iteration

        # Résolution du chemin DB
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = self._resolve_db_path(slug)

        # État interne (renseigné par run())
        self.run_id: Optional[int] = None
        self._started_at: Optional[datetime] = None

    # ─────────────────────────────────────────────
    # API publique : les sous-classes utilisent ces méthodes
    # ─────────────────────────────────────────────
    def run(self, input_data: Optional[dict] = None) -> dict:
        """Exécute l'agent en gérant logging + erreurs.

        Workflow :
            1. Insert ligne agent_runs avec status='running'
            2. validate_input(input_data) — peut lever ValueError
            3. execute(input_data) — la logique métier
            4. validate_output(output) — peut lever ValueError
            5. Update agent_runs avec status='success' + output_json + duration

        Si exception à n'importe quelle étape :
            → Update agent_runs avec status='failed' + error_msg
            → Re-raise pour visibilité côté caller

        Returns:
            output dict produit par execute()
        """
        input_data = input_data or {}

        # 1) Log de démarrage
        self._log_start(input_data)

        try:
            # 2) Validation entrée
            self.validate_input(input_data)

            # 3) Exécution métier (la SEULE chose que les sous-classes implémentent)
            output = self.execute(input_data)

            # Sécurité : output doit être un dict sérialisable JSON
            if not isinstance(output, dict):
                raise TypeError(
                    f"{self.name}.execute() doit retourner un dict, "
                    f"pas {type(output).__name__}"
                )

            # 4) Validation sortie
            self.validate_output(output)

            # 5) Log de succès
            self._log_success(output)

            return output

        except Exception as e:
            self._log_failure(e)
            raise

    @abstractmethod
    def execute(self, input_data: dict) -> dict:
        """À implémenter dans chaque sous-classe.

        Doit retourner un dict sérialisable JSON.
        Peut accéder à self.slug, self.language, self.db_path.
        """
        ...

    # ─────────────────────────────────────────────
    # Hooks optionnels (override possible)
    # ─────────────────────────────────────────────
    def validate_input(self, input_data: dict) -> None:
        """Pre-checks. Override pour valider les paramètres d'entrée."""
        pass

    def validate_output(self, output: dict) -> None:
        """Post-checks. Override pour valider la cohérence de l'output."""
        pass

    # ─────────────────────────────────────────────
    # Helpers DB pour les sous-classes (raccourcis pratiques)
    # ─────────────────────────────────────────────
    def db_connect(self) -> sqlite3.Connection:
        """Retourne une connexion à la DB Voxa du slug.

        La connexion a row_factory = sqlite3.Row pour accès par nom de colonne.
        À fermer après usage (ou utiliser dans un with block).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_last_run(self, agent_name: str) -> Optional[dict]:
        """Récupère le dernier run réussi d'un agent donné pour ce slug.

        Utile pour les agents qui veulent réutiliser le résultat d'un agent
        précédent (ex: Content Creator lit le dernier output du Gap Analyzer).

        Returns:
            dict avec keys (id, output_json parsé, finished_at) ou None
        """
        conn = self.db_connect()
        try:
            row = conn.execute("""
                SELECT id, output_json, finished_at
                FROM agent_runs
                WHERE slug = ? AND agent_name = ? AND status = 'success'
                ORDER BY finished_at DESC
                LIMIT 1
            """, (self.slug, agent_name)).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "output": json.loads(row["output_json"]) if row["output_json"] else {},
                "finished_at": row["finished_at"],
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────
    # Internal : gestion de la table agent_runs
    # ─────────────────────────────────────────────
    def _resolve_db_path(self, slug: str) -> Path:
        """Trouve le chemin DB pour le slug (réutilise voxa_db si dispo)."""
        try:
            import voxa_db as vdb
            cfg = vdb.CLIENTS_CONFIG.get(slug)
            if cfg:
                db = cfg["db"] if isinstance(cfg["db"], Path) else Path(cfg["db"])
                if db.exists():
                    return db
        except Exception:
            pass
        # Fallback
        candidate = BASE_DIR / f"voxa_{slug}.db"
        if not candidate.exists() and slug == "psg":
            candidate = BASE_DIR / "voxa.db"
        if not candidate.exists():
            raise FileNotFoundError(f"DB introuvable pour slug='{slug}'")
        return candidate

    def _log_start(self, input_data: dict) -> None:
        """Insert une ligne dans agent_runs avec status='running'.

        Stocke self.run_id pour les updates ultérieurs.
        """
        self._started_at = datetime.now()

        conn = self.db_connect()
        try:
            cursor = conn.execute("""
                INSERT INTO agent_runs
                (agent_name, slug, language, status, input_json,
                 started_at, iteration, parent_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.name,
                self.slug,
                self.language,
                "running",
                json.dumps(input_data, ensure_ascii=False),
                self._started_at.isoformat(),
                self.iteration,
                self.parent_run_id,
            ))
            self.run_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

    def _log_success(self, output: dict) -> None:
        """Update la ligne agent_runs avec succès + output."""
        finished_at = datetime.now()
        duration_ms = int((finished_at - self._started_at).total_seconds() * 1000)

        conn = self.db_connect()
        try:
            conn.execute("""
                UPDATE agent_runs
                SET status = 'success',
                    output_json = ?,
                    finished_at = ?,
                    duration_ms = ?
                WHERE id = ?
            """, (
                json.dumps(output, ensure_ascii=False),
                finished_at.isoformat(),
                duration_ms,
                self.run_id,
            ))
            conn.commit()
        finally:
            conn.close()

    def _log_failure(self, exc: Exception) -> None:
        """Update la ligne agent_runs avec failure + message d'erreur."""
        finished_at = datetime.now()
        duration_ms = int((finished_at - self._started_at).total_seconds() * 1000) \
            if self._started_at else 0

        # On garde le message d'erreur tronqué pour éviter de bloater la DB
        error_msg = f"{type(exc).__name__}: {exc}"[:1000]

        conn = self.db_connect()
        try:
            conn.execute("""
                UPDATE agent_runs
                SET status = 'failed',
                    error_msg = ?,
                    finished_at = ?,
                    duration_ms = ?
                WHERE id = ?
            """, (
                error_msg,
                finished_at.isoformat(),
                duration_ms,
                self.run_id,
            ))
            conn.commit()
        finally:
            conn.close()