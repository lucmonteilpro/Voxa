#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Voxa — Run nightly (Mac local cron)
# ─────────────────────────────────────────────────────────────
# Lance le tracker UI sur tous les marchés Betclic, puis sync
# la DB vers PythonAnywhere pour que le dashboard prod soit à jour.
#
# Lancé par cron toutes les nuits à 02h00 (voir install_cron.sh).
#
# Logs : ~/Voxa/logs/voxa_nightly_AAAAMMJJ.log
# ─────────────────────────────────────────────────────────────

set -e  # exit immédiatement si une commande échoue
set -u  # exit si variable non définie utilisée

# ─────────────────────────────────────────────
# Config (à ajuster si besoin)
# ─────────────────────────────────────────────
VOXA_DIR="$HOME/Voxa"
PA_USER="lucsharper"
PA_HOST="ssh.pythonanywhere.com"
PA_VOXA_PATH="/home/$PA_USER/Voxa"

# Quels slugs et marchés crawler chaque nuit
# Format : "slug:option" — option = "--all-markets" ou "--language fr"
RUNS=(
    "betclic:--all-markets"
    # Ajouter d'autres clients ici quand prêts, ex :
    # "psg:--language fr"
    # "winamax:--all-markets"
)

# ─────────────────────────────────────────────
# Init logging
# ─────────────────────────────────────────────
DATE_STAMP=$(date +"%Y%m%d")
TIME_STAMP=$(date +"%H:%M:%S")
LOG_DIR="$VOXA_DIR/logs"
LOG_FILE="$LOG_DIR/voxa_nightly_${DATE_STAMP}.log"

mkdir -p "$LOG_DIR"

# Redirige tout (stdout + stderr) vers le log + console
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Voxa Nightly Run — $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────
# Vérifications préalables
# ─────────────────────────────────────────────
if [ ! -d "$VOXA_DIR" ]; then
    echo "✗ Voxa dir introuvable : $VOXA_DIR"
    exit 1
fi

cd "$VOXA_DIR"

# Vérifie que tracker_ui.py existe
if [ ! -f "tracker_ui.py" ]; then
    echo "✗ tracker_ui.py introuvable dans $VOXA_DIR"
    exit 1
fi

# Vérifie Python
if ! command -v python3 &> /dev/null; then
    echo "✗ python3 introuvable dans le PATH"
    exit 1
fi

# Vérifie caffeinate (macOS uniquement) - prévient la mise en veille
if command -v caffeinate &> /dev/null; then
    CAFFEINATE_CMD="caffeinate -i"
    echo "✓ caffeinate disponible (Mac restera réveillé pendant le run)"
else
    CAFFEINATE_CMD=""
    echo "⚠ caffeinate indisponible (système non-macOS ?)"
fi

echo ""

# ─────────────────────────────────────────────
# Lancement des runs tracker_ui
# ─────────────────────────────────────────────
RUN_FAILED=0
DBS_TO_SYNC=()

for entry in "${RUNS[@]}"; do
    slug="${entry%%:*}"
    options="${entry#*:}"

    echo "────────────────────────────────────────────────────────────────────"
    echo "  Run : $slug $options"
    echo "  Heure début : $(date '+%H:%M:%S')"
    echo "────────────────────────────────────────────────────────────────────"

    if $CAFFEINATE_CMD python3 tracker_ui.py --slug "$slug" $options; then
        echo "✓ Run $slug terminé avec succès"
        DBS_TO_SYNC+=("voxa_${slug}.db")
    else
        echo "✗ Run $slug ÉCHEC (exit code $?)"
        RUN_FAILED=$((RUN_FAILED + 1))
    fi
    echo ""
done

# Cas spécial : voxa.db (PSG) ne suit pas le pattern voxa_<slug>.db
# (à étendre si tu ajoutes psg dans RUNS)

# ─────────────────────────────────────────────
# Sync DB Mac → PythonAnywhere
# ─────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Sync DB vers PythonAnywhere"
echo "════════════════════════════════════════════════════════════════════"

SYNC_FAILED=0
for db_file in "${DBS_TO_SYNC[@]}"; do
    if [ ! -f "$VOXA_DIR/$db_file" ]; then
        echo "⚠ $db_file introuvable, skip"
        continue
    fi

    echo "  → $db_file ($(du -h "$VOXA_DIR/$db_file" | cut -f1))"

    if scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "$VOXA_DIR/$db_file" \
        "$PA_USER@$PA_HOST:$PA_VOXA_PATH/$db_file"; then
        echo "    ✓ Synced"
    else
        echo "    ✗ ÉCHEC SCP (exit code $?)"
        SYNC_FAILED=$((SYNC_FAILED + 1))
    fi
done

# ─────────────────────────────────────────────
# Reload du dashboard PA
# ─────────────────────────────────────────────
# Note : pas besoin de reload si on touche juste à la DB.
# Le dashboard relit la DB à chaque requête HTTP, donc les nouvelles
# données seront visibles immédiatement à la prochaine ouverture.
# (Reload = uniquement si on push du code Python modifié)

# ─────────────────────────────────────────────
# Récap final
# ─────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Récap nightly run — $(date '+%H:%M:%S')"
echo "════════════════════════════════════════════════════════════════════"
echo "  Runs tracker_ui  : ${#RUNS[@]} planifiés, $RUN_FAILED échecs"
echo "  Sync DB → PA     : ${#DBS_TO_SYNC[@]} fichiers, $SYNC_FAILED échecs"
echo "  Log complet      : $LOG_FILE"
echo "════════════════════════════════════════════════════════════════════"

# Exit code reflète le statut global
if [ $RUN_FAILED -gt 0 ] || [ $SYNC_FAILED -gt 0 ]; then
    exit 1
fi
exit 0