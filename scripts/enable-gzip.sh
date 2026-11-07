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

# Debian/Ubuntu active déjà « gzip on; » dans nginx.conf, mais seulement pour le HTML.
# Le répéter ferait échouer nginx : on ne l'ajoute que s'il est absent.
rm -f "$CONF"
if nginx -T 2>/dev/null | grep -Eq '^\s*gzip\s+on\s*;'; then
  GZIP_ON=""
else
  GZIP_ON="gzip on;"
fi

for directive in gzip_types gzip_vary gzip_proxied gzip_comp_level gzip_min_length; do
  if nginx -T 2>/dev/null | grep -Eq "^\s*${directive}\s"; then
    echo "« ${directive} » est déjà réglé ailleurs dans nginx : rien n'a été modifié." >&2
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
