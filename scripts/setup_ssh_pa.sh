#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Voxa — Setup SSH key Mac → PythonAnywhere
# ─────────────────────────────────────────────────────────────
# Configure une SSH key pour que SCP puisse se faire sans mot de passe
# entre ton Mac et PA.
#
# À lancer UNE SEULE FOIS depuis ton Mac.
# Tu auras besoin de saisir ton mot de passe PA UNE FOIS pendant le setup.
# ─────────────────────────────────────────────────────────────

set -e

PA_USER="lucsharper"
PA_HOST="ssh.pythonanywhere.com"
SSH_KEY="$HOME/.ssh/voxa_pa_rsa"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Setup SSH Mac → PythonAnywhere"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────
# 1) Génère une SSH key dédiée si absente
# ─────────────────────────────────────────────
if [ -f "$SSH_KEY" ]; then
    echo "✓ SSH key existe déjà : $SSH_KEY"
    echo "  (skip génération)"
else
    echo "→ Génération d'une SSH key dédiée Voxa↔PA..."
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -C "voxa-mac-to-pa-$(date +%Y%m%d)"
    echo "✓ Key créée : $SSH_KEY"
fi

# ─────────────────────────────────────────────
# 2) Ajoute la key dans ~/.ssh/config pour usage automatique
# ─────────────────────────────────────────────
SSH_CONFIG="$HOME/.ssh/config"
touch "$SSH_CONFIG"
chmod 600 "$SSH_CONFIG"

if grep -q "Host $PA_HOST" "$SSH_CONFIG" 2>/dev/null; then
    echo "✓ Entry SSH config existe déjà pour $PA_HOST"
else
    echo "→ Ajout de l'entry dans $SSH_CONFIG..."
    cat >> "$SSH_CONFIG" <<EOF

# Voxa - PythonAnywhere
Host $PA_HOST
    User $PA_USER
    IdentityFile $SSH_KEY
    IdentitiesOnly yes
    ServerAliveInterval 60
EOF
    echo "✓ Config ajoutée"
fi

# ─────────────────────────────────────────────
# 3) Copie la public key sur PA
# ─────────────────────────────────────────────
echo ""
echo "→ Copie de la public key vers PA (mot de passe demandé) :"
echo ""

# ssh-copy-id n'est pas disponible par défaut sur macOS, on fait à la main
PUBKEY=$(cat "$SSH_KEY.pub")

ssh "$PA_USER@$PA_HOST" "
mkdir -p ~/.ssh && chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
if ! grep -q '$PUBKEY' ~/.ssh/authorized_keys 2>/dev/null; then
    echo '$PUBKEY' >> ~/.ssh/authorized_keys
    echo '✓ Key ajoutée sur PA'
else
    echo '✓ Key déjà présente sur PA'
fi
"

# ─────────────────────────────────────────────
# 4) Test la connexion sans mot de passe
# ─────────────────────────────────────────────
echo ""
echo "→ Test connexion SSH sans mot de passe..."
if ssh -o BatchMode=yes -o ConnectTimeout=10 "$PA_HOST" "echo '✓ Connexion OK'"; then
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  ✓ Setup SSH terminé avec succès"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""
    echo "  Tu peux maintenant tester un SCP manuel :"
    echo "  scp ~/Voxa/voxa_betclic.db $PA_HOST:~/Voxa/voxa_betclic.db"
    echo ""
else
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  ✗ Connexion SSH automatique KO"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""
    echo "  La key a été créée et ajoutée, mais la connexion automatique"
    echo "  ne fonctionne pas encore. Vérifications possibles :"
    echo ""
    echo "  1) PA peut bloquer les keys < 24h après création"
    echo "  2) Vérifie ~/.ssh/authorized_keys sur PA via la console web"
    echo "  3) Permissions : chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
    echo ""
    exit 1
fi