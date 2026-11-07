#!/usr/bin/env bash
# Active la compression gzip de nginx pour le JS, le CSS, le JSON et le SVG (pages ~4x plus légères).
#   sudo bash scripts/enable-gzip.sh
# Sans risque : la configuration est vérifiée (nginx -t) avant rechargement ; en cas d'erreur,
# le fichier ajouté est retiré et nginx n'est pas touché.
set -euo pipefail

CONF=/etc/nginx/conf.d/shopm-gzip.conf

if [[ $EUID -ne 0 ]]; then
  echo "À lancer avec sudo." >&2
  exit 1
fi

# Seuls les réglages globaux (bloc http : nginx.conf et conf.d) peuvent entrer en conflit.
# Ceux d'un autre site (bloc server) restent prioritaires pour ce site et ne gênent pas.
GLOBAL_FILES=(/etc/nginx/nginx.conf /etc/nginx/conf.d/*.conf)
active() { grep -hEs "^\s*$1\s" "${GLOBAL_FILES[@]}" >/dev/null; }

# Debian/Ubuntu active déjà « gzip on; » dans nginx.conf : le répéter ferait échouer nginx.
rm -f "$CONF"
GZIP_ON="gzip on;"
if grep -hEqs '^\s*gzip\s+on\s*;' "${GLOBAL_FILES[@]}"; then GZIP_ON=""; fi

for directive in gzip_types gzip_vary gzip_proxied gzip_comp_level gzip_min_length; do
  if active "$directive"; then
    echo "« ${directive} » est déjà réglé globalement dans nginx : rien n'a été modifié." >&2
    echo "Montre-moi la sortie de : sudo nginx -T | grep -n gzip" >&2
    exit 1
  fi
done

cat > "$CONF" <<NGINX
# Ajouté par ShopM (scripts/enable-gzip.sh)
$GZIP_ON
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_min_length 1024;
gzip_types text/plain text/css text/javascript application/javascript application/json
           application/manifest+json image/svg+xml;
NGINX

if nginx -t; then
  systemctl reload nginx
  echo "✅ Compression activée."
else
  rm -f "$CONF"
  echo "❌ nginx refuse la configuration : fichier retiré, rien n'a changé." >&2
  exit 1
fi
