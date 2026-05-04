#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Voxa — Install cron entry sur Mac
# ─────────────────────────────────────────────────────────────
# Installe une entrée crontab qui lance voxa_nightly.sh tous les
# jours à 02h00.
#
# À lancer UNE SEULE FOIS après avoir configuré SSH (setup_ssh_pa.sh).
# ─────────────────────────────────────────────────────────────

set -e

VOXA_DIR="$HOME/Voxa"
SCRIPT_PATH="$VOXA_DIR/scripts/voxa_nightly.sh"
CRON_LINE="0 2 * * * $SCRIPT_PATH > /dev/null 2>&1"
CRON_MARKER="# Voxa nightly tracker UI"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Install cron Voxa nightly"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────
# 1) Vérifications préalables
# ─────────────────────────────────────────────
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "✗ $SCRIPT_PATH introuvable"
    echo "  Place voxa_nightly.sh dans $VOXA_DIR/scripts/ d'abord"
    exit 1
fi

if [ ! -x "$SCRIPT_PATH" ]; then
    echo "→ Rendre voxa_nightly.sh exécutable..."
    chmod +x "$SCRIPT_PATH"
    echo "✓ chmod +x appliqué"
fi

# ─────────────────────────────────────────────
# 2) Affiche la cron actuelle
# ─────────────────────────────────────────────
echo ""
echo "Cron actuelle (avant modif) :"
echo "────────────────────────────────────────────────────────────────────"
crontab -l 2>/dev/null || echo "  (cron vide)"
echo "────────────────────────────────────────────────────────────────────"
echo ""

# ─────────────────────────────────────────────
# 3) Vérifie si l'entry existe déjà
# ─────────────────────────────────────────────
if crontab -l 2>/dev/null | grep -q "$SCRIPT_PATH"; then
    echo "✓ Entry Voxa déjà présente dans la cron"
    echo "  (rien à faire)"
    exit 0
fi

# ─────────────────────────────────────────────
# 4) Ajoute l'entry
# ─────────────────────────────────────────────
echo "→ Ajout de l'entry cron :"
echo "    $CRON_LINE"
echo ""

(crontab -l 2>/dev/null || true; echo ""; echo "$CRON_MARKER"; echo "$CRON_LINE") | crontab -

echo "✓ Entry cron ajoutée"
echo ""
echo "Cron actuelle (après modif) :"
echo "────────────────────────────────────────────────────────────────────"
crontab -l
echo "────────────────────────────────────────────────────────────────────"
echo ""

# ─────────────────────────────────────────────
# 5) Notes importantes
# ─────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  ✓ Cron installé. Le script tournera chaque nuit à 02h00."
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "Notes importantes :"
echo ""
echo "  1) Mac doit être ALLUMÉ à 02h00 (pas obligatoirement réveillé,"
echo "     caffeinate dans le script empêche la veille pendant l'exécution)"
echo ""
echo "  2) Si tu fermes ton Mac (capot rabattu sur portable), la cron"
echo "     ne tournera PAS. Pour qu'elle tourne capot fermé :"
echo "     System Preferences > Battery > Adapter > 'Prevent sleep when display off'"
echo ""
echo "  3) Logs disponibles dans : $VOXA_DIR/logs/voxa_nightly_AAAAMMJJ.log"
echo ""
echo "  4) Pour test manuel maintenant, lance :"
echo "     $SCRIPT_PATH"
echo ""
echo "  5) Pour désactiver la cron plus tard :"
echo "     crontab -e   # puis supprimer la ligne Voxa"
echo ""