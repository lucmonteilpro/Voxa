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
        """Trouve (ou crée) le chemin DB pour le slug.

        Stratégie en cascade :
          1. voxa_db.CLIENTS_CONFIG[slug] si dispo
          2. voxa_{slug}.db à la racine
          3. voxa.db (alias historique pour psg)
          4. Auto-création : si aucune DB n'existe pour ce slug, on crée
             voxa_{slug}.db avec juste la table agent_runs.

        L'auto-création (#4) permet aux agents sans données spécifiques
        (ex: SEO Agent) de tourner sur n'importe quel slug, même avant
        qu'on ait commencé à tracker ce client.
        """
        try:
            import voxa_db as vdb
            cfg = vdb.CLIENTS_CONFIG.get(slug)
            if cfg:
                db = cfg["db"] if isinstance(cfg["db"], Path) else Path(cfg["db"])
                if db.exists():
                    return db
        except Exception:
            pass

        # Tentative directe par slug
        candidate = BASE_DIR / f"voxa_{slug}.db"
        if candidate.exists():
            return candidate

        # Alias historique : voxa.db pour psg
        if slug == "psg":
            psg_db = BASE_DIR / "voxa.db"
            if psg_db.exists():
                return psg_db

        # Auto-création d'une DB minimale pour ce slug
        # (juste la table agent_runs nécessaire au logging)
        return self._create_minimal_db(candidate)

    def _create_minimal_db(self, db_path: Path) -> Path:
        """Crée une DB SQLite minimale avec juste la table agent_runs.

        Utilisé quand un agent tourne sur un slug pour lequel on n'a pas
        encore de DB Voxa complète (typiquement : SEO Agent qui audite le
        site d'un prospect avant qu'on ne configure son tracking).
        """
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    language TEXT,
                    status TEXT NOT NULL,
                    input_json TEXT,
                    output_json TEXT,
                    error_msg TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    iteration INTEGER DEFAULT 1,
                    parent_run_id INTEGER,
                    FOREIGN KEY (parent_run_id) REFERENCES agent_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_slug
                    ON agent_runs(slug, agent_name, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_parent
                    ON agent_runs(parent_run_id);
            """)
            conn.commit()
        finally:
            conn.close()
        return db_path

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